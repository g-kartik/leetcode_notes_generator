import shutil
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from modules.leetcode.settings import leetcode_settings
from modules.leetcode.storage.combined import CombinedQuestionRecord

from .settings import render_settings
from .utils import FileVariant as FV
from .utils import dsa_root, sanitized_filename

logger = structlog.get_logger(__name__)


class LeetCodeDSAProblemMarkdownRender:
    def __init__(
        self,
        variant: FV | str = FV.ALL,
        output_base: Path | str | None = None,
        write_to_obsidian_vault: bool = False,
    ):
        self.template_dir = render_settings.TEMPLATE_DIR
        self.project_root = render_settings.PROJECT_ROOT_DIR
        self.obsidian_vault = render_settings.OBSIDIAN_VAULT_DIR
        self.dsa_problems_assets_dir = leetcode_settings.DSA_PROBLEMS_ASSETS_DIR

        self.variant = FV(variant) if isinstance(variant, str) else variant
        self.write_to_obsidian = write_to_obsidian_vault

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
        self.template = self.env.get_template("leetcode_problem.md.j2")

        self.output_base.mkdir(parents=True, exist_ok=True)
        if self.write_to_obsidian:
            self.obsidian_vault.mkdir(parents=True, exist_ok=True)

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

    def _dsa_root(self, base: Path) -> Path:
        return dsa_root(base)

    def _save_remote(self, record: CombinedQuestionRecord, base: Path) -> Path:
        """Writes remote variant into <base>/LeetCode/DSA/remote/<file>.md."""
        log = logger.bind(slug=record.slug)
        remote_dir = self._dsa_root(base) / "remote"
        remote_dir.mkdir(parents=True, exist_ok=True)

        output_file = remote_dir / self._get_sanitized_filename(record)
        output_file.write_text(self.render(record, FV.REMOTE), encoding="utf-8")
        log.info("variant_file_written", variant="remote", path=str(output_file))
        return output_file

    def _save_local(self, record: CombinedQuestionRecord, base: Path) -> Path:
        """Writes local variant into <base>/LeetCode/DSA/local/<slug>/<file>.md, with assets."""
        if not record.slug:
            raise ValueError("question slug cannot be null")

        log = logger.bind(slug=record.slug)
        target_problem_dir = self._dsa_root(base) / "local" / record.slug
        target_problem_dir.mkdir(parents=True, exist_ok=True)

        source_assets_dir = self.dsa_problems_assets_dir / record.slug / "assets"

        target_assets_dir = target_problem_dir / "assets"

        if source_assets_dir.exists() and source_assets_dir.is_dir():
            if target_assets_dir.exists():
                shutil.rmtree(target_assets_dir)
            shutil.copytree(source_assets_dir, target_assets_dir)
            log.info("assets_copied", source=str(source_assets_dir), target=str(target_assets_dir))
        else:
            log.info("assets_copy_skipped", reason="no_local_assets_found")

        output_file = target_problem_dir / self._get_sanitized_filename(record)
        output_file.write_text(self.render(record, FV.LOCAL), encoding="utf-8")
        log.info("variant_file_written", variant="local", path=str(output_file))
        return output_file

    def _save_variant(self, record: CombinedQuestionRecord, variant: FV, base: Path) -> Path:
        return (
            self._save_local(record, base)
            if variant == FV.LOCAL
            else self._save_remote(record, base)
        )

    def save(self, record: CombinedQuestionRecord) -> dict:
        """
        Renders and saves `record` to output_base, and additionally to the
        Obsidian vault if write_to_obsidian=True. Both destinations share the
        same LeetCode/DSA/<variant>/... internal structure.

        Returns e.g.:
            {"local": {"output_base": Path(...), "obsidian": Path(...)}}
        or, when variant is ALL:
            {"local": {...}, "remote": {...}}
        """
        log = logger.bind(slug=record.slug)
        variants = [FV.LOCAL, FV.REMOTE] if self.variant == FV.ALL else [self.variant]

        log.info(
            "render_save_started",
            variants=[v.value for v in variants],
            write_to_obsidian=self.write_to_obsidian,
        )

        results = {}
        for v in variants:
            targets = {"output_base": self._save_variant(record, v, self.output_base)}
            if self.write_to_obsidian:
                targets["obsidian"] = self._save_variant(record, v, self.obsidian_vault)
            results[v.value if hasattr(v, "value") else str(v)] = targets

        log.info("render_save_completed", variants=list(results.keys()))
        return results
