"""`problems recent`: report LeetCode's recent-accepted-submissions feed.

Read-only — this only surfaces what LeetCode says was just accepted, with a
timestamp. It never touches the pending cache; that reconciliation lives in
`problems data pending sync`, which fetches the same feed but always
considers the full batch (see LeetCodeSyncManager.reconcile_recent_accepted).
"""

import click
import structlog

from .common import get_manager
from .problems import problems

logger = structlog.get_logger(__name__)


@problems.command("recent")
@click.option(
    "--today", "today_only", is_flag=True, default=False,
    help="Restrict to submissions accepted today (local time). Shows the full "
    "recent-accepted batch by default.",
)
@click.option(
    "--limit", type=int, default=20, show_default=True,
    help="How many recent accepted submissions to fetch from LeetCode.",
)
def problems_recent(today_only: bool, limit: int) -> None:
    """Report recently-accepted submissions. Read-only — touches no stored state."""
    log = logger.bind(stage="recent")
    log.info("recent_command_started", limit=limit, today_only=today_only)

    submissions = get_manager().list_recent_accepted(limit=limit, today_only=today_only)

    if not submissions:
        click.echo("Nothing to show.")
        return
    header = f"{'SLUG':<45}{'TITLE':<40}{'ACCEPTED AT'}"
    click.echo(header)
    click.echo("-" * len(header))
    for item in submissions:
        timestamp = item["timestamp"].isoformat(timespec="seconds") if item["timestamp"] else "-"
        click.echo(f"{item['slug']:<45}{item['title']:<40}{timestamp}")

    log.info("recent_command_completed", submission_count=len(submissions))
