"""Pure helpers for working with the recentAcSubmissionList feed.

Kept separate from pipeline.py because these are plain data transforms —
no network or storage I/O — over the list of {slug, title, timestamp} dicts
produced by parsers.gql_recent_ac_submissions.
"""

from datetime import datetime

import structlog

logger = structlog.get_logger(__name__)


def filter_today(submissions: list[dict], now: datetime | None = None) -> list[dict]:
    """Keeps only entries accepted today, in local time.

    `now` is only for tests to pin "today" — real callers should omit it.
    """
    reference = (now or datetime.now()).astimezone()
    start_of_today = reference.replace(hour=0, minute=0, second=0, microsecond=0)

    today_only = [
        item for item in submissions
        if item.get("timestamp") is not None and item["timestamp"] >= start_of_today
    ]
    logger.info(
        "recent_submissions_filtered_to_today",
        kept_count=len(today_only),
        total_count=len(submissions),
    )
    return today_only


def dedupe_latest_per_slug(submissions: list[dict]) -> list[dict]:
    """Collapses repeated entries for the same slug (e.g. resubmits) down to
    the one with the latest timestamp."""
    latest_by_slug: dict[str, dict] = {}
    for item in submissions:
        slug = item.get("slug")
        if not slug:
            continue
        existing = latest_by_slug.get(slug)
        if existing is None or item["timestamp"] > existing["timestamp"]:
            latest_by_slug[slug] = item

    deduped = list(latest_by_slug.values())
    logger.info(
        "recent_submissions_deduped",
        kept_count=len(deduped),
        total_count=len(submissions),
    )
    return deduped
