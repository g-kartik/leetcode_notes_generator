import sqlite3

import structlog

from modules.leetcode.models import SubmissionRecord

from .db import get_connection

logger = structlog.get_logger(__name__)


class SubmissionStorage:
    """SQLite-backed CRUD for SubmissionRecord data (the `submissions` table in leetcode.db).

    Personal solution data only (language, code, submission date) — kept in
    its own table, deliberately without a foreign key to `problems` (see
    db.py), and never exported.
    """

    def __init__(self, conn: sqlite3.Connection | None = None):
        self.conn = conn or get_connection()

    def _upsert_one(self, record: SubmissionRecord) -> None:
        self.conn.execute(
            "INSERT INTO submissions (slug, lang, code, submission_date) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(slug) DO UPDATE SET "
            "lang = excluded.lang, code = excluded.code, submission_date = excluded.submission_date",
            (record.slug, record.lang, record.code, record.submission_date.isoformat()),
        )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> SubmissionRecord:
        return SubmissionRecord(
            slug=row["slug"],
            lang=row["lang"],
            code=row["code"],
            submission_date=row["submission_date"],
        )

    # -------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------

    def add_or_update(self, record: SubmissionRecord | dict) -> SubmissionRecord:
        """Inserts or updates a submission using the slug as the key."""
        if isinstance(record, dict):
            record = SubmissionRecord(**record)
        if not record.slug:
            raise ValueError("submission record must have a slug")

        log = logger.bind(slug=record.slug)
        with self.conn:
            self._upsert_one(record)
        log.info("submission_record_saved", lang=record.lang)
        return record

    def bulk_add_or_update(self, records: list[SubmissionRecord | dict]) -> int:
        """Batch inserts multiple submissions using slug as keys in a single transaction."""
        count = 0
        with self.conn:
            for item in records:
                record = (
                    item
                    if isinstance(item, SubmissionRecord)
                    else SubmissionRecord(**item)
                )
                if not record.slug:
                    raise ValueError("submission record must have a slug")
                self._upsert_one(record)
                count += 1
        logger.info("submissions_bulk_saved", count=count)
        return count

    def get_by_slug(self, slug: str) -> SubmissionRecord | None:
        """Fetches a single submission record by slug."""
        log = logger.bind(slug=slug)
        row = self.conn.execute(
            "SELECT * FROM submissions WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            log.info("submission_record_not_found")
            return None
        log.info("submission_record_found", lang=row["lang"])
        return self._row_to_record(row)

    def exists(self, slug: str) -> bool:
        """Checks if a submission exists for `slug`."""
        found = (
            self.conn.execute(
                "SELECT 1 FROM submissions WHERE slug = ?", (slug,)
            ).fetchone()
            is not None
        )
        logger.bind(slug=slug).info("submission_exists_check", exists=found)
        return found

    def delete(self, slug: str) -> bool:
        """Deletes a submission record by slug. Returns True if deleted."""
        log = logger.bind(slug=slug)
        with self.conn:
            cursor = self.conn.execute(
                "DELETE FROM submissions WHERE slug = ?", (slug,)
            )
        if cursor.rowcount:
            log.info("submission_record_deleted")
            return True
        log.info("submission_record_delete_skipped", reason="not_found")
        return False

    def list_all(self) -> list[SubmissionRecord]:
        """Returns all stored submission records."""
        rows = self.conn.execute("SELECT * FROM submissions").fetchall()
        records = [self._row_to_record(row) for row in rows]
        logger.info("submissions_listed", count=len(records))
        return records

    def count(self) -> int:
        """Returns total number of stored submissions."""
        total = self.conn.execute("SELECT COUNT(*) AS c FROM submissions").fetchone()[
            "c"
        ]
        logger.info("submissions_counted", count=total)
        return total
