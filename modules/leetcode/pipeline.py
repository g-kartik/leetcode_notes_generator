import logging

from modules.leetcode.models import QuestionRecord, SubmissionDetails

from . import parsers
from .client import LeetCodeClient
from .storage import LeetCodeStorage

logger = logging.getLogger(__name__)


class LeetCodeSyncManager:
    def __init__(
        self,
        client: LeetCodeClient | None = None,
        storage: LeetCodeStorage | None = None,
    ):
        self.client = client or LeetCodeClient()
        self.storage = storage or LeetCodeStorage()

    def sync_solved_questions_data_entry(self) -> list[str]:
        """Step 1: Fetches all solved slugs from LeetCode API and add empty data set against it"""
        logger.info("Fetching solved questions list from LeetCode...")
        solved_problem_slugs = self.client.get_solved_questions_slugs()

        new_slugs = []

        for slug in solved_problem_slugs:
            if not self.storage.exists(slug):
                new_slugs.append(slug)
                logger.info(f"New solved question found: {slug}")

        logger.info(
            f"Sync complete: {len(solved_problem_slugs)} solved total, {len(new_slugs)} data entries created."
        )

        return new_slugs

    def populate_question_details(self, slug: str, force_update: bool = False) -> bool:
        """Step 2: Fetches details for a specific slug from GraphQL, parses HTML, and updates the storage record."""
        existing_record = self.storage.get_by_slug(slug)

        if force_update or not existing_record:
            logger.info(f"Fetching question details for '{slug}'...")

            gql_data = self.client.get_question_details(slug)
            if not gql_data:
                logger.warning(
                    f"Could not retrieve details for '{slug}' (paid only or API issue)."
                )
                return False

            parsed_data = parsers.gql_question_data(gql_data)

            if existing_record:
                # Preserve submission data
                question_record = QuestionRecord(
                    **parsed_data, submission=existing_record.submission
                )
            else:
                question_record = QuestionRecord(**parsed_data)

            question_record.content_txt = parsers.html_to_plain_text(
                question_record.content_html
            )
            question_record.content_md = parsers.html_to_markdown(
                question_record.content_html
            )

            self.storage.add_or_update(question_record)

            logger.info(f"Successfully populated record for '{slug}'.")

            return True

        logger.info(
            (
                f"We already have data for this question '{slug}'...",
                "If you want to update anyway use force_update.",
            )
        )
        return False

    def _get_accepted_submission_id(self, submission_list: list) -> int | None:
        for submission_data in submission_list:
            if submission_data.get("statusDisplay") == "Accepted":
                return submission_data.get("id")

    def populate_latest_accepted_submission_code(
        self, slug: str, force_update: bool = False
    ) -> bool:
        """Step 3: Fetches submission list and stores the latest accepted submission code for a specific slug from GraphQL"""
        existing_record = self.storage.get_by_slug(slug)

        if force_update or not existing_record or not existing_record.submission:
            submission_list_result = self.client.get_submission_list(slug)
            submission_list = parsers.gql_submission_list(submission_list_result)
            accepted_submission_id = self._get_accepted_submission_id(submission_list)

            if not accepted_submission_id:
                logger.warning(f"No submissions found for the question slug {slug}")
                return False

            submission_details_result = self.client.get_submission_details(
                accepted_submission_id
            )
            submission_data = parsers.gql_submission_data(submission_details_result)
            logger.info(submission_data)
            submission_record = SubmissionDetails(**submission_data)

            if existing_record:
                existing_record.submission = submission_record
                self.storage.add_or_update(existing_record)
            else:
                question_record = QuestionRecord(slug=slug, submission=submission_record)
                self.storage.add_or_update(question_record)

            logger.info(f"Successfully populated submission data for '{slug}'.")
            return True

        logger.info(
            (
                f"We already have submission data for this question '{slug}'...",
                "If you want to update anyway use force_update.",
            )
        )
        return False

    def run_full_sync(self, limit: int | None = None, force_update: bool = False):
        """Orchestrates the entire end-to-end pipeline."""
        # 1. Fetch solved slugs & create empty stubs
        new_slugs = self.sync_solved_questions_data_entry()

        # 2. Iterate through slugs and populate GraphQL details + Parsed Content
        # Note: Your transport layer rate limiter automatically handles delays between calls here!
        logger.info(f"Populating data for {len(new_slugs)} questions...")
        populated_count = 0

        for slug in new_slugs:
            updated = self.populate_question_details(slug, force_update=force_update)
            if updated:
                populated_count += 1

        logger.info(
            f"Pipeline finished! Populated details for {populated_count} questions."
        )


leetcode_manager = LeetCodeSyncManager()
