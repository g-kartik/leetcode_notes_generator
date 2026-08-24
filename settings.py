from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseProjectSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PROJECT_ROOT_DIR: Path = Path(__file__).resolve().parent
