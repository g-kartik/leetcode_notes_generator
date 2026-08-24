"""Command-line interface for the LeetCode notes generator.

Thin wrapper around `LeetCodeSyncManager` (fetch/store) and
`LeetCodeDSAProblemMarkdownRender` (render). All commands are safe to re-run:
each `populate` step only does network work when the target data is missing
or `--force` is passed.
"""

import json
from pathlib import Path

import click

from modules.leetcode.pipeline import LeetCodeSyncManager
from modules.render.markdown_problem import LeetCodeDSAProblemMarkdownRender
from modules.render.utils import FileVariant

_manager_instance: LeetCodeSyncManager | None = None


def _manager() -> LeetCodeSyncManager:
    """Lazily builds the shared sync manager, so `--help` never touches disk/network setup."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = LeetCodeSyncManager()
    return _manager_instance

# --------------------------------------------------------------------------- #
# Shared part metadata (used by `populate` and its batch-resolution helpers)
# --------------------------------------------------------------------------- #

_PART_METHODS = {
    "metadata": "populate_question_metadata",
    "images": "populate_question_images",
    "submission": "populate_submission_code",
}
_PART_CACHE_KEYS = {
    "metadata": "question",
    "images": "images",
    "submission": "submission",
}
_PART_ORDER = ("metadata", "images", "submission")


def _is_populated(mgr: LeetCodeSyncManager, part_name: str, slug: str) -> bool:
    """Whether `part_name` already has data for `slug`, without touching the network."""
    if part_name == "submission":
        return mgr.storage.submissions_exists(slug)

    record = mgr.storage.problems_get_by_slug(slug)
    if record is None:
        return False
    if part_name == "metadata":
        return bool(record.raw_question_html)
    if part_name == "images":
        return bool(record.imgs_local_paths)
    raise ValueError(f"Unknown part: {part_name}")


def _run_part_for_slug(mgr: LeetCodeSyncManager, part_name: str, slug: str, force: bool) -> str:
    """Runs one pipeline part for one slug. Returns 'skipped', 'success', or 'failed'."""
    if not force and _is_populated(mgr, part_name, slug):
        return "skipped"

    method = getattr(mgr, _PART_METHODS[part_name])
    return "success" if method(slug, force_update=force) else "failed"


def _describe(part_name: str, slug: str, status: str) -> str:
    labels = {"success": "done", "skipped": "skip", "failed": "fail"}
    return f"[{labels[status]:>4}] {part_name:<10} {slug}"


def _resolve_part_batch_slugs(mgr: LeetCodeSyncManager, part_name: str, no_cache: bool) -> list[str]:
    """Slugs to target for a single-part --all run."""
    if no_cache:
        return [r.slug for r in mgr.storage.list_all() if r.slug]

    key = _PART_CACHE_KEYS[part_name]
    cache = mgr.storage.read_pending_cache()
    return [slug for slug, parts in cache.items() if not parts.get(key, False)]


def _resolve_any_pending_slugs(mgr: LeetCodeSyncManager, no_cache: bool) -> list[str]:
    """Slugs to target for a `populate all --all` run (any part still outstanding)."""
    if no_cache:
        return [r.slug for r in mgr.storage.list_all() if r.slug]
    return list(mgr.storage.read_pending_cache().keys())


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


def _print_batch_summary(succeeded: list[str], failed: list[str], skipped: list[str] | None = None) -> None:
    parts = [f"{len(succeeded)} succeeded"]
    if skipped is not None:
        parts.append(f"{len(skipped)} skipped")
    parts.append(f"{len(failed)} failed")
    summary = ", ".join(parts)
    if failed:
        summary += f": {failed}"
    click.echo(f"\n{summary}")


# --------------------------------------------------------------------------- #
# Root group
# --------------------------------------------------------------------------- #


@click.group()
def cli() -> None:
    """LeetCode notes generator."""


# --------------------------------------------------------------------------- #
# sync
# --------------------------------------------------------------------------- #


@cli.command()
@click.option(
    "--refresh/--no-refresh", default=False,
    help="Hit the LeetCode API for the current solved list before reporting.",
)
def sync(refresh: bool) -> None:
    """Report slugs still pending metadata/images/submission."""
    mgr = _manager()
    pending = mgr.sync_solved_questions_data_entry(force_refresh=refresh)

    click.echo(f"{len(pending)} slug(s) pending.")
    for slug in pending:
        click.echo(f"  - {slug}")


# --------------------------------------------------------------------------- #
# populate
# --------------------------------------------------------------------------- #


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
        click.echo("Nothing to do — no slugs pending.")
        return

    succeeded, skipped, failed = [], [], []
    buckets = {"success": succeeded, "skipped": skipped, "failed": failed}
    for target_slug in slugs:
        status = _run_part_for_slug(mgr, part_name, target_slug, force)
        click.echo(_describe(part_name, target_slug, status))
        buckets[status].append(target_slug)

    _print_batch_summary(succeeded, failed, skipped)


@populate.command("metadata")
@_target_options
def populate_metadata(slug: str | None, run_all: bool, no_cache: bool, force: bool) -> None:
    """Fetch question metadata + description."""
    _run_part_command(_manager(), "metadata", slug, run_all, no_cache, force)


@populate.command("images")
@_target_options
def populate_images(slug: str | None, run_all: bool, no_cache: bool, force: bool) -> None:
    """Download question images (requires metadata to already exist)."""
    _run_part_command(_manager(), "images", slug, run_all, no_cache, force)


@populate.command("submission")
@_target_options
def populate_submission(slug: str | None, run_all: bool, no_cache: bool, force: bool) -> None:
    """Fetch the latest accepted submission's code."""
    _run_part_command(_manager(), "submission", slug, run_all, no_cache, force)


