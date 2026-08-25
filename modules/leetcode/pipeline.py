import structlog

from modules.leetcode.models import ProblemRecord, SubmissionRecord

from . import parsers
from .client import LeetCodeClient
from .image_processor import LeetCodeImageProcessor
from .storage import LeetCodeDSAStorage

logger = structlog.get_logger(__name__)


class LeetCodeSyncManager:
    def __init__(
        self,
        client: LeetCodeClient | None = None,
        storage: LeetCodeDSAStorage | None = None,
        image_processor: LeetCodeImageProcessor | None = None,
    ):
        self.client = client or LeetCodeClient()
        self.storage = storage or LeetCodeDSAStorage()
        self.image_processor = image_processor or LeetCodeImageProcessor()

    # ------------------------------------------------------------------ #
    # Step 1: discover solved problems (cache-backed)
    # ------------------------------------------------------------------ #

    def sync_solved_questions_data_entry(
        self, force_refresh: bool = False
    ) -> list[str]:
        """
        Returns slugs still pending at least one of metadata/images/submission.
        By default reads straight from the pending-slugs cache (no API call).
        Pass force_refresh=True to hit the LeetCode API for the latest solved
        list and merge any newly-solved slugs into the cache. Also runs
        automatically the first time, if the cache is empty.

        Note: this only populates the pending cache, never the DB. A DB record
        for a slug is created the first time populate_question_metadata actually
        fetches real data for it — the DB should only ever hold slugs with at
        least one populated part.
        """
        log = logger.bind(stage="sync")
        self.storage.reconcile_pending_cache()
        cache = self.storage.read_pending_cache()

        if force_refresh or not cache:
            log.info("solved_slugs_refresh_started", force_refresh=force_refresh)
            solved_problem_slugs = self.client.get_solved_questions_slugs()
            cache = self.storage.refresh_pending_cache(solved_problem_slugs)
            log.info("solved_slugs_refresh_completed", fetched_count=len(solved_problem_slugs))
        else:
            log.info("solved_slugs_cache_used", reason="cache_populated_and_no_refresh_requested")

        pending_slugs = list(cache.keys())
        log.info("pending_slugs_resolved", pending_count=len(pending_slugs))
        return pending_slugs

    # ------------------------------------------------------------------ #
    # Part 1: Question metadata + content (description)
    # ------------------------------------------------------------------ #

    def populate_question_metadata(self, slug: str, force_update: bool = False) -> bool:
        """
        Fetches question metadata + description content (via GraphQL) and stores it.
        Marks 'metadata' as fetched in the pending cache on success.

        If metadata already exists and force_update is False, this is a no-op.
        """
        with structlog.contextvars.bound_contextvars(slug=slug, stage="problem"):
            existing_record = self.storage.problems_get_by_slug(slug)

            has_metadata = existing_record is not None and bool(
                existing_record.raw_question_html
            )
            if has_metadata and not force_update:
                logger.info(
                    "problem_already_populated",
                    question_id=existing_record.id,
                    title=existing_record.title,
                )
                return False

            logger.info("problem_fetch_started", force_update=force_update)
            gql_data = self.client.get_question_details(slug)
            if not gql_data:
                logger.warning("problem_fetch_failed", reason="no_data_returned")
                return False

            parsed_data = parsers.gql_question_data(gql_data)

            # Preserve fields owned by the other part of this store (images).
            preserved = {}
            if existing_record:
                preserved["imgs_local_paths"] = existing_record.imgs_local_paths

            question_record = ProblemRecord(**parsed_data, **preserved)
            question_record.content.text = parsers.html_to_plain_text(
                question_record.raw_question_html
            )
            question_record.content.remote_markdown = parsers.html_to_markdown(
                question_record.raw_question_html
            )
            question_record.content.local_markdown = question_record.content.remote_markdown
            question_record.content.local_html = question_record.raw_question_html

            self.storage.problems_add_or_update(question_record)
            self.storage.mark_part_fetched(slug, "question")

            logger.info(
                "problem_fetch_succeeded",
                question_id=question_record.id,
                title=question_record.title,
            )
            return True

    # ------------------------------------------------------------------ #
    # Part 2: Question images
    # ------------------------------------------------------------------ #

    def populate_question_images(self, slug: str, force_update: bool = False) -> bool:
        """
        Downloads and caches question images (if any) and derives the
        image-localized HTML/Markdown content. Requires metadata (raw_question_html)
        to already exist — run populate_question_metadata first.
        Marks 'images' as fetched in the pending cache on completion, including
        when the question turns out to have no images (that's still a resolved state).

        If images already exist and force_update is False, this is a no-op.
        """
        with structlog.contextvars.bound_contextvars(slug=slug, stage="images"):
            existing_record = self.storage.problems_get_by_slug(slug)

            if not existing_record or not existing_record.raw_question_html:
                logger.warning("images_fetch_skipped", reason="problem_metadata_missing")
                return False

            has_images = bool(existing_record.imgs_local_paths)
            if has_images and not force_update:
                logger.info(
                    "images_already_populated",
                    image_count=len(existing_record.imgs_local_paths),
                )
                return False

            logger.info("images_processing_started", force_update=force_update)
            image_result = self.image_processor.process_question_images(
                question_record=existing_record
            )

            if not image_result:
                logger.info("images_fetch_succeeded", image_count=0)
                self.storage.mark_part_fetched(slug, "images")
                return True

            existing_record.imgs_local_paths = image_result.get("imgs_local_paths")
            existing_record.content.local_html = image_result.get("content_local_html")
            existing_record.content.local_markdown = parsers.html_to_markdown(
                image_result.get("content_local_html")
            )

            self.storage.problems_add_or_update(existing_record)
            self.storage.mark_part_fetched(slug, "images")

            logger.info(
                "images_fetch_succeeded",
                image_count=len(existing_record.imgs_local_paths or []),
            )
            return True

    # ------------------------------------------------------------------ #
    # Part 3: Submission code details
    # ------------------------------------------------------------------ #

    def _get_accepted_submission_id(self, submission_list: list) -> int | None:
        for submission_data in submission_list:
            if submission_data.get("statusDisplay") == "Accepted":
                return submission_data.get("id")
        return None

    def populate_submission_code(self, slug: str, force_update: bool = False) -> bool:
        """
        Fetches the latest accepted submission (language, code, date) and stores it.
        Marks 'submission' as fetched in the pending cache on success.
        Deliberately does NOT mark the part complete if no accepted submission is
        found yet — the user may submit an accepted solution later.

        If submission data already exists and force_update is False, this is a no-op.
        """
        with structlog.contextvars.bound_contextvars(slug=slug, stage="submission"):
            existing_submission = self.storage.submissions_get_by_slug(slug)

            has_submission = existing_submission is not None
            if has_submission and not force_update:
                logger.info(
                    "submission_already_populated",
                    lang=existing_submission.lang,
                    submission_date=str(existing_submission.submission_date),
                )
                return False

            logger.info("submission_fetch_started", force_update=force_update)
            submission_list_result = self.client.get_submission_list(slug)
            submission_list = parsers.gql_submission_list(submission_list_result)
            accepted_submission_id = self._get_accepted_submission_id(submission_list)

            if not accepted_submission_id:
                logger.warning("submission_fetch_failed", reason="no_accepted_submission_found")
                return False

            submission_details_result = self.client.get_submission_details(
                accepted_submission_id
            )
            submission_data = parsers.gql_submission_data(submission_details_result)
            submission_record = SubmissionRecord(slug=slug, **submission_data)

            self.storage.submissions_add_or_update(submission_record)
            self.storage.mark_part_fetched(slug, "submission")

            logger.info("submission_fetch_succeeded", lang=submission_record.lang)
            return True
