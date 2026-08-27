from pathlib import Path
from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseProjectSettings(BaseSettings):
    # Loaded in order, later files win: .env.defaults (committed — every
    # non-secret setting's shipped default) then .env (gitignored — real
    # secrets, plus any personal override of a default you want only on
    # this machine). A subclass that redeclares model_config to add its own
    # env_prefix must repeat this env_file tuple too, since pydantic merges
    # model_config per-key across the MRO — the subclass's own value for a
    # key always wins over the inherited one, it doesn't compose with it.
    model_config = SettingsConfigDict(
        env_file=(".env.defaults", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PROJECT_ROOT_DIR: ClassVar[Path] = Path(__file__).resolve().parent
