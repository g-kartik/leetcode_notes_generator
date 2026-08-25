import json

import structlog
from pydantic import ValidationError

from modules.leetcode.storage.combined import CombinedQuestionRecord

from .prompt_builder import PrefillPromptBuilder
from .providers.base import AIProvider, AIProviderError
from .providers.registry import get_provider
from .schema import PrefillContent
from .storage import AIPrefillStorage, PrefillVersion

logger = structlog.get_logger(__name__)


class PrefillGenerationError(RuntimeError):
    """Raised when a provider call succeeds but its output can't be turned into valid PrefillContent."""


def _strip_code_fence(text: str) -> str:
    """Some CLI tools wrap JSON in ```json ... ``` even when told not to — strip it defensively."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return text.strip()


class AIPrefillGenerator:
    """
    Orchestrates one prefill generation: builds the prompt, calls the
    configured AIProvider, validates the response against PrefillContent,
    and appends it as a new version in the prefill store.

    The provider is pluggable (see providers/registry.py) — this class never
    talks to a specific CLI tool directly, only the AIProvider interface.
    """

    def __init__(
        self,
        provider: AIProvider | None = None,
        prompt_builder: PrefillPromptBuilder | None = None,
        storage: AIPrefillStorage | None = None,
    ):
        self.provider = provider or get_provider()
        self.prompt_builder = prompt_builder or PrefillPromptBuilder()
        self.storage = storage or AIPrefillStorage()

    def _parse_response(self, raw: str) -> PrefillContent:
        cleaned = _strip_code_fence(raw)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise PrefillGenerationError(
                f"provider did not return valid JSON: {cleaned[:500]}"
            ) from exc
        try:
            return PrefillContent.model_validate(data)
        except ValidationError as exc:
            raise PrefillGenerationError(f"provider JSON didn't match schema: {exc}") from exc

    def generate(self, record: CombinedQuestionRecord) -> PrefillVersion:
        """
        Runs one generation for `record` and appends it as a new version.
        Raises AIProviderError (the provider itself failed) or
        PrefillGenerationError (the provider answered, but not with valid
        schema-conforming JSON) — callers decide how to report/retry.
        """
        log = logger.bind(slug=record.slug)
        system_prompt = self.prompt_builder.system_prompt()
        user_prompt = self.prompt_builder.user_prompt(record)

        log.info("prefill_generation_started", provider=self.provider.name)
        raw = self.provider.generate(system_prompt=system_prompt, user_prompt=user_prompt)

        content = self._parse_response(raw)
        version = self.storage.add_version(record.slug, provider=self.provider.name, content=content)
        log.info(
            "prefill_generation_succeeded",
            version_count=self.storage.version_count(record.slug),
        )
        return version
