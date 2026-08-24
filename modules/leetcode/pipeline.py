import structlog

from modules.leetcode.models import QuestionRecord, SubmissionDetails

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
        """
        cache = self.storage.read_pending_cache()

        if force_refresh or not cache:
            logger.info("Fetching solved questions list from LeetCode...")
            solved_problem_slugs = self.client.get_solved_questions_slugs()
            cache = self.storage.refresh_pending_cache(solved_problem_slugs)

            for slug in solved_problem_slugs:
                if not self.storage.exists(slug):
                    self.storage.add_or_update(QuestionRecord(slug=slug))
                    logger.info(f"New solved question found: {slug}")
        else:
            logger.info("Using cached pending slugs (force_refresh=False).")

        pending_slugs = list(cache.keys())
        logger.info(f"{len(pending_slugs)} question(s) pending in cache.")
        return pending_slugs

    # ------------------------------------------------------------------ #
    # Shared helper
    # ------------------------------------------------------------------ #

    def _get_or_create_record(self, slug: str) -> QuestionRecord:
        """Returns the existing record for `slug`, or a fresh empty one if none exists."""
        return self.storage.get_by_slug(slug) or QuestionRecord(slug=slug)

    # ------------------------------------------------------------------ #
    # Part 1: Question metadata + content (description)
    # ------------------------------------------------------------------ #

    def populate_question_metadata(self, slug: str, force_update: bool = False) -> bool:
        """
        Fetches question metadata + description content (via GraphQL) and stores it.
        Marks 'metadata' as fetched in the pending cache on success.

        If metadata already exists and force_update is False, this is a no-op.
        """
        existing_record = self.storage.get_by_slug(slug)

        has_metadata = existing_record is not None and bool(
            existing_record.raw_question_html
        )
        if has_metadata and not force_update:
            logger.info(
                f"Metadata already exists for '{slug}'. Use force_update to refetch."
            )
            return False

        logger.info(f"Fetching question metadata for '{slug}'...")
        gql_data = self.client.get_question_details(slug)
        if not gql_data:
            logger.warning(
                f"Could not retrieve details for '{slug}' (paid only or API issue)."
            )
            return False

        parsed_data = parsers.gql_question_data(gql_data)

        # Preserve fields owned by the other two parts (submission, images).
        preserved = {}
        if existing_record:
            preserved["submission"] = existing_record.submission
            preserved["imgs_local_paths"] = existing_record.imgs_local_paths

        question_record = QuestionRecord(**parsed_data, **preserved)
        question_record.content.text = parsers.html_to_plain_text(
            question_record.raw_question_html
        )
        question_record.content.remote_markdown = parsers.html_to_markdown(
            question_record.raw_question_html
        )
        question_record.content.local_markdown = question_record.content.remote_markdown
        question_record.content.local_html = question_record.raw_question_html

        self.storage.add_or_update(question_record)
        self.storage.mark_part_fetched(slug, "question")

        logger.info(f"Successfully populated metadata for '{slug}'.")
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
        existing_record = self.storage.get_by_slug(slug)

        if not existing_record or not existing_record.raw_question_html:
            logger.warning(
                f"No question metadata found for '{slug}'. "
                "Run populate_question_metadata first."
            )
            return False

        has_images = bool(existing_record.imgs_local_paths)
        if has_images and not force_update:
            logger.info(
                f"Images already processed for '{slug}'. Use force_update to reprocess."
            )
            return False

        logger.info(f"Processing question images for '{slug}'...")
        image_result = self.image_processor.process_question_images(
            question_record=existing_record
        )

        if not image_result:
            logger.info(f"No images to process for '{slug}'.")
            self.storage.mark_part_fetched(slug, "images")
            return True

        existing_record.imgs_local_paths = image_result.get("imgs_local_paths")
        existing_record.content.local_html = image_result.get("content_local_html")
        existing_record.content.local_markdown = parsers.html_to_markdown(
            image_result.get("content_local_html")
        )

        self.storage.add_or_update(existing_record)
        self.storage.mark_part_fetched(slug, "images")

        logger.info(f"Successfully populated images for '{slug}'.")
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
        existing_record = self.storage.get_by_slug(slug)

        has_submission = (
            existing_record is not None and existing_record.submission is not None
        )
        if has_submission and not force_update:
            logger.info(
                f"Submission data already exists for '{slug}'. Use force_update to refetch."
            )
            return False

        logger.info(f"Fetching submission data for '{slug}'...")
        submission_list_result = self.client.get_submission_list(slug)
        submission_list = parsers.gql_submission_list(submission_list_result)
        accepted_submission_id = self._get_accepted_submission_id(submission_list)

        if not accepted_submission_id:
            logger.warning(f"No accepted submissions found for '{slug}'.")
            return False

        submission_details_result = self.client.get_submission_details(
            accepted_submission_id
        )
        submission_data = parsers.gql_submission_data(submission_details_result)
        submission_record = SubmissionDetails(**submission_data)

        record = self._get_or_create_record(slug)
        record.submission = submission_record
        self.storage.add_or_update(record)
        self.storage.mark_part_fetched(slug, "submission")

        logger.info(f"Successfully populated submission data for '{slug}'.")
        return True
