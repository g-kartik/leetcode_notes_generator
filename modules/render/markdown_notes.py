import os
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from modules.leetcode.storage.combined import CombinedQuestionRecord

from .settings import render_settings
from .utils import FileVariant, NotesStyle, notes_root, problems_root, sanitized_filename

logger = structlog.get_logger(__name__)

_AI_STYLES = {NotesStyle.PLAIN_AI, NotesStyle.OBSIDIAN_AI}

_TEMPLATE_BY_STYLE = {
    NotesStyle.PLAIN: "leetcode_notes_plain.md.j2",
    NotesStyle.OBSIDIAN: "leetcode_notes_obsidian.md.j2",
    NotesStyle.PLAIN_AI: "leetcode_notes_plain.md.j2",
    NotesStyle.OBSIDIAN_AI: "leetcode_notes_obsidian.md.j2",
}

# No AI prefill step exists yet, so every section renders as an empty
# placeholder for the user to fill in by hand — only frontmatter + the
# problem/solution link(s) are populated.
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
        # Only used by the 'plain' style, which links a single problem-file variant.
        # 'obsidian' always links both remote and local, regardless of this.
        self.link_variant = link_variant

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

    def _problem_file_path(self, record: CombinedQuestionRecord, variant: FileVariant) -> Path:
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
        question_tag_slugs = [t.get("slug") for t in (record.tags or []) if t.get("slug")]
        return list(dict.fromkeys([*_EMPTY_PREFILL["pattern_tags"], *question_tag_slugs]))

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
        )

        if self.style == NotesStyle.OBSIDIAN:
            # Obsidian wikilinks resolve relative to the vault root, not the note's
            # own folder, and remote/local share the same filename — so both links
            # need a full, disambiguating path from output_base (which, when the
            # user points OUTPUT_BASE_DIR at their vault, IS the vault root).
            remote_file = self._problem_file_path(record, FileVariant.REMOTE)
            local_file = self._problem_file_path(record, FileVariant.LOCAL)
            self._warn_if_missing(remote_file, log)
            self._warn_if_missing(local_file, log)
            context["problem_remote_link"] = remote_file.relative_to(self.output_base).with_suffix("").as_posix()
            context["problem_local_link"] = local_file.relative_to(self.output_base).with_suffix("").as_posix()
        else:
            problem_file = self._problem_file_path(record, self.link_variant)
            self._warn_if_missing(problem_file, log)
            context["problem_note_name"] = problem_file.stem
            context["problem_note_relpath"] = os.path.relpath(problem_file, start=notes_dir)

        rendered = self.template.render(**context)
        log.info("notes_rendered", style=self.style.value)
        return rendered

    def save(self, record: CombinedQuestionRecord) -> Path:
        """
        Renders and saves the (single, style-agnostic) notes file for `record`
        into <output_base>/Leetcode Notes/<file>.md. Re-running with a different
        --style overwrites this same file — there's one notes file per problem.
        """
        log = logger.bind(slug=record.slug)
        notes_dir = notes_root(self.output_base)
        notes_dir.mkdir(parents=True, exist_ok=True)

        output_file = notes_dir / sanitized_filename(record.id, record.title)
        output_file.write_text(self.render(record), encoding="utf-8")
        log.info("notes_file_written", style=self.style.value, path=str(output_file))
        return output_file
