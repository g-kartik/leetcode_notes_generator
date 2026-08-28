import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import structlog
from pydantic import BaseModel

from .schema import PrefillContent
from .settings import ai_prefill_settings

logger = structlog.get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS prefill_versions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    slug         TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    provider     TEXT NOT NULL,
    content      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prefill_slug ON prefill_versions(slug);
"""


class PrefillVersion(BaseModel):
    generated_at: datetime
    provider: str
    content: PrefillContent


class AIPrefillStorage:
    """
    SQLite-backed store for AI-generated prefill content (the
    `prefill_versions` table), keyed by slug -> list of versions (oldest
    first). Kept in its own file (ai_prefill.db), separate from leetcode.db,
    since this data is regenerable and optional — it's not part of the sync
    pipeline's idempotency model, and deleting it never loses anything the
    pipeline can't reconstruct by generating again.

    Re-running generation for an already-prefilled slug appends a new
    version rather than overwriting the previous one, since the user may
    want to compare attempts or just try again after tweaking a prompt.
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or ai_prefill_settings.PREFILL_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    @staticmethod
    def _row_to_version(row: sqlite3.Row) -> PrefillVersion:
        return PrefillVersion(
            generated_at=row["generated_at"],
            provider=row["provider"],
            content=PrefillContent.model_validate_json(row["content"]),
        )

    def add_version(
        self, slug: str, *, provider: str, content: PrefillContent
    ) -> PrefillVersion:
        """Appends a new version for `slug`. Existing versions are never overwritten or dropped."""
        version = PrefillVersion(
            generated_at=datetime.now(UTC), provider=provider, content=content
        )
        with self.conn:
            self.conn.execute(
                "INSERT INTO prefill_versions (slug, generated_at, provider, content) VALUES (?, ?, ?, ?)",
                (
                    slug,
                    version.generated_at.isoformat(),
                    version.provider,
                    version.content.model_dump_json(),
                ),
            )
        count = self.version_count(slug)
        logger.bind(slug=slug).info(
            "ai_prefill_version_saved", provider=provider, version_count=count
        )
        return version

    def list_versions(self, slug: str) -> list[PrefillVersion]:
        """Returns every stored version for `slug`, oldest first. Empty list if none exist."""
        rows = self.conn.execute(
            "SELECT * FROM prefill_versions WHERE slug = ? ORDER BY id", (slug,)
        ).fetchall()
        return [self._row_to_version(row) for row in rows]

    def latest(self, slug: str) -> PrefillVersion | None:
        row = self.conn.execute(
            "SELECT * FROM prefill_versions WHERE slug = ? ORDER BY id DESC LIMIT 1",
            (slug,),
        ).fetchone()
        return self._row_to_version(row) if row else None

    def version_count(self, slug: str) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) AS c FROM prefill_versions WHERE slug = ?", (slug,)
        ).fetchone()["c"]

    def exists(self, slug: str) -> bool:
        return self.version_count(slug) > 0
