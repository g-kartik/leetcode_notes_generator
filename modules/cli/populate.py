"""`populate` command group: fetch and store problem data, part by part."""

import click
import structlog

from modules.leetcode.pipeline import LeetCodeSyncManager

from .common import get_manager, print_batch_summary
from .root import cli

logger = structlog.get_logger(__name__)

# --------------------------------------------------------------------------- #
# Shared part info (used by `populate` and its batch-resolution helpers)
# --------------------------------------------------------------------------- #

_PART_METHODS = {
    "problem": "populate_question_metadata",
    "images": "populate_question_images",
    "submission": "populate_submission_code",
}
_PART_CACHE_KEYS = {
    "problem": "question",
    "images": "images",
    "submission": "submission",
}
_PART_ORDER = ("problem", "images", "submission")


def _is_populated(mgr: LeetCodeSyncManager, part_name: str, slug: str) -> bool:
    """Whether `part_name` already has data for `slug`, without touching the network."""
    log = logger.bind(slug=slug, stage=part_name)

    if part_name == "submission":
        found = mgr.storage.submissions_exists(slug)
        log.info("part_populated_check", already_populated=found)
        return found

    record = mgr.storage.problems_get_by_slug(slug)
    if record is None:
        log.info("part_populated_check", already_populated=False, reason="no_problem_record_stored")
        return False
    if part_name == "problem":
        found = bool(record.raw_question_html)
    elif part_name == "images":
        found = bool(record.imgs_local_paths)
    else:
        raise ValueError(f"Unknown part: {part_name}")

    log.info("part_populated_check", already_populated=found)
    return found


def _run_part_for_slug(mgr: LeetCodeSyncManager, part_name: str, slug: str, force: bool) -> str:
    """Runs one pipeline part for one slug. Returns 'skipped', 'success', or 'failed'."""
    with structlog.contextvars.bound_contextvars(slug=slug, stage=part_name):
        log = logger.bind()

        if not force and _is_populated(mgr, part_name, slug):
            log.info("part_populate_skipped", reason="already_populated_using_stored_data")
            return "skipped"

        log.info("part_populate_started", force=force)
        method = getattr(mgr, _PART_METHODS[part_name])
        succeeded = method(slug, force_update=force)

        status = "success" if succeeded else "failed"
        log.info("part_populate_finished", status=status)
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

    key = _PART_CACHE_KEYS[part_name]
    cache = mgr.storage.read_pending_cache()
    slugs = [slug for slug, parts in cache.items() if not parts.get(key, False)]
    logger.info("part_batch_slugs_resolved", stage=part_name, source="pending_cache", slug_count=len(slugs))
    return slugs


def _resolve_any_pending_slugs(mgr: LeetCodeSyncManager, no_cache: bool) -> list[str]:
    """Slugs to target for a `populate all --all` run (any part still outstanding)."""
    if no_cache:
        slugs = [r.slug for r in mgr.storage.list_all() if r.slug]
        logger.info("populate_all_slugs_resolved", source="db", slug_count=len(slugs))
        return slugs
    slugs = list(mgr.storage.read_pending_cache().keys())
    logger.info("populate_all_slugs_resolved", source="pending_cache", slug_count=len(slugs))
    return slugs


def _validate_target(slug: str | None, run_all: bool, no_cache: bool) -> None:
    if slug and run_all:
        raise click.UsageError("Pass either SLUG or --all, not both.")
    if not slug and not run_all:
        raise click.UsageError("Pass either SLUG or --all.")
    if no_cache and not run_all:
        raise click.UsageError("--no-cache only applies with --all.")


def _target_options(f):
    """Shared SLUG / --all / --no-cache / --force options for populate subcommands."""
    f = click.argument("slug", required=False)(f)
    f = click.option(
        "--all", "run_all", is_flag=True,
        help="Run against every slug still pending this part in the cache.",
    )(f)
    f = click.option(
        "--no-cache", "no_cache", is_flag=True,
        help="With --all, target every slug in the database instead of just cache-pending ones.",
    )(f)
    f = click.option(
        "--force/--no-force", default=False,
        help="Refetch even if this part's data already exists.",
    )(f)
    return f


