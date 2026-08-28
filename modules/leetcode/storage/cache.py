import sqlite3

import structlog

from .db import get_connection

logger = structlog.get_logger(__name__)


class PendingCacheStore:
    """
    Solved-slugs pending cache (the `pending_cache` table in leetcode.db).

    Tracks solved slugs that still need one or more of:
      description / images / submission
    A slug's row is removed from the table automatically once all three
    parts are marked complete.
    """

    CACHE_PARTS = ("description", "images", "submission")

    def __init__(self, conn: sqlite3.Connection | None = None):
        self.conn = conn or get_connection()

    def _validate_part(self, part: str) -> None:
        if part not in self.CACHE_PARTS:
            raise ValueError(f"Unknown part '{part}'. Must be one of {self.CACHE_PARTS}.")

    @classmethod
    def _row_to_dict(cls, row: sqlite3.Row) -> dict:
        data = {part: bool(row[part]) for part in cls.CACHE_PARTS}
        data["id"] = row["id"]
        data["title"] = row["title"]
        data["difficulty"] = row["difficulty"]
        return data

    def read_pending_cache(self) -> dict[str, dict]:
        """Returns the full pending cache: {slug: {description, images,
        submission, id, title, difficulty}}. id/title/difficulty are
        whatever was captured the last time a live sync saw this slug (see
        refresh_pending_cache's `meta`) — None for a slug that's never been
        through a sync with this column present."""
        rows = self.conn.execute("SELECT * FROM pending_cache").fetchall()
        cache = {row["slug"]: self._row_to_dict(row) for row in rows}
        logger.info("pending_cache_read", pending_count=len(cache))
        return cache

    def get_pending_slugs(self) -> list[str]:
        """Returns slugs that still have at least one part outstanding."""
        rows = self.conn.execute("SELECT slug FROM pending_cache").fetchall()
        return [row["slug"] for row in rows]

    def refresh_pending_cache(
        self,
        slugs: list[str],
        initial_state: dict[str, dict[str, bool]] | None = None,
        meta: dict[str, dict] | None = None,
    ) -> dict[str, dict]:
        """
        Merges newly-fetched solved slugs into the cache. Slugs already
        tracked keep their existing per-part progress, but have their
        id/title/difficulty refreshed from `meta` whenever it's given —
        letting a row created before those columns existed (or with a
        network hiccup on some earlier sync) self-heal on the next live
        sync, instead of needing a one-off backfill.

        For a genuinely new slug, `initial_state` (if given) supplies its
        true per-part completion — e.g. reconstructed from existing
        problem/submission records, for a slug that was already synced
        before this cache existed or was reset — instead of assuming
        nothing has been fetched yet. A slug whose initial state already
        has every part complete is skipped entirely, matching
        `mark_part_fetched`'s drop-on-completion behavior.

        `meta` (if given) is {slug: {"id", "title", "difficulty"}} — cheaply
        available from the same bulk solved-questions fetch that produces
        `slugs`. Persisting it here (rather than just handing it back to the
        caller for one-time use) is what lets the CLI picker label a
        not-yet-fetched slug consistently even offline, from
        read_pending_cache() alone.
        """
        initial_state = initial_state or {}
        meta = meta or {}
        existing = {row["slug"] for row in self.conn.execute("SELECT slug FROM pending_cache").fetchall()}
        newly_added = 0
        skipped_already_complete = 0
        with self.conn:
            for slug in slugs:
                slug_meta = meta.get(slug) or {}
                if slug in existing:
                    if slug_meta:
                        self.conn.execute(
                            "UPDATE pending_cache SET id = ?, title = ?, difficulty = ? WHERE slug = ?",
                            (slug_meta.get("id"), slug_meta.get("title"), slug_meta.get("difficulty"), slug),
                        )
                    continue
                state = initial_state.get(slug)
                if state and all(state.get(part, False) for part in self.CACHE_PARTS):
                    skipped_already_complete += 1
                    continue
                values = {part: bool(state.get(part, False)) if state else False for part in self.CACHE_PARTS}
                self.conn.execute(
                    "INSERT INTO pending_cache "
                    "(slug, id, title, difficulty, description, images, submission) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        slug,
                        slug_meta.get("id"),
                        slug_meta.get("title"),
                        slug_meta.get("difficulty"),
                        values["description"],
                        values["images"],
                        values["submission"],
                    ),
                )
                existing.add(slug)
                newly_added += 1
        cache = self.read_pending_cache()
        logger.info(
            "pending_cache_refreshed",
            fetched_count=len(slugs),
            newly_added_count=newly_added,
            skipped_already_complete_count=skipped_already_complete,
            total_tracked=len(cache),
        )
        return cache

    def is_part_pending(self, slug: str, part: str) -> bool:
        """True if `part` for `slug` is still outstanding in the cache."""
        self._validate_part(part)
        # `part` is safe to interpolate into SQL here: _validate_part already
        # checked it against the fixed CACHE_PARTS whitelist above.
        row = self.conn.execute(f"SELECT {part} FROM pending_cache WHERE slug = ?", (slug,)).fetchone()
        pending = row is not None and not bool(row[part])
        logger.bind(slug=slug, part=part).info("pending_cache_part_checked", pending=pending)
        return pending

    def mark_part_fetched(self, slug: str, part: str) -> None:
        """
        Marks `part` ('description' | 'images' | 'submission') as fetched for `slug`.
        If all three parts are now True, the slug's row is deleted entirely.
        No-op if the slug isn't currently tracked in the cache.
        """
        self._validate_part(part)
        log = logger.bind(slug=slug, part=part)
        with self.conn:
            row = self.conn.execute("SELECT * FROM pending_cache WHERE slug = ?", (slug,)).fetchone()
            if row is None:
                log.info("pending_cache_mark_skipped", reason="slug_not_tracked")
                return

            self.conn.execute(f"UPDATE pending_cache SET {part} = 1 WHERE slug = ?", (slug,))
            updated = self.conn.execute("SELECT * FROM pending_cache WHERE slug = ?", (slug,)).fetchone()
            if all(updated[p] for p in self.CACHE_PARTS):
                self.conn.execute("DELETE FROM pending_cache WHERE slug = ?", (slug,))
                log.info("pending_cache_slug_completed", reason="all_parts_fetched")
            else:
                remaining = [p for p in self.CACHE_PARTS if not updated[p]]
                log.info("pending_cache_part_marked_fetched", remaining_parts=remaining)

    def reopen_part(self, slug: str, part: str) -> None:
        """
        Marks `part` as pending again for `slug`, re-inserting the slug's row
        if it had already been dropped (i.e. was previously 3/3 complete).
        The other parts are assumed still done — this is meant for reopening
        a single part that new information (e.g. a fresher accepted
        submission) shows is now stale, not for re-tracking a slug from
        scratch.
        """
        self._validate_part(part)
        log = logger.bind(slug=slug, part=part)
        with self.conn:
            row = self.conn.execute("SELECT * FROM pending_cache WHERE slug = ?", (slug,)).fetchone()
            if row is None:
                values = {p: (p != part) for p in self.CACHE_PARTS}
                self.conn.execute(
                    "INSERT INTO pending_cache (slug, description, images, submission) VALUES (?, ?, ?, ?)",
                    (slug, values["description"], values["images"], values["submission"]),
                )
            else:
                self.conn.execute(f"UPDATE pending_cache SET {part} = 0 WHERE slug = ?", (slug,))
        log.info("pending_cache_part_reopened")

    def remove_from_cache(self, slug: str) -> bool:
        """Manually drops a slug's row from the pending cache. Returns True if it was present."""
        log = logger.bind(slug=slug)
        with self.conn:
            cursor = self.conn.execute("DELETE FROM pending_cache WHERE slug = ?", (slug,))
        if cursor.rowcount:
            log.info("pending_cache_entry_removed")
            return True
        log.info("pending_cache_entry_remove_skipped", reason="not_found")
        return False
