"""Shared interactive fuzzy picker for commands that accept `SLUG | --all`.

Typing (or copy-pasting) a LeetCode slug by hand is painful — they're long
and there's no way to search LeetCode's own site for one. Whenever a command
gets neither a SLUG nor --all, it falls back to this instead of erroring:
a searchable, multi-select prompt over whatever's known about each problem,
so you never have to type a slug at all.
"""

from InquirerPy.base.control import Choice
from InquirerPy.inquirer import fuzzy

from modules.leetcode.models import ProblemRecord
from modules.leetcode.storage.combined import CombinedQuestionRecord

PICK_MESSAGE = (
    "Search a problem (type to filter, tab to multi-select, enter to confirm):"
)


def pick_slugs(
    candidates: list[tuple[str, str]],
    *,
    message: str = PICK_MESSAGE,
    multiselect: bool = True,
) -> list[str]:
    """
    Interactive fuzzy search + (multi)select over `candidates` — a list of
    (slug, label) pairs, where `label` is what's shown and searched.

    Returns the chosen slug(s) in selection order, or [] if there was
    nothing to pick from, or the user backed out (Ctrl-C / Esc / confirmed
    with nothing selected).
    """
    if not candidates:
        return []

    choices = [Choice(value=slug, name=label) for slug, label in candidates]
    try:
        result = fuzzy(
            message=message,
            choices=choices,
            multiselect=multiselect,
            max_height="70%",
            mandatory=False,
            raise_keyboard_interrupt=False,
        ).execute()
    except KeyboardInterrupt:
        return []

    if result is None:
        return []
    return result if isinstance(result, list) else [result]


def label_records(records: list[CombinedQuestionRecord]) -> list[tuple[str, str]]:
    """(slug, label) pairs for records that already have problem data (title, difficulty, ...)."""
    return [
        (r.slug, f"{r.id or 0:>4}  {r.title or r.slug}  ({r.difficulty or '?'})")
        for r in records
        if r.slug
    ]


def label_slugs(
    slugs: list[str],
    known: dict[str, ProblemRecord],
    *,
    solved_meta: dict[str, dict] | None = None,
    tags: dict[str, str] | None = None,
) -> list[tuple[str, str]]:
    """
    (slug, label) pairs for bare slugs that may or may not have problem data
    yet (e.g. solved-but-not-yet-fetched slugs from the pending cache) —
    labeled in the same "<id>  <title>  (<difficulty>)" format as
    label_records, so the picker never mixes formats.

    Prefers a local DB record (`known`) when one exists; otherwise falls back
    to `solved_meta` — id/title/difficulty per slug, e.g. straight from
    storage.read_pending_cache() (PendingCacheStore persists this on every
    live sync — see LeetCodeSyncManager.sync_pending_cache), so a slug
    that's solved but never locally fetched still gets a real label instead
    of the bare slug, even without a live sync (offline included). Only
    when neither source has anything for a slug does the label fall back to
    the bare slug — still searchable on its own, since LeetCode slugs are
    just the title in kebab-case.

    `tags`, if given, appends e.g. "(new)"/"(updated)" after the difficulty
    for slugs a just-run sync discovered/reopened.
    """
    solved_meta = solved_meta or {}
    tags = tags or {}
    labels = []
    for slug in slugs:
        record = known.get(slug)
        meta = solved_meta.get(slug)
        if record and record.title:
            base = f"{record.id or 0:>4}  {record.title}  ({record.difficulty or '?'})"
        elif meta and meta.get("title"):
            base = f"{meta.get('id') or 0:>4}  {meta['title']}  ({meta.get('difficulty') or '?'})"
        else:
            base = slug
        tag = tags.get(slug)
        labels.append((slug, f"{base} {tag}" if tag else base))
    return labels
