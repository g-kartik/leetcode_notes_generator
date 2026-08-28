import sqlite3
from pathlib import Path

import structlog

from modules.leetcode.settings import leetcode_settings

logger = structlog.get_logger(__name__)

# Schema changes made after a table's initial CREATE TABLE go here as
# numbered *.sql files (see migrations/0001_... for the pattern), applied in
# filename order and tracked in schema_migrations — never edit SCHEMA below
# for an existing table once it's shipped, since that only affects a
# brand-new DB; an existing one only picks up the change via a migration.
MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# All four tables live in one file (leetcode_settings.DSA_DB_PATH) since
# they're always used together and joined constantly (problems+tags for
# filtering, problems+submissions for rendering). submissions.slug is
# deliberately a plain column, not a FOREIGN KEY: ProblemStorage.delete()
# leaves a slug's submission data untouched by design, and a real FK would
# either block that delete or force an ON DELETE CASCADE that changes it.
SCHEMA = """
CREATE TABLE IF NOT EXISTS problems (
    slug                     TEXT PRIMARY KEY,
    id                       INTEGER UNIQUE,
    title                    TEXT,
    url                      TEXT,
    difficulty               TEXT,
    category                 TEXT,
    raw_question_html        TEXT,
    has_images               INTEGER,
    imgs_local_paths         TEXT,
    content_remote_markdown  TEXT,
    content_local_html       TEXT,
    content_local_markdown   TEXT,
    content_text             TEXT
);

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS problem_tags (
    problem_slug TEXT NOT NULL REFERENCES problems(slug) ON DELETE CASCADE,
    tag_id       INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (problem_slug, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_problem_tags_tag_id ON problem_tags(tag_id);

CREATE TABLE IF NOT EXISTS submissions (
    slug            TEXT PRIMARY KEY,
    lang            TEXT NOT NULL,
    code            TEXT NOT NULL,
    submission_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pending_cache (
    slug        TEXT PRIMARY KEY,
    description INTEGER NOT NULL DEFAULT 0,
    images      INTEGER NOT NULL DEFAULT 0,
    submission  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _run_migrations(conn: sqlite3.Connection) -> None:
    """
    Applies every migrations/*.sql file not yet recorded in
    schema_migrations, in filename order (numeric prefix, e.g.
    0001_add_pending_cache_metadata.sql) — so a DB created before a given
    schema change picks it up automatically the next time it connects,
    exactly once. A brand-new DB runs every migration too (SCHEMA above only
    ever reflects the *original* shape of each table — see the note by
    MIGRATIONS_DIR), so there's a single source of truth for the current
    schema regardless of when the DB file was first created.
    """
    applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = path.stem
        if version in applied:
            continue
        logger.info("schema_migration_applying", version=version)
        conn.executescript(path.read_text())
        conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
        conn.commit()
        logger.info("schema_migration_applied", version=version)


def get_connection() -> sqlite3.Connection:
    """
    Opens the shared leetcode.db connection: WAL mode (so a read doesn't
    block a concurrent write), foreign keys enforced, row_factory set so
    query results can be accessed by column name, the base schema applied
    idempotently, then every not-yet-applied migration (see
    MIGRATIONS_DIR/_run_migrations). Creates the file and its parent
    directory on first use.
    """
    path = leetcode_settings.DSA_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    conn.commit()
    _run_migrations(conn)
    logger.info("leetcode_db_connected", path=str(path))
    return conn
