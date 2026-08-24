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
            self._save_raw({"submissions": {}})

    def _load_raw(self) -> dict:
        """Reads raw JSON from disk."""
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError, FileNotFoundError:
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

        data = self._load_raw()
        data["submissions"][record.slug] = record.model_dump(mode="json")
        self._save_raw(data)
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
        return count

    def get_by_slug(self, slug: str) -> SubmissionRecord | None:
        """Fetches a single submission record by slug ($O(1)$ lookup)."""
        data = self._load_raw()
        raw_record = data["submissions"].get(slug)
        return SubmissionRecord(**raw_record) if raw_record else None

    def exists(self, slug: str) -> bool:
        """Checks if a submission exists for `slug`."""
        data = self._load_raw()
        return slug in data["submissions"]

    def delete(self, slug: str) -> bool:
        """Deletes a submission record by slug. Returns True if deleted."""
        data = self._load_raw()
        if slug in data["submissions"]:
            del data["submissions"][slug]
            self._save_raw(data)
            return True
        return False

    def list_all(self) -> list[SubmissionRecord]:
        """Returns all stored submission records."""
        data = self._load_raw()
        return [SubmissionRecord(**raw) for raw in data["submissions"].values()]

    def count(self) -> int:
        """Returns total number of stored submissions."""
        data = self._load_raw()
        return len(data["submissions"])
