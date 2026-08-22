import requests
from requests_ratelimiter import LimiterAdapter
from urllib3.util import Retry

from modules.leetcode.settings import leetcode_settings


class LeetCodeClient:

    def __init__(self, settings=leetcode_settings):
        self.settings = settings
        self.session = requests.Session()
        self._setup_session()

    def _setup_session(self):
        # 1. Automatic Retries on HTTP 429 (Too Many Requests) or Server Errors (5xx)
        retries = Retry(
            total=3,  # Total number of retries
            backoff_factor=2,  # Exponential backoff: 2s, 4s, 8s
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False,
        )

        # 2. Rate Limiting Adapter (e.g., max 2 requests per second)
        rate_limiter = LimiterAdapter(
            per_second=2,
            max_retries=retries,
        )

        # Mount the rate limiter and retries on all HTTP/HTTPS endpoints
        self.session.mount("https://", rate_limiter)
        self.session.mount("http://", rate_limiter)

        # Configure Headers and Cookies
        self.session.headers.update(
            {
                "X-CSRFToken": self.settings.CSRF_TOKEN,
                "Content-Type": "application/json",
                "Referer": str(self.settings.BASE_URL),
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            }
        )
        self.session.cookies.set(
            "LEETCODE_SESSION",
            self.settings.SESSION,
            domain="leetcode.com",
        )
        self.session.cookies.set(
            "csrftoken",
            self.settings.CSRF_TOKEN,
            domain="leetcode.com",
        )

    def get_solved_questions_slugs(self) -> list[dict]:
        """Fetches all solved problems ('ac' status) from the REST API endpoint."""

        url = self.settings.ENDPOINT_ALL_PROBLEMS
        response = self.session.get(url)
        response.raise_for_status()

        data = response.json()
        raw_pairs = data.get("stat_status_pairs", [])

        solved_problems_slugs = []

        for pair in raw_pairs:
            if pair.get("status") == "ac":
                slug = pair.get("stat").get("question__title_slug")
                solved_problems_slugs.append(slug)

        return solved_problems_slugs

    def get_question_details(self, title_slug: str) -> dict:
        """Queries LeetCode's GraphQL API to get comprehensive metadata for a specific problem."""
        url = f"{self.settings.BASE_URL}/graphql"

        query = """
        query selectQuestion($titleSlug: String!) {
          question(titleSlug: $titleSlug) {
            content
            questionFrontendId
            title
            titleSlug
            difficulty
            categoryTitle
            topicTags {
              name
              slug
            }
          }
        }
        """

        payload = {"query": query, "variables": {"titleSlug": title_slug}}

        response = self.session.post(url, json=payload)
        response.raise_for_status()

        result = response.json()
        if "errors" in result:
            raise RuntimeError(f"GraphQL Error: {result['errors']}")

        return result.get("data", {}).get("question", {})
