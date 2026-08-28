import structlog

from modules.leetcode.models import ProblemRecord, SubmissionRecord

from .cache import PendingCacheStore
from .combined import CombinedQuestionRecord
from .db import get_connection
from .problems import ProblemStorage
from .submissions import SubmissionStorage

logger = structlog.get_logger(__name__)

__all__ = ["LeetCodeDSAStorage", "CombinedQuestionRecord"]


class LeetCodeDSAStorage:
    """
    Facade over the problem store, submission store, and pending-parts cache.

    All three share one leetcode.db SQLite connection (see db.py). Problem
    data (community/public, safe to export — the `problems`/`tags`/
    `problem_tags` tables) and submission data (personal, never exported —
    the `submissions` table) are still kept in separate tables by
    construction, same boundary as before, just tables instead of separate
    JSON files now. Each store's CRUD is exposed here under a `problems_*` /
    `submissions_*` prefix.

    A small set of unprefixed methods is kept for backward compatibility
    with existing callers and operates on the problems store only. Callers
    that need both problem and submission data together should use
    `get_combined_by_slug` / `list_all_combined` — the only place the two
    stores are joined back into one view.
    """

    CACHE_PARTS = PendingCacheStore.CACHE_PARTS

    def __init__(self):
        self.conn = get_connection()
        self.problems = ProblemStorage(self.conn)
        self.submissions = SubmissionStorage(self.conn)
        self.cache = PendingCacheStore(self.conn)

    # -------------------------------------------------------------------
    # Combined view (the only place problems + submissions are joined)
    # -------------------------------------------------------------------

    def get_combined_by_slug(self, slug: str) -> CombinedQuestionRecord | None:
        """Returns `slug`'s problem data merged with its submission data, or None if the problem doesn't exist."""
        log = logger.bind(slug=slug)
        problem = self.problems.get_by_slug(slug)
        if problem is None:
            log.info("combined_record_skipped", reason="problem_record_missing")
            return None
        submission = self.submissions.get_by_slug(slug)
        log.info("combined_record_built", has_submission=submission is not None)
        return CombinedQuestionRecord.from_parts(problem, submission)

    def list_all_combined(self) -> list[CombinedQuestionRecord]:
        """Returns every stored problem, each merged with its submission data if any exists."""
        combined = [
            CombinedQuestionRecord.from_parts(p, self.submissions.get_by_slug(p.slug))
            for p in self.problems.list_all()
        ]
        logger.info("combined_records_listed", count=len(combined))
        return combined

    # -------------------------------------------------------------------
    # Backward-compatible unprefixed CRUD (problems store only)
    # -------------------------------------------------------------------

    def add_or_update(self, record: ProblemRecord | dict) -> ProblemRecord:
        """Inserts or updates a problem record. Alias for problems_add_or_update."""
        return self.problems.add_or_update(record)

    def bulk_add_or_update(self, records: list[ProblemRecord | dict]) -> int:
        """Batch inserts/updates problem records. Alias for problems_bulk_add_or_update."""
        return self.problems.bulk_add_or_update(records)

    def get_by_slug(self, slug: str) -> ProblemRecord | None:
        """Fetches a single problem record by slug. Alias for problems_get_by_slug."""
        return self.problems.get_by_slug(slug)

    def get_by_id(self, question_id: int) -> ProblemRecord | None:
        """Fetches a single problem record by frontend question ID. Alias for problems_get_by_id."""
        return self.problems.get_by_id(question_id)

    def exists(self, identifier: str | int) -> bool:
        """Checks if a problem exists by slug (str) or question ID (int). Alias for problems_exists."""
        return self.problems.exists(identifier)

    def delete(self, identifier: str | int) -> bool:
        """
        Deletes a problem record by slug (str) or question ID (int). Alias for
        problems_delete. Leaves that slug's submission data untouched — call
        submissions_delete separately to remove it too.
        """
        return self.problems.delete(identifier)

    def list_all(self) -> list[ProblemRecord]:
        """Returns all stored problem records. Alias for problems_list_all."""
        return self.problems.list_all()

    def count(self) -> int:
        """Returns total number of stored problems. Alias for problems_count."""
        return self.problems.count()

    # -------------------------------------------------------------------
    # Prefixed CRUD: problems
    # -------------------------------------------------------------------

    def problems_add_or_update(self, record: ProblemRecord | dict) -> ProblemRecord:
        """Inserts or updates a problem record using its slug as the key."""
        return self.problems.add_or_update(record)

    def problems_bulk_add_or_update(self, records: list[ProblemRecord | dict]) -> int:
        """Batch inserts/updates problem records in a single disk I/O."""
        return self.problems.bulk_add_or_update(records)

    def problems_get_by_slug(self, slug: str) -> ProblemRecord | None:
        """Fetches a single problem record by slug."""
        return self.problems.get_by_slug(slug)

    def problems_get_by_id(self, question_id: int) -> ProblemRecord | None:
        """Fetches a single problem record by frontend question ID."""
        return self.problems.get_by_id(question_id)

    def problems_exists(self, identifier: str | int) -> bool:
        """Checks if a problem exists by slug (str) or question ID (int)."""
        return self.problems.exists(identifier)

    def problems_delete(self, identifier: str | int) -> bool:
        """Deletes a problem record by slug (str) or question ID (int). Returns True if deleted."""
        return self.problems.delete(identifier)

    def problems_list_all(self) -> list[ProblemRecord]:
        """Returns all stored problem records."""
        return self.problems.list_all()

    def problems_count(self) -> int:
        """Returns total number of stored problems."""
        return self.problems.count()

    # -------------------------------------------------------------------
    # Prefixed CRUD: submissions
    # -------------------------------------------------------------------

    def submissions_add_or_update(self, record: SubmissionRecord | dict) -> SubmissionRecord:
        """Inserts or updates a submission record using its slug as the key."""
        return self.submissions.add_or_update(record)

    def submissions_bulk_add_or_update(self, records: list[SubmissionRecord | dict]) -> int:
        """Batch inserts/updates submission records in a single disk I/O."""
        return self.submissions.bulk_add_or_update(records)

    def submissions_get_by_slug(self, slug: str) -> SubmissionRecord | None:
        """Fetches a single submission record by slug."""
        return self.submissions.get_by_slug(slug)

    def submissions_exists(self, slug: str) -> bool:
        """Checks if a submission exists for `slug`."""
        return self.submissions.exists(slug)

    def submissions_delete(self, slug: str) -> bool:
        """Deletes a submission record by slug. Returns True if deleted."""
        return self.submissions.delete(slug)

    def submissions_list_all(self) -> list[SubmissionRecord]:
        """Returns all stored submission records."""
        return self.submissions.list_all()

    def submissions_count(self) -> int:
        """Returns total number of stored submissions."""
        return self.submissions.count()

    # -------------------------------------------------------------------
    # Solved-slugs pending cache (unchanged behavior, delegated to PendingCacheStore)
    # -------------------------------------------------------------------

    def read_pending_cache(self) -> dict[str, dict[str, bool]]:
        """Returns the full pending cache: {slug: {description, images, submission}}."""
        return self.cache.read_pending_cache()

    def get_pending_slugs(self) -> list[str]:
        """Returns slugs that still have at least one part outstanding."""
        return self.cache.get_pending_slugs()

    def _actual_part_state(self, slug: str) -> dict[str, bool]:
        """
        Reconstructs true per-part completion for `slug` from the problem/
        submission records themselves, independent of whatever the pending
        cache currently says.

        `images` uses `ProblemRecord.images_populated` (has_images=False, or
        has_images=True with at least one successful download) rather than
        raw `imgs_local_paths` truthiness — a question can legitimately have
        zero images, which would otherwise be indistinguishable from "images
        part never ran", while a question whose images all failed to
        download should still be considered pending (worth retrying).
        """
        problem = self.problems.get_by_slug(slug)
        return {
            "description": bool(problem and problem.raw_question_html),
            "images": bool(problem and problem.images_populated),
            "submission": self.submissions.exists(slug),
        }

    def refresh_pending_cache(self, slugs: list[str]) -> dict[str, dict[str, bool]]:
        """
        Merges newly-fetched solved slugs into the cache, preserving existing
        per-part progress. For slugs not already tracked, reconstructs true
        per-part completion from the existing problem/submission records (so
        a problem already fully synced in problems.json/submissions.json —
        e.g. after the pending cache was reset or rebuilt — isn't re-flagged
        as fully pending) and skips adding it if every part is already done.
        """
        tracked = self.cache.read_pending_cache()
        initial_state = {
            slug: self._actual_part_state(slug) for slug in slugs if slug not in tracked
        }
        return self.cache.refresh_pending_cache(slugs, initial_state=initial_state)

    def reconcile_pending_cache(self) -> int:
        """
        Cross-checks every slug still tracked in the pending cache against the
        actual problem/submission records and marks any part that's genuinely
        already fetched but not yet reflected in the cache — e.g. the cache
        fell out of sync with problems.json/submissions.json after being
        edited by hand or rebuilt from a stale state. A slug found fully
        complete is dropped from the cache (via the normal mark_part_fetched
        behavior). Returns the number of parts marked as a result.

        Cheap and read-mostly (a no-op write per genuinely-stale part), so
        it's safe to call unconditionally before resolving pending slugs.
        """
        tracked = self.cache.read_pending_cache()
        marked = 0
        for slug, parts in tracked.items():
            actual = self._actual_part_state(slug)
            for part, done in actual.items():
                if done and not parts.get(part, False):
                    self.cache.mark_part_fetched(slug, part)
                    marked += 1
        if marked:
            logger.info("pending_cache_reconciled", parts_marked=marked)
        return marked

    def is_part_pending(self, slug: str, part: str) -> bool:
        """True if `part` for `slug` is still outstanding in the cache."""
        return self.cache.is_part_pending(slug, part)

    def mark_part_fetched(self, slug: str, part: str) -> None:
        """Marks `part` ('description' | 'images' | 'submission') as fetched for `slug`."""
        self.cache.mark_part_fetched(slug, part)

    def reopen_part(self, slug: str, part: str) -> None:
        """Marks `part` pending again for `slug`, re-adding it to the cache if it was previously fully complete."""
        self.cache.reopen_part(slug, part)

    def remove_from_cache(self, slug: str) -> bool:
        """Manually drops a slug from the pending cache. Returns True if it was present."""
        return self.cache.remove_from_cache(slug)
