import json

from modules.leetcode.models import QuestionRecord
from modules.leetcode.settings import leetcode_settings


class LeetCodeDSAStorage:
    def __init__(self):
        self.db_path = leetcode_settings.DSA_PROBLEMS_JSON
        self._ensure_db_exists()

    def _ensure_db_exists(self) -> None:
        """Initializes an empty JSON structure if the file doesn't exist."""
        if not self.db_path.exists():
            self._save_raw({"questions": {}})

    def _load_raw(self) -> dict:
        """Reads raw JSON from disk."""
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError, FileNotFoundError:
            return {"questions": {}}

    def _save_raw(self, data: dict) -> None:
        """Atomic write: writes to a temporary file first, then replaces target file."""
        temp_path = self.db_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_path.replace(self.db_path)

    # -------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------

    def add_or_update(self, record: QuestionRecord | dict) -> QuestionRecord:
        """Inserts or updates a question using the slug as the key."""
        if isinstance(record, dict):
            record = QuestionRecord(**record)

        data = self._load_raw()
        data["questions"][record.slug] = record.model_dump(mode="json")
        self._save_raw(data)
        return record

    def bulk_add_or_update(self, records: list[QuestionRecord | dict]) -> int:
        """Batch inserts multiple questions using slug as keys in a single disk I/O."""
        data = self._load_raw()
        count = 0
        for item in records:
            record = (
                item if isinstance(item, QuestionRecord) else QuestionRecord(**item)
            )
            data["questions"][record.slug] = record.model_dump(mode="json")
            count += 1
        self._save_raw(data)
        return count

    def get_by_slug(self, slug: str) -> QuestionRecord | None:
        """Fetches a single question record by slug ($O(1)$ lookup)."""
        data = self._load_raw()
        raw_record = data["questions"].get(slug)
        return QuestionRecord(**raw_record) if raw_record else None

    def get_by_id(self, question_id: int) -> QuestionRecord | None:
        """Secondary lookup: fetches a question record by frontend question ID."""
        data = self._load_raw()
        for raw_record in data["questions"].values():
            if raw_record.get("id") == question_id:
                return QuestionRecord(**raw_record)
        return None

    def exists(self, identifier: str | int) -> bool:
        """Checks if a question exists by slug (str) or question ID (int)."""
        if isinstance(identifier, str):
            data = self._load_raw()
            return identifier in data["questions"]
        return self.get_by_id(identifier) is not None

    def delete(self, identifier: str | int) -> bool:
        """Deletes a record by slug (str) or question ID (int). Returns True if deleted."""
        data = self._load_raw()
        target_slug = None

        if isinstance(identifier, str):
            target_slug = identifier
        else:
            # Locate slug matching the numeric question ID
            for slug, q_data in data["questions"].items():
                if q_data.get("id") == identifier:
                    target_slug = slug
                    break

        if target_slug and target_slug in data["questions"]:
            del data["questions"][target_slug]
            self._save_raw(data)
            return True

        return False

    def list_all(self) -> list[QuestionRecord]:
        """Returns all stored question records."""
        data = self._load_raw()
        return [QuestionRecord(**raw) for raw in data["questions"].values()]

    def count(self) -> int:
        """Returns total number of stored questions."""
        data = self._load_raw()
        return len(data["questions"])
