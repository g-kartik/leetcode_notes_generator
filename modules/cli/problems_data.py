"""`problems data` command group: fetch problem data, and manage the
pending-slugs cache used to track what's still outstanding."""

import click
import structlog

from modules.sync.pipeline import LeetCodeSyncManager

from .common import BatchPacer, CircuitBreaker, get_manager, print_batch_summary
from .picker import label_slugs, pick_slugs
from .problems import problems

logger = structlog.get_logger(__name__)

# --------------------------------------------------------------------------- #
# Shared part info (used by `fetch` and its batch-resolution helpers)
# --------------------------------------------------------------------------- #

_PART_METHODS = {
    "description": "populate_question_metadata",
    "images": "populate_question_images",
    "submission": "populate_submission_code",
}
_PART_ORDER = ("description", "images", "submission")


def _is_populated(mgr: LeetCodeSyncManager, part_name: str, slug: str) -> bool:
    """Whether `part_name` already has data for `slug`, without touching the network."""
    log = logger.bind(slug=slug, stage=part_name)

    if part_name == "submission":
        exists = mgr.storage.submissions_exists(slug)
        # A submission can exist but still be cache-pending — e.g. reopened by
        # reconcile_recent_accepted because a fresher accepted submission was seen.
        reopened = mgr.storage.is_part_pending(slug, "submission")
        found = exists and not reopened
        log.info("part_populated_check", already_populated=found, exists=exists, reopened=reopened)
        return found

    record = mgr.storage.problems_get_by_slug(slug)
    if record is None:
        log.info("part_populated_check", already_populated=False, reason="no_problem_record_stored")
        return False
    if part_name == "description":
        found = bool(record.raw_question_html)
    elif part_name == "images":
        # A question can legitimately have zero images (has_images=False,
        # done) or have images that all failed to download so far
        # (has_images=True, imgs_local_paths still empty, worth retrying) —
        # images_populated tells the two apart instead of just checking
        # imgs_local_paths truthiness.
        found = record.images_populated
    else:
        raise ValueError(f"Unknown part: {part_name}")

    log.info("part_populated_check", already_populated=found)
    return found


def _run_part_for_slug(mgr: LeetCodeSyncManager, part_name: str, slug: str, refetch: bool) -> str:
    """Runs one pipeline part for one slug. Returns 'skipped', 'success', or 'failed'."""
    with structlog.contextvars.bound_contextvars(slug=slug, stage=part_name):
        log = logger.bind()

        if not refetch and _is_populated(mgr, part_name, slug):
            log.info("part_fetch_skipped", reason="already_populated_using_stored_data")
            return "skipped"

        log.info("part_fetch_started", refetch=refetch)
        method = getattr(mgr, _PART_METHODS[part_name])
        succeeded = method(slug, force_update=refetch)

        status = "success" if succeeded else "failed"
        log.info("part_fetch_finished", status=status)
        return status


def _describe(part_name: str, slug: str, status: str) -> str:
    labels = {"success": "done", "skipped": "skip", "failed": "fail"}
    return f"[{labels[status]:>4}] {part_name:<10} {slug}"


def _resolve_part_batch_slugs(mgr: LeetCodeSyncManager, part_name: str, no_cache: bool) -> list[str]:
    """Slugs to target for a single-part --all run."""
    if no_cache:
        slugs = [r.slug for r in mgr.storage.list_all() if r.slug]
        logger.info("part_batch_slugs_resolved", stage=part_name, source="db", slug_count=len(slugs))
        return slugs

    cache = mgr.storage.read_pending_cache()
    slugs = [slug for slug, parts in cache.items() if not parts.get(part_name, False)]
    logger.info("part_batch_slugs_resolved", stage=part_name, source="pending_cache", slug_count=len(slugs))
    return slugs


def _resolve_any_pending_slugs(mgr: LeetCodeSyncManager, no_cache: bool) -> list[str]:
    """Slugs to target for a `fetch --part full --all` run (any part still outstanding)."""
    if no_cache:
        slugs = [r.slug for r in mgr.storage.list_all() if r.slug]
        logger.info("full_fetch_slugs_resolved", source="db", slug_count=len(slugs))
        return slugs
    slugs = list(mgr.storage.read_pending_cache().keys())
    logger.info("full_fetch_slugs_resolved", source="pending_cache", slug_count=len(slugs))
    return slugs


