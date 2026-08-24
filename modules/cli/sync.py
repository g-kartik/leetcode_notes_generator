"""`sync` command: report slugs still pending problem/images/submission."""

import click
import structlog

from .common import get_manager
from .root import cli

logger = structlog.get_logger(__name__)


@cli.command()
@click.option(
    "--refresh/--no-refresh", default=False,
    help="Hit the LeetCode API for the current solved list before reporting.",
)
def sync(refresh: bool) -> None:
    """Report slugs still pending problem/images/submission."""
    log = logger.bind(stage="sync")
    log.info("sync_command_started", refresh=refresh)

    mgr = get_manager()
    pending = mgr.sync_solved_questions_data_entry(force_refresh=refresh)

    click.echo(f"{len(pending)} slug(s) pending.")
    for slug in pending:
        click.echo(f"  - {slug}")

    log.info("sync_command_completed", pending_count=len(pending))
