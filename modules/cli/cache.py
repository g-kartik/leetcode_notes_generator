"""`cache` command group: inspect and manage the pending-slugs cache."""

import click
import structlog

from .common import get_manager
from .root import cli

logger = structlog.get_logger(__name__)


@cli.group()
def cache() -> None:
    """Inspect and manage the pending-slugs cache."""


def _print_cache_table(entries: dict[str, dict[str, bool]]) -> None:
    header = f"{'SLUG':<45}{'PROBLEM':^12}{'IMAGES':^12}{'SUBMISSION':^12}"
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
    logger.bind(stage="cache").info("cache_list_command_started")
    entries = get_manager().storage.read_pending_cache()
    if not entries:
        click.echo("Cache is empty — nothing pending.")
        return
    _print_cache_table(entries)


@cache.command("show")
@click.argument("slug")
def cache_show(slug: str) -> None:
    """Show cache progress for one slug."""
    with structlog.contextvars.bound_contextvars(slug=slug, stage="cache"):
        logger.info("cache_show_command_started")
        entry = get_manager().storage.read_pending_cache().get(slug)
        if entry is None:
            logger.info("cache_show_command_skipped", reason="slug_not_tracked")
            raise click.ClickException(f"'{slug}' is not in the pending cache (fully done, or never tracked).")
        _print_cache_table({slug: entry})


@cache.command("clear")
@click.argument("slug")
def cache_clear(slug: str) -> None:
    """Manually drop a slug from the pending cache."""
    with structlog.contextvars.bound_contextvars(slug=slug, stage="cache"):
        logger.info("cache_clear_command_started")
        if get_manager().storage.remove_from_cache(slug):
            click.echo(f"Removed '{slug}' from the pending cache.")
        else:
            click.echo(f"'{slug}' was not in the pending cache.")
