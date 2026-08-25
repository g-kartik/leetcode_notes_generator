"""`recent` command group: LeetCode's recent-accepted-submissions feed.

Separate from `sync`/`populate` (which drive the full solved-slugs pending
cache): this surfaces what was *just* accepted, with a timestamp — good for
a "what did I solve today" report, and for noticing an already-synced
problem now has a fresher accepted submission than what's stored.

Like every other command here, these two are standalone: `recent sync` only
updates the pending cache, it never fetches problem/image/submission data
itself. Follow it up with `populate submission --all` (or a specific slug)
to actually pull anything it flagged.
"""

import click
import structlog

from .common import get_manager
from .root import cli

logger = structlog.get_logger(__name__)


@cli.group()
def recent() -> None:
    """Inspect and sync against LeetCode's recent-accepted-submissions feed."""


def _fetch_options(f):
    f = click.option(
        "--limit", type=int, default=20, show_default=True,
        help="How many recent accepted submissions to fetch from LeetCode.",
    )(f)
    f = click.option(
        "--today/--all-time", "today_only", default=True, show_default=True,
        help="Restrict to submissions accepted today (local time), or show the raw feed.",
    )(f)
    return f


def _print_submissions_table(submissions: list[dict]) -> None:
    if not submissions:
        click.echo("Nothing to show.")
        return
    header = f"{'SLUG':<45}{'TITLE':<40}{'ACCEPTED AT'}"
    click.echo(header)
    click.echo("-" * len(header))
    for item in submissions:
        timestamp = item["timestamp"].isoformat(timespec="seconds") if item["timestamp"] else "-"
        click.echo(f"{item['slug']:<45}{item['title']:<40}{timestamp}")


def _print_slug_list(label: str, slugs: list[str]) -> None:
    if not slugs:
        return
    click.echo(f"\n{label}:")
    for slug in slugs:
        click.echo(f"  - {slug}")


@recent.command("list")
@_fetch_options
def recent_list(limit: int, today_only: bool) -> None:
    """Report recently-accepted submissions. Read-only — touches no stored state."""
    log = logger.bind(stage="recent")
    log.info("recent_list_command_started", limit=limit, today_only=today_only)

    submissions = get_manager().list_recent_accepted(limit=limit, today_only=today_only)
    _print_submissions_table(submissions)

    log.info("recent_list_command_completed", submission_count=len(submissions))


@recent.command("sync")
@_fetch_options
def recent_sync(limit: int, today_only: bool) -> None:
    """
    Classify recently-accepted submissions against stored data and update the
    pending cache accordingly. Does not fetch any problem/image/submission
    data itself — follow up with `populate submission --all` for that.
    """
    log = logger.bind(stage="recent_sync")
    log.info("recent_sync_command_started", limit=limit, today_only=today_only)

    result = get_manager().sync_recent_accepted(limit=limit, today_only=today_only)

    click.echo(f"{len(result['solved'])} recent accepted submission(s) checked.")
    click.echo(f"  {len(result['new_slugs'])} new (queued for a full populate)")
    click.echo(f"  {len(result['stale_submission_slugs'])} stale submission(s) reopened for refetch")
    click.echo(f"  {len(result['up_to_date_slugs'])} already up to date")

    _print_slug_list("New", result["new_slugs"])
    _print_slug_list("Stale submission", result["stale_submission_slugs"])

    log.info(
        "recent_sync_command_completed",
        new_count=len(result["new_slugs"]),
        stale_count=len(result["stale_submission_slugs"]),
        up_to_date_count=len(result["up_to_date_slugs"]),
    )
