from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from settings import project_settings


class LeetCodeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Automatically maps `session` to `LEETCODE_SESSION`
        env_prefix="LEETCODE_",
        extra="ignore",
    )
    # Matches LEETCODE_SESSION in .env
    SESSION: str = Field(..., description="LeetCode session cookie")

    # Matches LEETCODE_CSRF_TOKEN in .env
    CSRF_TOKEN: str = Field(..., description="LeetCode CSRF token")

    BASE_URL: str = "https://leetcode.com"

    ENDPOINT_ALL_PROBLEMS: str = f"{BASE_URL}/api/problems/all/"

    DATA_STORAGE_DIR: Path = project_settings.PROJECT_ROOT_DIR / "LEETCODE_DATA"

    PROBLEMS_DATA_DIR: Path = DATA_STORAGE_DIR / "dsa_problems"

    DSA_PROBLEMS_JSON: Path = PROBLEMS_DATA_DIR / "db.json"
    DSA_PROBLEMS_ASSETS_DIR: Path = PROBLEMS_DATA_DIR / "assets"

# Module-level single instance or lazy evaluation
leetcode_settings = LeetCodeSettings()
