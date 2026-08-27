from pathlib import Path

from pydantic import field_validator

from settings import BaseProjectSettings


class RendererSettings(BaseProjectSettings):
    TEMPLATE_DIR: Path = BaseProjectSettings.PROJECT_ROOT_DIR / "templates"

    DEFAULT_WRITE_DIR: Path = BaseProjectSettings.PROJECT_ROOT_DIR / "LOCAL_RENDER"

    # Optional .env override for where rendered problems/notes live — e.g. point
    # this straight at (a folder inside) an Obsidian vault. A CLI --output-base
    # always wins over this; this is the fallback checked before DEFAULT_WRITE_DIR.
    OUTPUT_BASE_DIR: Path | None = None

    # Default `--style` for `notes render` ("plain" or "obsidian"), so it
    # doesn't have to be typed on every invocation. A CLI --style always wins
    # over this.
    DEFAULT_NOTES_STYLE: str = "plain"

    @field_validator("OUTPUT_BASE_DIR", mode="before")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("OUTPUT_BASE_DIR")
    @classmethod
    def _expand_output_base(cls, value: Path | None) -> Path | None:
        return value.expanduser() if value is not None else None

    def resolve_base_dir(self, cli_override: Path | str | None = None) -> Path:
        """Base output dir, in priority order: CLI --output-base > OUTPUT_BASE_DIR (.env) > DEFAULT_WRITE_DIR."""
        if cli_override is not None:
            return Path(cli_override).expanduser()
        if self.OUTPUT_BASE_DIR is not None:
            return self.OUTPUT_BASE_DIR
        return self.DEFAULT_WRITE_DIR


render_settings = RendererSettings()
