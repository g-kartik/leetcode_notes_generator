import json

import structlog

from modules.leetcode.models import QuestionRecord
from modules.leetcode.settings import leetcode_settings

logger = structlog.get_logger(__name__)


class LeetCodeDSAStorage:
    CACHE_PARTS = ("question", "images", "submission")

    def __init__(self):
        self.db_path = leetcode_settings.DSA_PROBLEMS_JSON_DB
        self.cache_path = leetcode_settings.DSA_PROBLEMS_CACHE_JSON_DB
        self._ensure_db_exists()
        self._ensure_cache_exists()

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

    # -------------------------------------------------------------------
    # Solved-slugs pending cache
    #
    # Tracks solved slugs that still need one or more of:
    #   metadata / images / submission
    # A slug is removed from the cache automatically once all three parts
    # are marked complete.
    # -------------------------------------------------------------------

    def _ensure_cache_exists(self) -> None:
        if not self.cache_path.exists():
            self._save_cache({})

    def _load_cache(self) -> dict:
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError, FileNotFoundError:
            return {}

    def _save_cache(self, data: dict) -> None:
        """Atomic write for the cache file, same pattern as _save_raw."""
        temp_path = self.cache_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_path.replace(self.cache_path)

    def read_pending_cache(self) -> dict[str, dict[str, bool]]:
        """Returns the full pending cache: {slug: {question, images, submission}}."""
        return self._load_cache()

    def get_pending_slugs(self) -> list[str]:
        """Returns slugs that still have at least one part outstanding."""
        return list(self._load_cache().keys())

    def refresh_pending_cache(self, slugs: list[str]) -> dict[str, dict[str, bool]]:
        """
        Merges newly-fetched solved slugs into the cache. Slugs already
        tracked keep their existing per-part progress; only genuinely new
        slugs are added, with all parts set to False.
        """
        cache = self._load_cache()
        for slug in slugs:
            if slug not in cache:
                cache[slug] = {part: False for part in self.CACHE_PARTS}
        self._save_cache(cache)
        return cache

    def is_part_pending(self, slug: str, part: str) -> bool:
        """True if `part` for `slug` is still outstanding in the cache."""
        if part not in self.CACHE_PARTS:
            raise ValueError(
                f"Unknown part '{part}'. Must be one of {self.CACHE_PARTS}."
            )
        cache = self._load_cache()
        entry = cache.get(slug)
        return bool(entry) and not entry.get(part, False)

    def mark_part_fetched(self, slug: str, part: str) -> None:
        """
        Marks `part` ('question' | 'images' | 'submission') as fetched for `slug`.
        If all three parts are now True, the slug is removed from the cache entirely.
        No-op if the slug isn't currently tracked in the cache.
        """
        if part not in self.CACHE_PARTS:
            raise ValueError(
                f"Unknown part '{part}'. Must be one of {self.CACHE_PARTS}."
            )

        cache = self._load_cache()
        if slug not in cache:
            return

        cache[slug][part] = True
        if all(cache[slug].values()):
            del cache[slug]

        self._save_cache(cache)

    def remove_from_cache(self, slug: str) -> bool:
        """Manually drops a slug from the pending cache. Returns True if it was present."""
        cache = self._load_cache()
        if slug in cache:
            del cache[slug]
            self._save_cache(cache)
            return True
        return False