@populate.command("all")
@_target_options
def populate_all(slug: str | None, run_all: bool, no_cache: bool, force: bool) -> None:
    """Run metadata, then images, then submission, in that fixed order."""
    _validate_target(slug, run_all, no_cache)
    mgr = _manager()

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
        click.echo("Nothing to do — no slugs pending.")
        return

    succeeded, failed = [], []
    for target_slug in slugs:
        slug_failed = False
        for part_name in _PART_ORDER:
            status = _run_part_for_slug(mgr, part_name, target_slug, force)
            click.echo(_describe(part_name, target_slug, status))
            slug_failed = slug_failed or status == "failed"
        (failed if slug_failed else succeeded).append(target_slug)

    _print_batch_summary(succeeded, failed)


# --------------------------------------------------------------------------- #
# render
# --------------------------------------------------------------------------- #


@cli.command()
@click.argument("slug", required=False)
@click.option(
    "--all", "run_all", is_flag=True,
    help="Render every slug that already has metadata populated.",
)
@click.option(
    "--variant",
    type=click.Choice([v.value for v in FileVariant]),
    default=FileVariant.ALL.value,
    show_default=True,
)
@click.option(
    "--output-base", "output_base", type=click.Path(path_type=Path), default=None,
    help="Defaults to render_settings.DEFAULT_WRITE_DIR.",
)
@click.option("--obsidian/--no-obsidian", "obsidian", default=False)
def render(
    slug: str | None,
    run_all: bool,
    variant: str,
    output_base: Path | None,
    obsidian: bool,
) -> None:
    """Render a stored question into Markdown notes."""
    if slug and run_all:
        raise click.UsageError("Pass either SLUG or --all, not both.")
    if not slug and not run_all:
        raise click.UsageError("Pass either SLUG or --all.")

    mgr = _manager()
    renderer = LeetCodeDSAProblemMarkdownRender(
        variant=FileVariant(variant),
        output_base=output_base,
        write_to_obsidian_vault=obsidian,
    )

    if slug:
        record = mgr.storage.get_combined_by_slug(slug)
        if record is None or not record.raw_question_html:
            raise click.ClickException(f"no metadata found for '{slug}', run 'populate metadata {slug}' first")
        renderer.save(record)
        click.echo(f"[done] rendered {slug}")
        return

    records = [r for r in mgr.storage.list_all_combined() if r.raw_question_html]
    if not records:
        click.echo("Nothing to render — no slugs have metadata populated yet.")
        return

    succeeded, failed = [], []
    for record in records:
        try:
            renderer.save(record)
        except Exception as exc:
            click.echo(f"[fail] {record.slug}: {exc}")
            failed.append(record.slug)
        else:
            click.echo(f"[done] {record.slug}")
            succeeded.append(record.slug)

    _print_batch_summary(succeeded, failed)


