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

    BASE_URL: str = "https://leetcode.com"

    ENDPOINT_ALL_PROBLEMS: str = f"{BASE_URL}/api/problems/all/"

    DATA_STORAGE_DIR: Path = BaseProjectSettings.PROJECT_ROOT_DIR / "LEETCODE_DATA"
    PROBLEMS_DATA_DIR: Path = DATA_STORAGE_DIR / "dsa_problems"

    DSA_PROBLEMS_JSON: Path = PROBLEMS_DATA_DIR / "db.json"
    DSA_PROBLEMS_ASSETS_DIR: Path = PROBLEMS_DATA_DIR / "assets"


leetcode_settings = LeetCodeSettings()