def _validate_target(
    slug: str | None, run_all: bool, no_cache: bool, limit: int | None = None
) -> None:
    """Neither SLUG nor --all is valid — it means "pick interactively" (see _pick_target_slugs)."""
    if slug and run_all:
        raise click.UsageError("Pass either SLUG or --all, not both.")
    if no_cache and not run_all:
        raise click.UsageError("--no-cache only applies with --all.")
    if limit is not None and not run_all:
        raise click.UsageError("--limit only applies with --all.")


def _pick_target_slugs(mgr: LeetCodeSyncManager, candidates: list[str]) -> list[str]:
    """
    Interactive fallback for when neither SLUG nor --all was given: a
    searchable multi-select over `candidates`, labeled with title/difficulty
    wherever a problem record already exists (falls back to the bare slug
    otherwise — e.g. a solved-but-not-yet-fetched slug from the pending
    cache, which has no title yet). Returns [] (having already told the
    user why) if there's nothing to pick from or nothing was selected.
    """
    if not candidates:
        click.echo("Nothing to pick from — no slugs pending.")
        return []
    known = {r.slug: r for r in mgr.storage.list_all() if r.slug}
    picked = pick_slugs(label_slugs(candidates, known))
    if not picked:
        click.echo("Nothing selected.")
    return picked


def _apply_limit(stage: str, slugs: list[str], limit: int | None) -> list[str]:
    """Caps a resolved batch to at most `limit` slugs, so a large backlog can be
    worked through over several runs instead of one long, easily-noticed session."""
    if not limit or len(slugs) <= limit:
        return slugs
    logger.info("fetch_batch_capped", stage=stage, limit=limit, total_pending=len(slugs))
    return slugs[:limit]


def _report_circuit_break(stage: str, remaining_count: int, max_failures: int) -> None:
    """Logs + echoes that a batch stopped early — the remaining slugs are simply
    left pending (nothing lost) for a later, hopefully-unblocked run."""
    logger.warning(
        "fetch_batch_aborted",
        stage=stage,
        reason="too_many_consecutive_failures",
        max_consecutive_failures=max_failures,
        remaining_slug_count=remaining_count,
    )
    click.echo(
        f"\n[abort] {max_failures} consecutive failures — stopping early, "
        f"{remaining_count} slug(s) left pending for a later run."
    )


def _run_single_part(
    mgr: LeetCodeSyncManager,
    part_name: str,
    slug: str | None,
    run_all: bool,
    no_cache: bool,
    refetch: bool,
    limit: int | None,
    max_failures: int,
    batch_size: int,
) -> None:
    if slug:
        status = _run_part_for_slug(mgr, part_name, slug, refetch)
        click.echo(_describe(part_name, slug, status))
        if status == "failed":
            raise click.ClickException(f"could not fetch '{part_name}' for '{slug}' — no data returned")
        return

    if run_all:
        slugs = _apply_limit(part_name, _resolve_part_batch_slugs(mgr, part_name, no_cache), limit)
        if not slugs:
            logger.info("fetch_command_batch_completed", stage=part_name, reason="no_slugs_pending")
            click.echo("Nothing to do — no slugs pending.")
            return
    else:
        slugs = _pick_target_slugs(mgr, _resolve_part_batch_slugs(mgr, part_name, no_cache))
        if not slugs:
            return

    logger.info("fetch_command_batch_started", stage=part_name, slug_count=len(slugs))
    succeeded, skipped, failed = [], [], []
    buckets = {"success": succeeded, "skipped": skipped, "failed": failed}
    breaker = CircuitBreaker(max_failures)
    pacer = BatchPacer(batch_size)
    total = len(slugs)
    for idx, target_slug in enumerate(slugs):
        status = _run_part_for_slug(mgr, part_name, target_slug, refetch)
        click.echo(_describe(part_name, target_slug, status))
        buckets[status].append(target_slug)

        breaker.record(status == "failed")
        if breaker.tripped:
            _report_circuit_break(part_name, total - idx - 1, max_failures)
            break

        if pacer.should_pause_after(idx + 1, total):
            pacer.pause(part_name, idx + 1, total)

    logger.info(
        "fetch_command_batch_completed",
        stage=part_name,
        succeeded_count=len(succeeded),
        skipped_count=len(skipped),
        failed_count=len(failed),
    )
    print_batch_summary(succeeded, failed, skipped)