@cli.group()
def populate() -> None:
    """Fetch and store problem data, part by part."""


def _run_part_command(
    mgr: LeetCodeSyncManager, part_name: str, slug: str | None, run_all: bool, no_cache: bool, force: bool
) -> None:
    _validate_target(slug, run_all, no_cache)

    if slug:
        status = _run_part_for_slug(mgr, part_name, slug, force)
        click.echo(_describe(part_name, slug, status))
        if status == "failed":
            raise click.ClickException(f"could not populate '{part_name}' for '{slug}' — no data returned")
        return

    slugs = _resolve_part_batch_slugs(mgr, part_name, no_cache)
    if not slugs:
        logger.info("populate_command_batch_completed", stage=part_name, reason="no_slugs_pending")
        click.echo("Nothing to do — no slugs pending.")
        return

    logger.info("populate_command_batch_started", stage=part_name, slug_count=len(slugs))
    succeeded, skipped, failed = [], [], []
    buckets = {"success": succeeded, "skipped": skipped, "failed": failed}
    for target_slug in slugs:
        status = _run_part_for_slug(mgr, part_name, target_slug, force)
        click.echo(_describe(part_name, target_slug, status))
        buckets[status].append(target_slug)

    logger.info(
        "populate_command_batch_completed",
        stage=part_name,
        succeeded_count=len(succeeded),
        skipped_count=len(skipped),
        failed_count=len(failed),
    )
    print_batch_summary(succeeded, failed, skipped)


@populate.command("problem")
@_target_options
def populate_problem(slug: str | None, run_all: bool, no_cache: bool, force: bool) -> None:
    """Fetch the problem's description and metadata."""
    _run_part_command(get_manager(), "problem", slug, run_all, no_cache, force)


@populate.command("images")
@_target_options
def populate_images(slug: str | None, run_all: bool, no_cache: bool, force: bool) -> None:
    """Download question images (requires the problem to already exist)."""
    _run_part_command(get_manager(), "images", slug, run_all, no_cache, force)


@populate.command("submission")
@_target_options
def populate_submission(slug: str | None, run_all: bool, no_cache: bool, force: bool) -> None:
    """Fetch the latest accepted submission's code."""
    _run_part_command(get_manager(), "submission", slug, run_all, no_cache, force)


@populate.command("all")
@_target_options
def populate_all(slug: str | None, run_all: bool, no_cache: bool, force: bool) -> None:
    """Run problem, then images, then submission, in that fixed order."""
    _validate_target(slug, run_all, no_cache)
    mgr = get_manager()

    if slug:
        failed_parts = []
        for part_name in _PART_ORDER:
            status = _run_part_for_slug(mgr, part_name, slug, force)
            click.echo(_describe(part_name, slug, status))
            if status == "failed":
                failed_parts.append(part_name)
        if failed_parts:
            raise click.ClickException(f"'{slug}' failed part(s): {', '.join(failed_parts)}")
        return

    slugs = _resolve_any_pending_slugs(mgr, no_cache)
    if not slugs:
        logger.info("populate_all_command_completed", reason="no_slugs_pending")
        click.echo("Nothing to do — no slugs pending.")
        return

    logger.info("populate_all_command_started", slug_count=len(slugs))
    succeeded, failed = [], []
    for target_slug in slugs:
        slug_failed = False
        for part_name in _PART_ORDER:
            status = _run_part_for_slug(mgr, part_name, target_slug, force)
            click.echo(_describe(part_name, target_slug, status))
            slug_failed = slug_failed or status == "failed"
        (failed if slug_failed else succeeded).append(target_slug)

    logger.info(
        "populate_all_command_completed",
        succeeded_count=len(succeeded),
        failed_count=len(failed),
    )
    print_batch_summary(succeeded, failed)
