import os
import shutil
from datetime import datetime
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from modules.ai_prefill.storage import AIPrefillStorage
from modules.leetcode.storage.combined import CombinedQuestionRecord

from .settings import render_settings
from .utils import (
    FileVariant,
    NotesStyle,
    notes_root,
    problems_root,
    sanitized_filename,
)

logger = structlog.get_logger(__name__)

_AI_STYLES = {NotesStyle.PLAIN_AI, NotesStyle.OBSIDIAN_AI}

_BACKUP_TIMESTAMP_FMT = "%Y-%m-%d-%H-%M-%S"

_TEMPLATE_BY_STYLE = {
    NotesStyle.PLAIN: "leetcode_notes_plain.md.j2",
    NotesStyle.OBSIDIAN: "leetcode_notes_obsidian.md.j2",
    NotesStyle.PLAIN_AI: "leetcode_notes_plain.md.j2",
    NotesStyle.OBSIDIAN_AI: "leetcode_notes_obsidian.md.j2",
}


class PrefillMissingError(RuntimeError):
    """Raised when a '+ai' style is requested but no AI prefill content has been generated yet for the slug."""


# Every section renders as an empty placeholder for the user to fill in by
# hand by default — only frontmatter + the problem/solution link(s) are
# populated. '+ai' styles override the prefill_* keys below with the latest
# stored modules.ai_prefill.PrefillContent for the slug (see render()).
_EMPTY_PREFILL = dict(
    aliases=[],
    pattern_tags=[],
    problem_summary=None,
    pattern=None,
    core_idea=None,
    invariant=None,
    trap=None,
    recognition_clue=None,
    complexity_time=None,
    complexity_space=None,
    takeaway=None,
    related=None,
)