# --------------------------------------------------------------------------- #
# cache
# --------------------------------------------------------------------------- #


@cli.group()
def cache() -> None:
    """Inspect and manage the pending-slugs cache."""


def _print_cache_table(entries: dict[str, dict[str, bool]]) -> None:
    header = f"{'SLUG':<45}{'METADATA':^12}{'IMAGES':^12}{'SUBMISSION':^12}"
    click.echo(header)
    click.echo("-" * len(header))
    for slug, parts in entries.items():
        row = f"{slug:<45}"
        for key in ("question", "images", "submission"):
            row += f"{'yes' if parts.get(key, False) else '-':^12}"
        click.echo(row)


@cache.command("list")
def cache_list() -> None:
    """List every slug with at least one part still pending."""
    entries = _manager().storage.read_pending_cache()
    if not entries:
        click.echo("Cache is empty — nothing pending.")
        return
    _print_cache_table(entries)


@cache.command("show")
@click.argument("slug")
def cache_show(slug: str) -> None:
    """Show cache progress for one slug."""
    entry = _manager().storage.read_pending_cache().get(slug)
    if entry is None:
        raise click.ClickException(f"'{slug}' is not in the pending cache (fully done, or never tracked).")
    _print_cache_table({slug: entry})


@cache.command("clear")
@click.argument("slug")
def cache_clear(slug: str) -> None:
    """Manually drop a slug from the pending cache."""
    if _manager().storage.remove_from_cache(slug):
        click.echo(f"Removed '{slug}' from the pending cache.")
    else:
        click.echo(f"'{slug}' was not in the pending cache.")


# --------------------------------------------------------------------------- #
# db
# --------------------------------------------------------------------------- #


@cli.group()
def db() -> None:
    """Inspect and manage the stored question database."""


@db.command("list")
def db_list() -> None:
    """List every stored question, summarized."""
    records = _manager().storage.list_all()
    if not records:
        click.echo("Database is empty.")
        return

    header = f"{'ID':<6}{'DIFFICULTY':<12}{'SLUG':<45}TITLE"
    click.echo(header)
    click.echo("-" * len(header))
    for record in sorted(records, key=lambda r: (r.id is None, r.id or 0)):
        click.echo(
            f"{record.id or '-':<6}{record.difficulty or '-':<12}{record.slug or '-':<45}{record.title or '-'}"
        )


@db.command("show")
@click.argument("slug")
def db_show(slug: str) -> None:
    """Print the full stored record (problem + submission) for one slug, as JSON."""
    record = _manager().storage.get_combined_by_slug(slug)
    if record is None:
        raise click.ClickException(f"'{slug}' not found in the database.")
    click.echo(json.dumps(record.model_dump(mode="json"), indent=2, ensure_ascii=False))


@db.command("count")
def db_count() -> None:
    """Print the total number of stored questions."""
    click.echo(str(_manager().storage.count()))


@db.command("delete")
@click.argument("slug")
@click.option("--force", is_flag=True, help="Skip the confirmation prompt.")
def db_delete(slug: str, force: bool) -> None:
    """Delete a stored question record (problem + submission). Destructive — asks to confirm unless --force."""
    if not force:
        click.confirm(f"Delete '{slug}' from the database? This cannot be undone.", abort=True)
    mgr = _manager()
    problem_deleted = mgr.storage.problems_delete(slug)
    mgr.storage.submissions_delete(slug)
    if not problem_deleted:
        raise click.ClickException(f"'{slug}' not found in the database.")
    click.echo(f"Deleted '{slug}'.")


if __name__ == "__main__":
    cli()
