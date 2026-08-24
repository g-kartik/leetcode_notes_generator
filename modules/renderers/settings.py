from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RendererSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    OBSIDIAN_VAULT_DIR: Path

    @field_validator(
        "OBSIDIAN_VAULT_DIR",
    )
    @classmethod
    def expand_paths(cls, value: Path) -> Path:
        return value.expanduser()


# Module-level single instance or lazy evaluation
render_settings = RendererSettings()