def _run_full(
    mgr: LeetCodeSyncManager,
    slug: str | None,
    run_all: bool,
    no_cache: bool,
    refetch: bool,
    limit: int | None,
    max_failures: int,
    batch_size: int,
) -> None:
    if slug:
        failed_parts = []
        for part_name in _PART_ORDER:
            status = _run_part_for_slug(mgr, part_name, slug, refetch)
            click.echo(_describe(part_name, slug, status))
            if status == "failed":
                failed_parts.append(part_name)
        if failed_parts:
            raise click.ClickException(f"'{slug}' failed part(s): {', '.join(failed_parts)}")
        return

    if run_all:
        slugs = _apply_limit("full", _resolve_any_pending_slugs(mgr, no_cache), limit)
        if not slugs:
            logger.info("full_fetch_command_completed", reason="no_slugs_pending")
            click.echo("Nothing to do — no slugs pending.")
            return
    else:
        slugs = _pick_target_slugs(mgr, _resolve_any_pending_slugs(mgr, no_cache))
        if not slugs:
            return

    logger.info("full_fetch_command_started", slug_count=len(slugs))
    succeeded, failed = [], []
    breaker = CircuitBreaker(max_failures)
    pacer = BatchPacer(batch_size)
    total = len(slugs)
    for idx, target_slug in enumerate(slugs):
        slug_failed = False
        for part_name in _PART_ORDER:
            status = _run_part_for_slug(mgr, part_name, target_slug, refetch)
            click.echo(_describe(part_name, target_slug, status))
            slug_failed = slug_failed or status == "failed"
        (failed if slug_failed else succeeded).append(target_slug)

        breaker.record(slug_failed)
        if breaker.tripped:
            _report_circuit_break("full", total - idx - 1, max_failures)
            break

        if pacer.should_pause_after(idx + 1, total):
            pacer.pause("full", idx + 1, total)

    logger.info(
        "full_fetch_command_completed",
        succeeded_count=len(succeeded),
        failed_count=len(failed),
    )
    print_batch_summary(succeeded, failed)


@problems.group()
def data() -> None:
    """Fetch problem data, and manage the pending-slugs cache."""


@data.command("fetch")
@click.argument("slug", required=False)
@click.option(
    "--part", "part_name",
    type=click.Choice(["description", "images", "submission", "full"]),
    default="full", show_default=True,
    help="Which part to fetch. 'full' runs description, then images, then "
    "submission, in that fixed order — matches the dependency chain where "
    "images/submission need the description to exist first.",
)
@click.option(
    "--all", "run_all", is_flag=True,
    help="Run against every slug still pending this part in the cache "
    "('full' pending any part). Omit both SLUG and --all to pick "
    "interactively instead.",
)
@click.option(
    "--no-cache", "no_cache", is_flag=True,
    help="With --all, target every slug in the database instead of just cache-pending ones.",
)
@click.option(
    "--refetch", is_flag=True,
    help="Refetch even if this part's data already exists.",
)
@click.option(
    "--limit", "limit", type=int, default=None,
    help="With --all, cap the run to at most this many slugs — spreads a large "
    "backlog across several runs instead of one long session.",
)
@click.option(
    "--max-failures", "max_failures", type=int, default=5, show_default=True,
    help="With --all, abort the run after this many consecutive failures "
    "(likely rate-limited/blocked). 0 disables.",
)
@click.option(
    "--batch-size", "batch_size", type=int, default=25, show_default=True,
    help="With --all, pause for a randomized 60-120s cooldown after every N slugs, "
    "so a large backlog runs as several short sessions instead of one long, "
    "uninterrupted burst. 0 disables.",
)
def data_fetch(
    slug: str | None,
    part_name: str,
    run_all: bool,
    no_cache: bool,
    refetch: bool,
    limit: int | None,
    max_failures: int,
    batch_size: int,
) -> None:
    """Fetch and store problem data. Defaults to 'full'."""
    _validate_target(slug, run_all, no_cache, limit)
    mgr = get_manager()
    if part_name == "full":
        _run_full(mgr, slug, run_all, no_cache, refetch, limit, max_failures, batch_size)
    else:
        _run_single_part(mgr, part_name, slug, run_all, no_cache, refetch, limit, max_failures, batch_size)


