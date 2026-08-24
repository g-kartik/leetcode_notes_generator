import json

import structlog

from modules.leetcode.models import ProblemRecord
from modules.leetcode.settings import leetcode_settings

logger = structlog.get_logger(__name__)


class ProblemStorage:
    """JSON-backed CRUD for ProblemRecord data (problems.json).

    Community/public problem data only — never touches submission data, so
    this file is always safe to share or export as-is.
    """

    def __init__(self):
        self.db_path = leetcode_settings.DSA_PROBLEMS_JSON_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_db_exists()

    def _ensure_db_exists(self) -> None:
        """Initializes an empty JSON structure if the file doesn't exist."""
        if not self.db_path.exists():
            logger.info("problems_db_initialized", path=str(self.db_path))
            self._save_raw({"problems": {}})

    def _load_raw(self) -> dict:
        """Reads raw JSON from disk."""
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as exc:
            logger.warning("problems_db_load_failed_using_empty", path=str(self.db_path), error=str(exc))
            return {"problems": {}}

    def _save_raw(self, data: dict) -> None:
        """Atomic write: writes to a temporary file first, then replaces target file."""
        temp_path = self.db_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_path.replace(self.db_path)

    # -------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------

    def add_or_update(self, record: ProblemRecord | dict) -> ProblemRecord:
        """Inserts or updates a problem using the slug as the key."""
        if isinstance(record, dict):
            record = ProblemRecord(**record)

        log = logger.bind(slug=record.slug)
        data = self._load_raw()
        data["problems"][record.slug] = record.model_dump(mode="json")
        self._save_raw(data)
        log.info("problem_record_saved", question_id=record.id, title=record.title)
        return record

    def bulk_add_or_update(self, records: list[ProblemRecord | dict]) -> int:
        """Batch inserts multiple problems using slug as keys in a single disk I/O."""
        data = self._load_raw()
        count = 0
        for item in records:
            record = item if isinstance(item, ProblemRecord) else ProblemRecord(**item)
            data["problems"][record.slug] = record.model_dump(mode="json")
            count += 1
        self._save_raw(data)
        logger.info("problems_bulk_saved", count=count)
        return count

    def get_by_slug(self, slug: str) -> ProblemRecord | None:
        """Fetches a single problem record by slug ($O(1)$ lookup)."""
        log = logger.bind(slug=slug)
        data = self._load_raw()
        raw_record = data["problems"].get(slug)
        if raw_record is None:
            log.info("problem_record_not_found")
            return None
        log.info("problem_record_found", question_id=raw_record.get("id"))
        return ProblemRecord(**raw_record)

    def get_by_id(self, question_id: int) -> ProblemRecord | None:
        """Secondary lookup: fetches a problem record by frontend question ID."""
        log = logger.bind(question_id=question_id)
        data = self._load_raw()
        for raw_record in data["problems"].values():
            if raw_record.get("id") == question_id:
                log.info("problem_record_found_by_id", slug=raw_record.get("slug"))
                return ProblemRecord(**raw_record)
        log.info("problem_record_not_found_by_id")
        return None

    def exists(self, identifier: str | int) -> bool:
        """Checks if a problem exists by slug (str) or question ID (int)."""
        if isinstance(identifier, str):
            data = self._load_raw()
            found = identifier in data["problems"]
            logger.bind(slug=identifier).info("problem_exists_check", exists=found)
            return found
        return self.get_by_id(identifier) is not None

    def delete(self, identifier: str | int) -> bool:
        """Deletes a record by slug (str) or question ID (int). Returns True if deleted."""
        log = logger.bind(identifier=identifier)
        data = self._load_raw()
        target_slug = None

        if isinstance(identifier, str):
            target_slug = identifier
        else:
            # Locate slug matching the numeric question ID
            for slug, p_data in data["problems"].items():
                if p_data.get("id") == identifier:
                    target_slug = slug
                    break

        if target_slug and target_slug in data["problems"]:
            del data["problems"][target_slug]
            self._save_raw(data)
            log.info("problem_record_deleted", slug=target_slug)
            return True

        log.info("problem_record_delete_skipped", reason="not_found")
        return False

    def list_all(self) -> list[ProblemRecord]:
        """Returns all stored problem records."""
        data = self._load_raw()
        records = [ProblemRecord(**raw) for raw in data["problems"].values()]
        logger.info("problems_listed", count=len(records))
        return records

    def count(self) -> int:
        """Returns total number of stored problems."""
        data = self._load_raw()
        total = len(data["problems"])
        logger.info("problems_counted", count=total)
        return total
