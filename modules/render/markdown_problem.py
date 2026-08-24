import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from modules.leetcode.models import QuestionRecord
from modules.leetcode.settings import leetcode_settings

from .settings import render_settings
from .utils import FileVariant as FV


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

    def render(self, record: QuestionRecord, variant: FV) -> str:
        """Renders a QuestionRecord into a Markdown string for a specific variant."""
        markdown_content = (
            record.content.remote_markdown
            if variant == FV.REMOTE
            else record.content.local_markdown
        )
        return self.template.render(
            frontend_id=record.id,
            slug=record.slug,
            title=record.title,
            difficulty=record.difficulty,
            tags=record.tags,
            url=record.url,
            content=markdown_content,
            submission=record.submission,
        )

    def _get_sanitized_filename(self, record: QuestionRecord) -> str:
        """Generates an OS-safe Markdown filename."""
        raw_name = f"{record.id or 0:04d} - {record.title}.md"
        return "".join(
            c for c in raw_name if c.isalnum() or c in (" ", "-", "_", ".")
        ).rstrip()

    def _dsa_root(self, base: Path) -> Path:
        """The fixed internal structure root: <base>/LeetCode/DSA."""
        return base / "LeetCode" / "DSA"

    def _save_remote(self, record: QuestionRecord, base: Path) -> Path:
        """Writes remote variant into <base>/LeetCode/DSA/remote/<file>.md."""
        remote_dir = self._dsa_root(base) / "remote"
        remote_dir.mkdir(parents=True, exist_ok=True)

        output_file = remote_dir / self._get_sanitized_filename(record)
        output_file.write_text(self.render(record, FV.REMOTE), encoding="utf-8")
        return output_file

    def _save_local(self, record: QuestionRecord, base: Path) -> Path:
        """Writes local variant into <base>/LeetCode/DSA/local/<slug>/<file>.md, with assets."""
        if not record.slug:
            raise ValueError("question slug cannot be null")

        target_problem_dir = self._dsa_root(base) / "local" / record.slug
        target_problem_dir.mkdir(parents=True, exist_ok=True)

        source_assets_dir = self.dsa_problems_assets_dir / record.slug / "assets"

        target_assets_dir = target_problem_dir / "assets"

        if source_assets_dir.exists() and source_assets_dir.is_dir():
            if target_assets_dir.exists():
                shutil.rmtree(target_assets_dir)
            shutil.copytree(source_assets_dir, target_assets_dir)

        output_file = target_problem_dir / self._get_sanitized_filename(record)
        output_file.write_text(self.render(record, FV.LOCAL), encoding="utf-8")
        return output_file

    def _save_variant(self, record: QuestionRecord, variant: FV, base: Path) -> Path:
        return (
            self._save_local(record, base)
            if variant == FV.LOCAL
            else self._save_remote(record, base)
        )

    def save(self, record: QuestionRecord) -> dict:
        """
        Renders and saves `record` to output_base, and additionally to the
        Obsidian vault if write_to_obsidian=True. Both destinations share the
        same LeetCode/DSA/<variant>/... internal structure.

        Returns e.g.:
            {"local": {"output_base": Path(...), "obsidian": Path(...)}}
        or, when variant is ALL:
            {"local": {...}, "remote": {...}}
        """
        variants = [FV.LOCAL, FV.REMOTE] if self.variant == FV.ALL else [self.variant]

        results = {}
        for v in variants:
            targets = {"output_base": self._save_variant(record, v, self.output_base)}
            if self.write_to_obsidian:
                targets["obsidian"] = self._save_variant(record, v, self.obsidian_vault)
            results[v.value if hasattr(v, "value") else str(v)] = targets

        return results
