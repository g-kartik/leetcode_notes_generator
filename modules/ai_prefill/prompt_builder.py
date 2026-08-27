import json
from pathlib import Path
from string import Template

from modules.leetcode.storage.combined import CombinedQuestionRecord

from .schema import PrefillContent
from .settings import ai_prefill_settings


class PrefillPromptBuilder:
    """
    Loads the system/user prompt templates from AI_PREFILL_PROMPTS_DIR
    (resources/prompts/ai_prefill/*.txt by default) and fills them in for one problem.

    Kept separate from the provider layer so prompt wording can be tuned by
    editing text files, not Python — and separate from schema.py so the
    schema stays the single source of truth for both the prompt (embedded as
    JSON schema text) and response validation.

    Uses stdlib string.Template ($name placeholders) rather than str.format,
    since the embedded JSON schema is full of literal '{' / '}' that would
    collide with format-string syntax.
    """

    def __init__(self, prompts_dir: Path | None = None):
        self.prompts_dir = prompts_dir or ai_prefill_settings.PROMPTS_DIR
        self._system_template = Template(
            (self.prompts_dir / "system_prompt.txt").read_text(encoding="utf-8")
        )
        self._user_template = Template(
            (self.prompts_dir / "user_prompt.txt").read_text(encoding="utf-8")
        )

    def system_prompt(self) -> str:
        schema_json = json.dumps(PrefillContent.model_json_schema(), indent=2)
        return self._system_template.safe_substitute(schema_json=schema_json)

    def user_prompt(self, record: CombinedQuestionRecord) -> str:
        tags = ", ".join(
            t.get("name") or t.get("slug", "") for t in (record.tags or [])
        )
        description = (record.content.text or record.content.remote_markdown or "").strip()
        submission = record.submission
        code = (submission.code if submission else "(no accepted submission stored)").strip()

        return self._user_template.safe_substitute(
            title=record.title or record.slug,
            question_id=record.id if record.id is not None else "?",
            difficulty=record.difficulty or "?",
            tags=tags or "none",
            description=description[: ai_prefill_settings.MAX_DESCRIPTION_CHARS],
            language=submission.lang if submission else "unknown",
            code=code[: ai_prefill_settings.MAX_CODE_CHARS],
        )
