from abc import ABC, abstractmethod


class AIProviderError(RuntimeError):
    """Raised when a provider's underlying CLI invocation fails or returns unusable output."""


class AIProvider(ABC):
    """
    One pluggable AI backend for prefill generation. Implementations only
    need to turn (system_prompt, user_prompt) into raw response text — prompt
    assembly (prompt_builder.py) and response validation (generator.py) live
    outside this layer, so a new provider is just "how do I run this tool and
    get its answer back", nothing else.
    """

    name: str

    @abstractmethod
    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        """
        Runs the underlying AI tool and returns its raw text response —
        expected to be a JSON payload (see schema.PrefillContent), not yet
        parsed or validated. Raises AIProviderError on any failure (nonzero
        exit, timeout, missing binary, empty output).
        """
