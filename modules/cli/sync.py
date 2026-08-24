"""`sync` command: report slugs still pending metadata/images/submission."""

import click

from .common import get_manager
from .root import cli


@cli.command()
@click.option(
    "--refresh/--no-refresh", default=False,
    help="Hit the LeetCode API for the current solved list before reporting.",
)
def sync(refresh: bool) -> None:
    """Report slugs still pending metadata/images/submission."""
    mgr = get_manager()
    pending = mgr.sync_solved_questions_data_entry(force_refresh=refresh)

    click.echo(f"{len(pending)} slug(s) pending.")
    for slug in pending:
        click.echo(f"  - {slug}")
