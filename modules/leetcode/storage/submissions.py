import json

import structlog

from modules.leetcode.models import SubmissionRecord
from modules.leetcode.settings import leetcode_settings

logger = structlog.get_logger(__name__)


class SubmissionStorage:
    """JSON-backed CRUD for SubmissionRecord data (submissions.json).

    Personal solution data only (language, code, submission date) — kept in
    its own file, separate from problems.json, and never exported.
    """

    def __init__(self):
        self.db_path = leetcode_settings.DSA_SUBMISSIONS_JSON_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_db_exists()

    def _ensure_db_exists(self) -> None:
        """Initializes an empty JSON structure if the file doesn't exist."""
        if not self.db_path.exists():
            logger.info("submissions_db_initialized", path=str(self.db_path))
            self._save_raw({"submissions": {}})

    def _load_raw(self) -> dict:
        """Reads raw JSON from disk."""
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as exc:
            logger.warning("submissions_db_load_failed_using_empty", path=str(self.db_path), error=str(exc))
            return {"submissions": {}}

    def _save_raw(self, data: dict) -> None:
        """Atomic write: writes to a temporary file first, then replaces target file."""
        temp_path = self.db_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_path.replace(self.db_path)

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
        data = self._load_raw()
        data["submissions"][record.slug] = record.model_dump(mode="json")
        self._save_raw(data)
        log.info("submission_record_saved", lang=record.lang)
        return record

    def bulk_add_or_update(self, records: list[SubmissionRecord | dict]) -> int:
        """Batch inserts multiple submissions using slug as keys in a single disk I/O."""
        data = self._load_raw()
        count = 0
        for item in records:
            record = (
                item if isinstance(item, SubmissionRecord) else SubmissionRecord(**item)
            )
            if not record.slug:
                raise ValueError("submission record must have a slug")
            data["submissions"][record.slug] = record.model_dump(mode="json")
            count += 1
        self._save_raw(data)
        logger.info("submissions_bulk_saved", count=count)
        return count

    def get_by_slug(self, slug: str) -> SubmissionRecord | None:
        """Fetches a single submission record by slug ($O(1)$ lookup)."""
        log = logger.bind(slug=slug)
        data = self._load_raw()
        raw_record = data["submissions"].get(slug)
        if raw_record is None:
            log.info("submission_record_not_found")
            return None
        log.info("submission_record_found", lang=raw_record.get("lang"))
        return SubmissionRecord(**raw_record)

    def exists(self, slug: str) -> bool:
        """Checks if a submission exists for `slug`."""
        data = self._load_raw()
        found = slug in data["submissions"]
        logger.bind(slug=slug).info("submission_exists_check", exists=found)
        return found

    def delete(self, slug: str) -> bool:
        """Deletes a submission record by slug. Returns True if deleted."""
        log = logger.bind(slug=slug)
        data = self._load_raw()
        if slug in data["submissions"]:
            del data["submissions"][slug]
            self._save_raw(data)
            log.info("submission_record_deleted")
            return True
        log.info("submission_record_delete_skipped", reason="not_found")
        return False

    def list_all(self) -> list[SubmissionRecord]:
        """Returns all stored submission records."""
        data = self._load_raw()
        records = [SubmissionRecord(**raw) for raw in data["submissions"].values()]
        logger.info("submissions_listed", count=len(records))
        return records

    def count(self) -> int:
        """Returns total number of stored submissions."""
        data = self._load_raw()
        total = len(data["submissions"])
        logger.info("submissions_counted", count=total)
        return total
