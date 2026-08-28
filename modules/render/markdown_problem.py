import shutil
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from modules.leetcode.settings import leetcode_settings
from modules.leetcode.storage.combined import CombinedQuestionRecord

from .settings import render_settings
from .utils import FileVariant as FV
from .utils import problems_root, sanitized_filename

logger = structlog.get_logger(__name__)


class LeetCodeDSAProblemMarkdownRender:
    def __init__(
        self,
        output_base: Path | str | None = None,
    ):
        self.template_dir = render_settings.TEMPLATE_DIR
        self.project_root = render_settings.PROJECT_ROOT_DIR
        self.dsa_problems_assets_dir = leetcode_settings.DSA_PROBLEMS_ASSETS_DIR

        # Priority: caller-supplied (CLI) > OUTPUT_BASE_DIR (.env) > DEFAULT_WRITE_DIR.
        self.output_base = render_settings.resolve_base_dir(output_base)

        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape([]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.template = self.env.get_template("leetcode_problem.md.j2")

        self.output_base.mkdir(parents=True, exist_ok=True)

    def render(self, record: CombinedQuestionRecord, variant: FV) -> str:
        """Renders a CombinedQuestionRecord into a Markdown string for a specific variant."""
        log = logger.bind(slug=record.slug)
        markdown_content = (
            record.content.remote_markdown
            if variant == FV.REMOTE
            else record.content.local_markdown
        )
        rendered = self.template.render(
            frontend_id=record.id,
            slug=record.slug,
            title=record.title,
            difficulty=record.difficulty,
            tags=record.tags,
            url=record.url,
            content=markdown_content,
            submission=record.submission,
        )
        log.info(
            "markdown_rendered",
            variant=variant.value if hasattr(variant, "value") else str(variant),
            has_submission=record.submission is not None,
        )
        return rendered

    def _get_sanitized_filename(self, record: CombinedQuestionRecord) -> str:
        return sanitized_filename(record.id, record.title)

    def _save_remote(self, record: CombinedQuestionRecord, root: Path) -> Path:
        """Writes remote variant into <root>/remote/<file>.md."""
        log = logger.bind(slug=record.slug)
        remote_dir = root / "remote"
        remote_dir.mkdir(parents=True, exist_ok=True)

        output_file = remote_dir / self._get_sanitized_filename(record)
        output_file.write_text(self.render(record, FV.REMOTE), encoding="utf-8")
        log.info("variant_file_written", variant="remote", path=str(output_file))
        return output_file

    def _save_local(self, record: CombinedQuestionRecord, root: Path) -> Path:
        """Writes local variant into <root>/local/<slug>/<file>.md, with assets."""
        if not record.slug:
            raise ValueError("question slug cannot be null")

        log = logger.bind(slug=record.slug)
        target_problem_dir = root / "local" / record.slug
        target_problem_dir.mkdir(parents=True, exist_ok=True)

        # Images live directly under DSA_PROBLEMS_ASSETS_DIR/<slug>/ (no nested
        # "assets" folder on the source side — see image_processor.py) — that
        # whole slug dir becomes this note's assets/ folder.
        source_assets_dir = self.dsa_problems_assets_dir / record.slug

        target_assets_dir = target_problem_dir / "assets"

        if source_assets_dir.exists() and source_assets_dir.is_dir():
            if target_assets_dir.exists():
                shutil.rmtree(target_assets_dir)
            shutil.copytree(source_assets_dir, target_assets_dir)
            log.info(
                "assets_copied",
                source=str(source_assets_dir),
                target=str(target_assets_dir),
            )
        else:
            log.info("assets_copy_skipped", reason="no_local_assets_found")

        output_file = target_problem_dir / self._get_sanitized_filename(record)
        output_file.write_text(self.render(record, FV.LOCAL), encoding="utf-8")
        log.info("variant_file_written", variant="local", path=str(output_file))
        return output_file

    def _save_variant(
        self, record: CombinedQuestionRecord, variant: FV, root: Path
    ) -> Path:
        return (
            self._save_local(record, root)
            if variant == FV.LOCAL
            else self._save_remote(record, root)
        )

    def save(self, record: CombinedQuestionRecord) -> dict:
        """
        Renders and saves `record` under <output_base>/Leetcode Problems/<variant>/....

        Remote is always written. Local is written too only when the record
        has a local variant worth having (see CombinedQuestionRecord.has_local_variant)
        — otherwise it'd be a byte-for-byte duplicate of remote.

        Returns e.g.: {"local": Path(...), "remote": Path(...)}
        """
        log = logger.bind(slug=record.slug)
        variants = [FV.REMOTE, FV.LOCAL] if record.has_local_variant else [FV.REMOTE]
        root = problems_root(self.output_base)

        log.info("render_save_started", variants=[v.value for v in variants])

        results = {v.value: self._save_variant(record, v, root) for v in variants}

        log.info("render_save_completed", variants=list(results.keys()))
        return results
