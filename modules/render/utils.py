from enum import StrEnum
from pathlib import Path


class FileVariant(StrEnum):
    REMOTE = "remote"  # Will use the markdown with remote(internet) image urls
    LOCAL = "local"  # Will use the markdown with locally saved image urls(local relative paths)


class NotesStyle(StrEnum):
    PLAIN = "plain"  # Plain Markdown, no Obsidian syntax
    OBSIDIAN = "obsidian"  # Obsidian wikilinks + callouts
    PLAIN_AI = "plain+ai"  # Plain + AI-prefilled content (not implemented yet)
    OBSIDIAN_AI = "obsidian+ai"  # Obsidian + AI-prefilled content (not implemented yet)


def sanitized_filename(frontend_id: int | None, title: str | None) -> str:
    """Generates the shared OS-safe Markdown filename `<id> - <title>.md` used by every renderer."""
    raw_name = f"{frontend_id or 0:04d} - {title}.md"
    return "".join(
        c for c in raw_name if c.isalnum() or c in (" ", "-", "_", ".")
    ).rstrip()


def problems_root(base: Path) -> Path:
    """<base>/Leetcode Problems — root for both the remote and local problem/solution files."""
    return base / "Leetcode Problems"


def notes_root(base: Path) -> Path:
    """<base>/Leetcode Notes — root for the single, style-agnostic notes file per problem."""
    return base / "Leetcode Notes"
