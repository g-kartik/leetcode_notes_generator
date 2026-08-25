import json
from datetime import datetime
from pathlib import Path

import structlog
from pydantic import BaseModel

from .schema import PrefillContent
from .settings import ai_prefill_settings

logger = structlog.get_logger(__name__)


class PrefillVersion(BaseModel):
    generated_at: datetime
    provider: str
    content: PrefillContent


class AIPrefillStorage:
    """
    JSON-backed store for AI-generated prefill content, keyed by slug ->
    list of versions (oldest first). Kept as its own file (ai_prefill.json),
    separate from problems.json/submissions.json, since this data is
    regenerable and optional — it's not part of the sync pipeline's
    idempotency model, and deleting it never loses anything the pipeline
    can't reconstruct by generating again.

    Re-running generation for an already-prefilled slug appends a new
    version rather than overwriting the previous one, since the user may
    want to compare attempts or just try again after tweaking a prompt.
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or ai_prefill_settings.PREFILL_JSON_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_db_exists()

    def _ensure_db_exists(self) -> None:
        if not self.db_path.exists():
            logger.info("ai_prefill_db_initialized", path=str(self.db_path))
            self._save_raw({"prefills": {}})

    def _load_raw(self) -> dict:
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as exc:
            logger.warning(
                "ai_prefill_db_load_failed_using_empty",
                path=str(self.db_path),
                error=str(exc),
            )
            return {"prefills": {}}

    def _save_raw(self, data: dict) -> None:
        """Atomic write: writes to a temporary file first, then replaces target file."""
        temp_path = self.db_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_path.replace(self.db_path)

    def add_version(self, slug: str, *, provider: str, content: PrefillContent) -> PrefillVersion:
        """Appends a new version for `slug`. Existing versions are never overwritten or dropped."""
        version = PrefillVersion(generated_at=datetime.now(), provider=provider, content=content)
        data = self._load_raw()
        data["prefills"].setdefault(slug, []).append(version.model_dump(mode="json"))
        self._save_raw(data)
        logger.bind(slug=slug).info(
            "ai_prefill_version_saved",
            provider=provider,
            version_count=len(data["prefills"][slug]),
        )
        return version

    def list_versions(self, slug: str) -> list[PrefillVersion]:
        """Returns every stored version for `slug`, oldest first. Empty list if none exist."""
        data = self._load_raw()
        return [PrefillVersion(**v) for v in data["prefills"].get(slug, [])]

    def latest(self, slug: str) -> PrefillVersion | None:
        versions = self.list_versions(slug)
        return versions[-1] if versions else None

    def version_count(self, slug: str) -> int:
        return len(self._load_raw()["prefills"].get(slug, []))

    def exists(self, slug: str) -> bool:
        return self.version_count(slug) > 0
