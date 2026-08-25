from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from settings import BaseProjectSettings


class LeetCodeSettings(BaseProjectSettings):
    model_config = SettingsConfigDict(
        env_prefix="LEETCODE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SESSION: str = Field(..., description="LeetCode session cookie")
    CSRF_TOKEN: str = Field(..., description="LeetCode CSRF token")

    # Optional (not a secret) — only needed for the recentAcSubmissionList
    # query, which takes a username rather than reading it off the session.
    USERNAME: str | None = Field(default=None, description="LeetCode public username")

    BASE_URL: str = "https://leetcode.com"

    ENDPOINT_ALL_PROBLEMS: str = f"{BASE_URL}/api/problems/all/"

    # Kept conservative on purpose — a large batch run (e.g. populating hundreds
    # of solved problems in one sitting) is exactly the traffic shape abuse
    # detection looks for. See modules/leetcode/rate_limiting.py.
    REQUESTS_PER_SECOND: float = 1.0

    DATA_STORAGE_DIR: Path = BaseProjectSettings.PROJECT_ROOT_DIR / "LEETCODE_DATA"
    PROBLEMS_DATA_DIR: Path = DATA_STORAGE_DIR / "dsa_problems"

    DSA_PROBLEMS_JSON_DB: Path = PROBLEMS_DATA_DIR / "problems.json"
    DSA_SUBMISSIONS_JSON_DB: Path = PROBLEMS_DATA_DIR / "submissions.json"
    DSA_PROBLEMS_CACHE_JSON_DB: Path = PROBLEMS_DATA_DIR / "solved_slugs_cache.json"
    DSA_PROBLEMS_ASSETS_DIR: Path = PROBLEMS_DATA_DIR / "assets"


leetcode_settings = LeetCodeSettings()
