"""`problems list/show/count/delete`: inspect and manage the stored question database."""

import json

import click
import structlog

from .common import get_manager, print_batch_summary
from .picker import label_records, pick_slugs
from .problems import problems

logger = structlog.get_logger(__name__)


@problems.command("list")
def problems_list() -> None:
    """List every stored question, summarized."""
    logger.bind(stage="problems").info("problems_list_command_started")
    records = get_manager().storage.list_all()
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


def _pick_stored_slugs(mgr) -> list[str]:
    """Interactive multi-select fallback over every stored slug."""
    records = mgr.storage.list_all()
    if not records:
        click.echo("Nothing to pick from — database is empty.")
        return []
    picked = pick_slugs(label_records(records))
    if not picked:
        click.echo("Nothing selected.")
    return picked


def _show_one(mgr, slug: str) -> None:
    with structlog.contextvars.bound_contextvars(slug=slug, stage="problems"):
        logger.info("problems_show_command_started")
        record = mgr.storage.get_combined_by_slug(slug)
        if record is None:
            logger.info("problems_show_command_skipped", reason="not_found")
            raise click.ClickException(f"'{slug}' not found in the database.")
        click.echo(
            json.dumps(record.model_dump(mode="json"), indent=2, ensure_ascii=False)
        )


@problems.command("show")
@click.argument("slug", required=False)
def problems_show(slug: str | None) -> None:
    """Print the full stored record (problem + submission) for one or more
    slugs, as JSON. Omit SLUG to pick interactively instead — a searchable,
    multi-select prompt over every stored slug."""
    mgr = get_manager()

    if slug:
        _show_one(mgr, slug)
        return

    slugs = _pick_stored_slugs(mgr)
    if not slugs:
        return
    for idx, target_slug in enumerate(slugs):
        if idx:
            click.echo()
        try:
            _show_one(mgr, target_slug)
        except click.ClickException as exc:
            click.echo(f"[fail] {exc}", err=True)


@problems.command("count")
def problems_count() -> None:
    """Print the total number of stored questions."""
    logger.bind(stage="problems").info("problems_count_command_started")
    click.echo(str(get_manager().storage.count()))


def _delete_one(mgr, slug: str) -> bool:
    with structlog.contextvars.bound_contextvars(slug=slug, stage="problems"):
        logger.info("problems_delete_command_started")
        problem_deleted = mgr.storage.problems_delete(slug)
        mgr.storage.submissions_delete(slug)
        if not problem_deleted:
            logger.info("problems_delete_command_skipped", reason="not_found")
            return False
        return True


@problems.command("delete")
@click.argument("slug", required=False)
@click.option("--skip-confirm", is_flag=True, help="Skip the confirmation prompt.")
def problems_delete(slug: str | None, skip_confirm: bool) -> None:
    """Delete one or more stored question records (problem + submission).
    Destructive — asks to confirm unless --skip-confirm. Omit SLUG to pick
    interactively instead — a searchable, multi-select prompt over every
    stored slug."""
    mgr = get_manager()

    if slug:
        if not skip_confirm:
            click.confirm(
                f"Delete '{slug}' from the database? This cannot be undone.", abort=True
            )
        if not _delete_one(mgr, slug):
            raise click.ClickException(f"'{slug}' not found in the database.")
        click.echo(f"Deleted '{slug}'.")
        return

    slugs = _pick_stored_slugs(mgr)
    if not slugs:
        return
    if not skip_confirm:
        click.echo(f"About to delete {len(slugs)} slug(s): {', '.join(slugs)}")
        click.confirm("This cannot be undone. Continue?", abort=True)

    succeeded, failed = [], []
    for target_slug in slugs:
        if _delete_one(mgr, target_slug):
            click.echo(f"[done] deleted {target_slug}")
            succeeded.append(target_slug)
        else:
            click.echo(f"[fail] {target_slug}: not found")
            failed.append(target_slug)
    print_batch_summary(succeeded, failed)