# --------------------------------------------------------------------------- #
# `problems data pending`
# --------------------------------------------------------------------------- #

def _print_cache_table(entries: dict[str, dict[str, bool]]) -> None:
    header = f"{'SLUG':<45}{'DESCRIPTION':^13}{'IMAGES':^12}{'SUBMISSION':^12}"
    click.echo(header)
    click.echo("-" * len(header))
    for slug, parts in entries.items():
        row = f"{slug:<45}"
        for key in ("description", "images", "submission"):
            row += f"{'yes' if parts.get(key, False) else '-':^12}"
        click.echo(row)


@data.group()
def pending() -> None:
    """Inspect and manage the pending-slugs cache."""


@pending.command("sync")
def pending_sync() -> None:
    """
    Hard-refresh the pending cache from LeetCode, then report what's still
    outstanding. Always hits the network (LeetCode's complete solved-list,
    plus the recent-accepted-submissions feed) — for a free, local-only view
    of the cache instead, use `pending list` / `pending count` / `pending show`.
    """
    log = logger.bind(stage="pending_sync")
    log.info("pending_sync_command_started")

    result = get_manager().sync_pending_cache()

    click.echo(f"{len(result['new_slugs'])} new slug(s) discovered.")
    click.echo(f"{len(result['stale_submission_slugs'])} submission(s) resubmitted since last sync.")
    click.echo(f"{len(result['pending_slugs'])} slug(s) pending overall.")
    for slug in result["pending_slugs"]:
        click.echo(f"  - {slug}")

    log.info("pending_sync_command_completed", pending_count=len(result["pending_slugs"]))


@pending.command("count")
def pending_count() -> None:
    """Print the number of slugs with at least one part still pending. Read-only."""
    logger.bind(stage="pending").info("pending_count_command_started")
    click.echo(str(len(get_manager().storage.read_pending_cache())))


@pending.command("list")
def pending_list() -> None:
    """List every slug with at least one part still pending. Read-only."""
    logger.bind(stage="pending").info("pending_list_command_started")
    entries = get_manager().storage.read_pending_cache()
    if not entries:
        click.echo("Cache is empty — nothing pending.")
        return
    _print_cache_table(entries)


@pending.command("show")
@click.argument("slug", required=False)
def pending_show(slug: str | None) -> None:
    """Show cache progress for one or more slugs. Omit SLUG to pick
    interactively instead — a searchable, multi-select prompt over every
    pending slug."""
    mgr = get_manager()
    entries = mgr.storage.read_pending_cache()

    if slug:
        with structlog.contextvars.bound_contextvars(slug=slug, stage="pending"):
            logger.info("pending_show_command_started")
            entry = entries.get(slug)
            if entry is None:
                logger.info("pending_show_command_skipped", reason="slug_not_tracked")
                raise click.ClickException(f"'{slug}' is not in the pending cache (fully done, or never tracked).")
            _print_cache_table({slug: entry})
        return

    slugs = _pick_target_slugs(mgr, list(entries.keys()))
    if not slugs:
        return
    _print_cache_table({s: entries[s] for s in slugs})


@pending.command("clear")
@click.argument("slug", required=False)
def pending_clear(slug: str | None) -> None:
    """Manually drop one or more slugs from the pending cache. Omit SLUG to
    pick interactively instead — a searchable, multi-select prompt over
    every pending slug."""
    mgr = get_manager()

    if slug:
        with structlog.contextvars.bound_contextvars(slug=slug, stage="pending"):
            logger.info("pending_clear_command_started")
            if mgr.storage.remove_from_cache(slug):
                click.echo(f"Removed '{slug}' from the pending cache.")
            else:
                click.echo(f"'{slug}' was not in the pending cache.")
        return

    slugs = _pick_target_slugs(mgr, list(mgr.storage.read_pending_cache().keys()))
    if not slugs:
        return
    for target_slug in slugs:
        with structlog.contextvars.bound_contextvars(slug=target_slug, stage="pending"):
            logger.info("pending_clear_command_started")
            if mgr.storage.remove_from_cache(target_slug):
                click.echo(f"Removed '{target_slug}' from the pending cache.")
            else:
                click.echo(f"'{target_slug}' was not in the pending cache.")
