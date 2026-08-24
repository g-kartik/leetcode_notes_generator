import os
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from modules.leetcode.storage.combined import CombinedQuestionRecord

from .settings import render_settings
from .utils import FileVariant, NotesStyle, dsa_root, sanitized_filename

logger = structlog.get_logger(__name__)

_AI_STYLES = {NotesStyle.PLAIN_AI, NotesStyle.OBSIDIAN_AI}

_TEMPLATE_BY_STYLE = {
    NotesStyle.PLAIN: "leetcode_notes_plain.md.j2",
    NotesStyle.OBSIDIAN: "leetcode_notes_obsidian.md.j2",
    NotesStyle.PLAIN_AI: "leetcode_notes_plain.md.j2",
    NotesStyle.OBSIDIAN_AI: "leetcode_notes_obsidian.md.j2",
}

# AI styles share their base style's folder — prefilling a note later edits the
# same file rather than producing a separate artifact.
_FOLDER_BY_STYLE = {
    NotesStyle.PLAIN: "plain",
    NotesStyle.OBSIDIAN: "obsidian",
    NotesStyle.PLAIN_AI: "plain",
    NotesStyle.OBSIDIAN_AI: "obsidian",
}

# No AI prefill step exists yet, so every section renders as an empty
# placeholder for the user to fill in by hand — only frontmatter + the
# problem/solution link are populated.
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
        write_to_obsidian_vault: bool = False,
        link_variant: FileVariant = FileVariant.REMOTE,
    ):
        self.style = NotesStyle(style) if isinstance(style, str) else style
        if self.style in _AI_STYLES:
            raise NotImplementedError(
                f"notes style '{self.style.value}' is not implemented yet — AI prefill is a "
                f"later task. Use '{NotesStyle.PLAIN.value}' or '{NotesStyle.OBSIDIAN.value}' for now."
            )
        if link_variant == FileVariant.ALL:
            raise ValueError("link_variant must be 'remote' or 'local', not 'all'")

        self.template_dir = render_settings.TEMPLATE_DIR
        self.obsidian_vault = render_settings.OBSIDIAN_VAULT_DIR
        self.write_to_obsidian = write_to_obsidian_vault
        self.link_variant = link_variant

        # Base dir is caller-supplied, else falls back to the configured default.
        self.output_base = (
            Path(output_base)
            if output_base is not None
            else render_settings.DEFAULT_WRITE_DIR
        )

        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape([]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.template = self.env.get_template(_TEMPLATE_BY_STYLE[self.style])

        self.output_base.mkdir(parents=True, exist_ok=True)
        if self.write_to_obsidian:
            self.obsidian_vault.mkdir(parents=True, exist_ok=True)

    def _notes_dir(self, base: Path) -> Path:
        """<base>/LeetCode/DSA/notes/<plain|obsidian>."""
        return dsa_root(base) / "notes" / _FOLDER_BY_STYLE[self.style]

    def _problem_file_path(self, record: CombinedQuestionRecord, base: Path) -> Path:
        """Absolute path to this record's already-rendered problem/solution file."""
        filename = sanitized_filename(record.id, record.title)
        root = dsa_root(base)
        if self.link_variant == FileVariant.LOCAL:
            if not record.slug:
                raise ValueError("question slug cannot be null")
            return root / "local" / record.slug / filename
        return root / "remote" / filename

    def render(self, record: CombinedQuestionRecord, base: Path) -> str:
        """Renders a CombinedQuestionRecord into a notes Markdown string (frontmatter + link only, for now)."""
        log = logger.bind(slug=record.slug)
        problem_file = self._problem_file_path(record, base)
        if not problem_file.exists():
            log.warning(
                "notes_link_target_missing",
                path=str(problem_file),
                hint="run the 'render' command for this slug first",
            )

        context = dict(
            _EMPTY_PREFILL,
            frontend_id=record.id,
            slug=record.slug,
            title=record.title,
            difficulty=record.difficulty,
            url=record.url,
            topics=record.tags or [],
            problem_note_name=problem_file.stem,
            problem_note_relpath=os.path.relpath(problem_file, start=self._notes_dir(base)),
        )
        rendered = self.template.render(**context)
        log.info("notes_rendered", style=self.style.value, link_variant=self.link_variant.value)
        return rendered

    def _save_to(self, record: CombinedQuestionRecord, base: Path) -> Path:
        """Writes the notes file into <base>/LeetCode/DSA/notes/<style>/<file>.md."""
        log = logger.bind(slug=record.slug)
        notes_dir = self._notes_dir(base)
        notes_dir.mkdir(parents=True, exist_ok=True)

        output_file = notes_dir / sanitized_filename(record.id, record.title)
        output_file.write_text(self.render(record, base), encoding="utf-8")
        log.info("notes_file_written", style=self.style.value, path=str(output_file))
        return output_file

    def save(self, record: CombinedQuestionRecord) -> dict:
        """
        Renders and saves a notes file for `record` to output_base, and
        additionally to the Obsidian vault if write_to_obsidian_vault=True.

        Returns e.g.: {"output_base": Path(...), "obsidian": Path(...)}
        """
        log = logger.bind(slug=record.slug)
        log.info(
            "notes_save_started",
            style=self.style.value,
            write_to_obsidian=self.write_to_obsidian,
        )

        results = {"output_base": self._save_to(record, self.output_base)}
        if self.write_to_obsidian:
            results["obsidian"] = self._save_to(record, self.obsidian_vault)

        log.info("notes_save_completed", style=self.style.value)
        return results
