"""
One-off migration: reads the legacy JSON stores (problems.json,
submissions.json, solved_slugs_cache.json, ai_prefill.json) and populates
the new SQLite-backed leetcode.db / ai_prefill.db.

Never deletes or edits the source JSON files — moves them into a
_json_backup/ subfolder next to them once every count has been verified to
match. problems/submissions/pending_cache migration is upsert-based, so
it's safe to re-run; ai_prefill migration skips any slug that already has
versions in the new store, so re-running won't duplicate history.

Run once: uv run python scripts/migrate_json_to_sqlite.py
"""

import json
from pathlib import Path

from modules.ai_prefill.schema import PrefillContent
from modules.ai_prefill.storage import AIPrefillStorage
from modules.leetcode.models import ProblemRecord, SubmissionRecord
from modules.leetcode.settings import leetcode_settings
from modules.leetcode.storage import LeetCodeDSAStorage

DATA_DIR = leetcode_settings.PROBLEMS_DATA_DIR
BACKUP_DIR = DATA_DIR / "_json_backup"

JSON_FILES = ["problems.json", "submissions.json", "solved_slugs_cache.json", "ai_prefill.json"]


def _load_json(path: Path, default):
    if not path.exists():
        print(f"  (skip) {path.name} not found")
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def migrate_problems(storage: LeetCodeDSAStorage) -> tuple[int, int]:
    raw = _load_json(DATA_DIR / "problems.json", {"problems": {}})
    records = [ProblemRecord(**p) for p in raw["problems"].values()]
    storage.problems.bulk_add_or_update(records)
    return len(raw["problems"]), storage.problems.count()


def migrate_submissions(storage: LeetCodeDSAStorage) -> tuple[int, int]:
    raw = _load_json(DATA_DIR / "submissions.json", {"submissions": {}})
    records = [SubmissionRecord(**s) for s in raw["submissions"].values()]
    if records:
        storage.submissions.bulk_add_or_update(records)
    return len(raw["submissions"]), storage.submissions.count()


def migrate_pending_cache(storage: LeetCodeDSAStorage) -> tuple[int, int]:
    raw = _load_json(DATA_DIR / "solved_slugs_cache.json", {})
    with storage.conn:
        for slug, parts in raw.items():
            values = {p: bool(parts.get(p, False)) for p in storage.cache.CACHE_PARTS}
            if all(values.values()):
                continue  # pending_cache only ever holds still-incomplete slugs
            storage.conn.execute(
                "INSERT OR REPLACE INTO pending_cache (slug, description, images, submission) "
                "VALUES (?, ?, ?, ?)",
                (slug, values["description"], values["images"], values["submission"]),
            )
    return len(raw), len(storage.read_pending_cache())


def migrate_ai_prefill() -> tuple[int, int, int]:
    raw = _load_json(DATA_DIR / "ai_prefill.json", {"prefills": {}})
    store = AIPrefillStorage()
    total_source_versions = sum(len(v) for v in raw["prefills"].values())
    migrated, skipped = 0, 0
    for slug, versions in raw["prefills"].items():
        if store.version_count(slug) > 0:
            skipped += len(versions)
            continue
        with store.conn:
            for v in versions:
                content = PrefillContent(**v["content"])
                store.conn.execute(
                    "INSERT INTO prefill_versions (slug, generated_at, provider, content) "
                    "VALUES (?, ?, ?, ?)",
                    (slug, v["generated_at"], v["provider"], content.model_dump_json()),
                )
                migrated += 1
    return total_source_versions, migrated, skipped


def backup_json_files() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for name in JSON_FILES:
        src = DATA_DIR / name
        if src.exists():
            src.rename(BACKUP_DIR / name)
            print(f"  moved {name} -> {BACKUP_DIR / name}")


def main() -> None:
    storage = LeetCodeDSAStorage()

    print("Migrating problems...")
    old_p, new_p = migrate_problems(storage)
    print(f"  problems.json: {old_p} -> leetcode.db problems table: {new_p}")

    print("Migrating submissions...")
    old_s, new_s = migrate_submissions(storage)
    print(f"  submissions.json: {old_s} -> leetcode.db submissions table: {new_s}")

    print("Migrating pending cache...")
    old_c, new_c = migrate_pending_cache(storage)
    print(f"  solved_slugs_cache.json: {old_c} -> leetcode.db pending_cache table: {new_c}")

    print("Migrating AI prefill versions...")
    total_v, migrated_v, skipped_v = migrate_ai_prefill()
    print(f"  ai_prefill.json: {total_v} versions -> ai_prefill.db: {migrated_v} migrated, {skipped_v} skipped (already present)")

    mismatches = []
    if old_p != new_p:
        mismatches.append(f"problems: {old_p} != {new_p}")
    if old_s != new_s:
        mismatches.append(f"submissions: {old_s} != {new_s}")
    if old_c != new_c:
        mismatches.append(f"pending_cache: {old_c} != {new_c}")

    if mismatches:
        print("\nCount mismatch(es) found, NOT backing up JSON files:")
        for m in mismatches:
            print(f"  - {m}")
        return

    print("\nAll counts match. Backing up JSON source files...")
    backup_json_files()
    print("\nDone. Original JSON files are preserved (untouched) under _json_backup/.")


if __name__ == "__main__":
    main()
