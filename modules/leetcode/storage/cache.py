import json

from modules.leetcode.settings import leetcode_settings


class PendingCacheStore:
    """
    Solved-slugs pending cache.

    Tracks solved slugs that still need one or more of:
      metadata / images / submission
    A slug is removed from the cache automatically once all three parts
    are marked complete.
    """

    CACHE_PARTS = ("question", "images", "submission")

    def __init__(self):
        self.cache_path = leetcode_settings.DSA_PROBLEMS_CACHE_JSON_DB
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_cache_exists()

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
        """Atomic write for the cache file, same pattern as the JSON stores."""
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
