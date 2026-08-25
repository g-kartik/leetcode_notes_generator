import json

import structlog

from modules.leetcode.settings import leetcode_settings

logger = structlog.get_logger(__name__)


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
            logger.info("pending_cache_initialized", path=str(self.cache_path))
            self._save_cache({})

    def _load_cache(self) -> dict:
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as exc:
            logger.warning("pending_cache_load_failed_using_empty", path=str(self.cache_path), error=str(exc))
            return {}

    def _save_cache(self, data: dict) -> None:
        """Atomic write for the cache file, same pattern as the JSON stores."""
        temp_path = self.cache_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_path.replace(self.cache_path)

    def read_pending_cache(self) -> dict[str, dict[str, bool]]:
        """Returns the full pending cache: {slug: {question, images, submission}}."""
        cache = self._load_cache()
        logger.info("pending_cache_read", pending_count=len(cache))
        return cache

    def get_pending_slugs(self) -> list[str]:
        """Returns slugs that still have at least one part outstanding."""
        return list(self._load_cache().keys())

    def refresh_pending_cache(
        self,
        slugs: list[str],
        initial_state: dict[str, dict[str, bool]] | None = None,
    ) -> dict[str, dict[str, bool]]:
        """
        Merges newly-fetched solved slugs into the cache. Slugs already
        tracked keep their existing per-part progress.

        For a genuinely new slug, `initial_state` (if given) supplies its
        true per-part completion — e.g. reconstructed from existing
        problem/submission records, for a slug that was already synced
        before this cache existed or was reset — instead of assuming
        nothing has been fetched yet. A slug whose initial state already
        has every part complete is skipped entirely, matching
        `mark_part_fetched`'s drop-on-completion behavior.
        """
        cache = self._load_cache()
        initial_state = initial_state or {}
        newly_added = 0
        skipped_already_complete = 0
        for slug in slugs:
            if slug in cache:
                continue
            state = initial_state.get(slug)
            if state and all(state.get(part, False) for part in self.CACHE_PARTS):
                skipped_already_complete += 1
                continue
            cache[slug] = {part: bool(state.get(part, False)) if state else False for part in self.CACHE_PARTS}
            newly_added += 1
        self._save_cache(cache)
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
        if part not in self.CACHE_PARTS:
            raise ValueError(
                f"Unknown part '{part}'. Must be one of {self.CACHE_PARTS}."
            )
        cache = self._load_cache()
        entry = cache.get(slug)
        pending = bool(entry) and not entry.get(part, False)
        logger.bind(slug=slug, part=part).info("pending_cache_part_checked", pending=pending)
        return pending

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

        log = logger.bind(slug=slug, part=part)
        cache = self._load_cache()
        if slug not in cache:
            log.info("pending_cache_mark_skipped", reason="slug_not_tracked")
            return

        cache[slug][part] = True
        if all(cache[slug].values()):
            del cache[slug]
            log.info("pending_cache_slug_completed", reason="all_parts_fetched")
        else:
            remaining = [p for p, done in cache[slug].items() if not done]
            log.info("pending_cache_part_marked_fetched", remaining_parts=remaining)

        self._save_cache(cache)

    def remove_from_cache(self, slug: str) -> bool:
        """Manually drops a slug from the pending cache. Returns True if it was present."""
        log = logger.bind(slug=slug)
        cache = self._load_cache()
        if slug in cache:
            del cache[slug]
            self._save_cache(cache)
            log.info("pending_cache_entry_removed")
            return True
        log.info("pending_cache_entry_remove_skipped", reason="not_found")
        return False
