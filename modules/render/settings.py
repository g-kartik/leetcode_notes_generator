from pathlib import Path

from pydantic import field_validator

from settings import BaseProjectSettings


class RendererSettings(BaseProjectSettings):
    TEMPLATE_DIR: Path = BaseProjectSettings.PROJECT_ROOT_DIR / "templates"

    OBSIDIAN_VAULT_DIR: Path

    @field_validator("OBSIDIAN_VAULT_DIR",)
    @classmethod
    def expand_paths(cls, value: Path) -> Path:
        return value.expanduser()


render_settings = RendererSettings()
