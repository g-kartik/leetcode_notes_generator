import shutil
from enum import StrEnum
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from modules.leetcode.models import QuestionRecord
from modules.leetcode.settings import leetcode_settings


class FileVariant(StrEnum):
    REMOTE = "remote"  # Will use the markdown with remote(internet) image urls
    LOCAL = "local"  # Will use the markdown with locally saved image urls(local relative paths)


class LeetCodeProblemMarkdownRenderer:
    def __init__(
        self,
        template_dir: str | Path = "templates",
        variant: FileVariant | str = "remote",
    ):
        self.template_dir = Path(template_dir)
        self.project_root = leetcode_settings.PROJECT_ROOT
        self.obsidian_vault = leetcode_settings.OBSIDIAN_VALUT_DIR
        self.variant = variant
        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape([]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.template = self.env.get_template("leetcode_problem.md.j2")
        self.obsidian_vault.mkdir(parents=True, exist_ok=True)

    def render(self, record: QuestionRecord) -> str:
        """Renders a QuestionRecord into an Obsidian Markdown string based on variant."""
        markdown_content = (
            record.content.remote_markdown
            if self.variant == FileVariant.REMOTE
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

    def _save_remote(self, record: QuestionRecord) -> Path:
        """Saves remote variant markdown directly into vault_dir root."""

        remote_dir = self.obsidian_vault / "remote"
        remote_dir.mkdir(parents=True, exist_ok=True)
        filename = self._get_sanitized_filename(record)
        output_file = remote_dir / filename

        markdown_content = self.render(record)
        output_file.write_text(markdown_content, encoding="utf-8")
        return output_file

    def _save_local(self, record: QuestionRecord) -> Path:
        """Saves local variant into vault_path/leetcode_problems/local/<slug>/ with copied assets."""
        # Target path: <vault_dir>/local/<slug>/
        if not record.slug:
            raise ValueError("question slug cannot be null")

        target_problem_dir = self.obsidian_vault / "local" / record.slug
        target_problem_dir.mkdir(parents=True, exist_ok=True)

        # Source assets path in project: project_root/leetcode_problems/local/<slug>/assets/
        source_assets_dir = (
            Path(self.project_root)
            / "leetcode_problems"
            / "local"
            / record.slug
            / "assets"
        )
        target_assets_dir = target_problem_dir / "assets"

        # Copy assets folder to vault if local assets exist in project root
        if source_assets_dir.exists() and source_assets_dir.is_dir():
            if target_assets_dir.exists():
                shutil.rmtree(target_assets_dir)
            shutil.copytree(source_assets_dir, target_assets_dir)

        # Write markdown note directly inside problem slug folder
        filename = self._get_sanitized_filename(record)
        output_file = target_problem_dir / filename

        markdown_content = self.render(record)
        output_file.write_text(markdown_content, encoding="utf-8")
        return output_file

    def save_to_vault(self, record: QuestionRecord) -> Path:
        """Renders and delegates saving to the appropriate variant handler."""
        if self.variant == FileVariant.LOCAL:
            return self._save_local(record)
        else:
            return self._save_remote(record)
