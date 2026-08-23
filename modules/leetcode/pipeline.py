import logging

from modules.leetcode.models import QuestionRecord

from .client import LeetCodeClient
from .parsers.question_content.html_to_markdown import html_to_markdown
from .parsers.question_content.html_to_plain_text import html_to_plain_text
from .parsers.question_detail_response import gql_question_data_parser
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

            parsed_data = gql_question_data_parser(gql_data)

            if existing_record:
                # Preserve submission data
                question_record = QuestionRecord(**parsed_data, submission=existing_record.submission)
            else:
                question_record = QuestionRecord(**parsed_data)

            question_record.content_txt = html_to_plain_text(
                question_record.content_html
            )
            question_record.content_md = html_to_markdown(question_record.content_html)

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
