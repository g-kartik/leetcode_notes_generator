"""`db` command group: inspect and manage the stored question database."""

import json

import click
import structlog

from .common import get_manager
from .root import cli

logger = structlog.get_logger(__name__)


@cli.group()
def db() -> None:
    """Inspect and manage the stored question database."""


@db.command("list")
def db_list() -> None:
    """List every stored question, summarized."""
    logger.bind(stage="db").info("db_list_command_started")
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


@db.command("show")
@click.argument("slug")
def db_show(slug: str) -> None:
    """Print the full stored record (problem + submission) for one slug, as JSON."""
    with structlog.contextvars.bound_contextvars(slug=slug, stage="db"):
        logger.info("db_show_command_started")
        record = get_manager().storage.get_combined_by_slug(slug)
        if record is None:
            logger.info("db_show_command_skipped", reason="not_found")
            raise click.ClickException(f"'{slug}' not found in the database.")
        click.echo(json.dumps(record.model_dump(mode="json"), indent=2, ensure_ascii=False))


@db.command("count")
def db_count() -> None:
    """Print the total number of stored questions."""
    logger.bind(stage="db").info("db_count_command_started")
    click.echo(str(get_manager().storage.count()))


@db.command("delete")
@click.argument("slug")
@click.option("--force", is_flag=True, help="Skip the confirmation prompt.")
def db_delete(slug: str, force: bool) -> None:
    """Delete a stored question record (problem + submission). Destructive — asks to confirm unless --force."""
    with structlog.contextvars.bound_contextvars(slug=slug, stage="db"):
        logger.info("db_delete_command_started", force=force)
        if not force:
            click.confirm(f"Delete '{slug}' from the database? This cannot be undone.", abort=True)
        mgr = get_manager()
        problem_deleted = mgr.storage.problems_delete(slug)
        mgr.storage.submissions_delete(slug)
        if not problem_deleted:
            logger.info("db_delete_command_skipped", reason="not_found")
            raise click.ClickException(f"'{slug}' not found in the database.")
        click.echo(f"Deleted '{slug}'.")