class LeetCodeDSAProblemNotesRender:
    def __init__(
        self,
        style: NotesStyle | str = NotesStyle.PLAIN,
        output_base: Path | str | None = None,
    ):
        self.style = NotesStyle(style) if isinstance(style, str) else style

        self.template_dir = render_settings.TEMPLATE_DIR

        # Priority: caller-supplied (CLI) > OUTPUT_BASE_DIR (.env) > DEFAULT_WRITE_DIR.
        self.output_base = render_settings.resolve_base_dir(output_base)

        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape([]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.template = self.env.get_template(_TEMPLATE_BY_STYLE[self.style])

        self.output_base.mkdir(parents=True, exist_ok=True)

    def _problem_file_path(
        self, record: CombinedQuestionRecord, variant: FileVariant
    ) -> Path:
        """Absolute path to this record's already-rendered problem/solution file, for one variant."""
        filename = sanitized_filename(record.id, record.title)
        root = problems_root(self.output_base)
        if variant == FileVariant.LOCAL:
            if not record.slug:
                raise ValueError("question slug cannot be null")
            return root / "local" / record.slug / filename
        return root / "remote" / filename

    def _tags(self, record: CombinedQuestionRecord) -> list[str]:
        """Personal pattern tags + LeetCode question-tag slugs, deduped, in one list."""
        question_tag_slugs = [
            t.get("slug") for t in (record.tags or []) if t.get("slug")
        ]
        return list(
            dict.fromkeys([*_EMPTY_PREFILL["pattern_tags"], *question_tag_slugs])
        )

    def _flashcard_deck_tags(self, record: CombinedQuestionRecord) -> list[str]:
        """Deck-tag-only scaffold for the Flashcards callout — no AI, no cards,
        just one '#flashcards/DSA/<tag>' line per note tag plus the problem
        itself, ready for the user to add cards under by hand."""
        lines = [f"#flashcards/DSA/{tag}" for tag in self._tags(record)]
        if record.slug:
            lines.append(f"#flashcards/DSA/problems/{record.slug}")
        return lines

    def _warn_if_missing(self, path: Path, log) -> None:
        if not path.exists():
            log.warning(
                "notes_link_target_missing",
                path=str(path),
                hint="run the 'render' command for this slug first",
            )

    def render(self, record: CombinedQuestionRecord) -> str:
        """Renders a CombinedQuestionRecord into a notes Markdown string (frontmatter + problem link(s) only, for now)."""
        log = logger.bind(slug=record.slug)
        notes_dir = notes_root(self.output_base)

        context = dict(
            _EMPTY_PREFILL,
            frontend_id=record.id,
            slug=record.slug,
            title=record.title,
            difficulty=record.difficulty,
            url=record.url,
            tags=self._tags(record),
            flashcards=self._flashcard_deck_tags(record),
        )

        if self.style in _AI_STYLES:
            prefill = AIPrefillStorage().latest(record.slug)
            if prefill is None:
                raise PrefillMissingError(
                    f"no AI prefill content found for '{record.slug}' — run "
                    f"'notes prefill {record.slug}' first, or use '{NotesStyle.PLAIN.value}'/"
                    f"'{NotesStyle.OBSIDIAN.value}' instead"
                )
            # PrefillContent's field names are chosen to match these template
            # vars 1:1 (see modules/ai_prefill/schema.py), so this directly
            # overrides the corresponding _EMPTY_PREFILL placeholders.
            # 'flashcards' is deliberately not part of PrefillContent — the
            # deck-tag scaffold above is left as-is either way.
            context.update(prefill.content.model_dump())
            log.info("notes_prefill_applied", generated_at=str(prefill.generated_at))

        if self.style in (NotesStyle.OBSIDIAN, NotesStyle.OBSIDIAN_AI):
            # Obsidian wikilinks resolve relative to the vault root, not the note's
            # own folder, and remote/local share the same filename — so both links
            # need a full, disambiguating path from output_base (which, when the
            # user points OUTPUT_BASE_DIR at their vault, IS the vault root).
            remote_file = self._problem_file_path(record, FileVariant.REMOTE)
            self._warn_if_missing(remote_file, log)
            context["problem_remote_link"] = (
                remote_file.relative_to(self.output_base).with_suffix("").as_posix()
            )
            if record.has_local_variant:
                local_file = self._problem_file_path(record, FileVariant.LOCAL)
                self._warn_if_missing(local_file, log)
                context["problem_local_link"] = (
                    local_file.relative_to(self.output_base).with_suffix("").as_posix()
                )
            else:
                context["problem_local_link"] = None
        else:
            # Always link whichever variant was actually rendered for this
            # problem — local when it exists, remote otherwise. See
            # CombinedQuestionRecord.has_local_variant.
            variant = FileVariant.LOCAL if record.has_local_variant else FileVariant.REMOTE
            problem_file = self._problem_file_path(record, variant)
            self._warn_if_missing(problem_file, log)
            context["problem_note_name"] = problem_file.stem
            context["problem_note_relpath"] = os.path.relpath(
                problem_file, start=notes_dir
            )

        rendered = self.template.render(**context)
        log.info("notes_rendered", style=self.style.value)
        return rendered

    def _backup_dir(self, record: CombinedQuestionRecord) -> Path:
        """
        <output_base>/Leetcode Notes/backups/<id>-<slug>/ — one subfolder per
        problem, since repeated --force runs can accumulate multiple backups
        and dumping every problem's backups into one shared folder would make
        them hard to tell apart.
        """
        return (
            notes_root(self.output_base)
            / "backups"
            / f"{record.id or 0:04d}-{record.slug}"
        )

    def _backup_existing_note(
        self, output_file: Path, record: CombinedQuestionRecord, log
    ) -> Path:
        """Copies the current notes file into its per-problem backup folder, timestamped."""
        backup_dir = self._backup_dir(record)
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime(_BACKUP_TIMESTAMP_FMT)
        backup_file = backup_dir / f"{output_file.stem}-{timestamp}{output_file.suffix}"
        shutil.copy2(output_file, backup_file)
        log.info("notes_existing_backed_up", path=str(backup_file))
        return backup_file

    def save(
        self, record: CombinedQuestionRecord, force: bool = False
    ) -> tuple[Path, str]:
        """
        Renders and saves the (single, style-agnostic) notes file for `record`
        into <output_base>/Leetcode Notes/<file>.md. Re-running with a different
        --style overwrites this same file — there's one notes file per problem.

        A notes file is meant to be hand-edited after generation (pattern, core
        idea, invariant, trap, ...), so an existing file is never silently
        overwritten: by default, this is a no-op if the file already exists.
        Pass force=True to regenerate anyway — the existing file is copied into
        its per-problem backup folder (timestamped) first, so nothing is lost.

        Returns (path, status) where status is "written" or "skipped".
        """
        log = logger.bind(slug=record.slug)
        notes_dir = notes_root(self.output_base)
        notes_dir.mkdir(parents=True, exist_ok=True)

        output_file = notes_dir / sanitized_filename(record.id, record.title)

        if output_file.exists():
            if not force:
                log.info(
                    "notes_save_skipped",
                    reason="notes_file_already_exists",
                    path=str(output_file),
                    hint="pass force=True (--force) to regenerate; the existing file is backed up first",
                )
                return output_file, "skipped"
            self._backup_existing_note(output_file, record, log)

        output_file.write_text(self.render(record), encoding="utf-8")
        log.info("notes_file_written", style=self.style.value, path=str(output_file))
        return output_file, "written"
