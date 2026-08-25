"""
AI prefill generation for personal study notes: fills in pattern/core-idea/
invariant/trap/... sections (see modules/render/markdown_notes.py's planned
AI styles) by prompting a pluggable CLI AI tool with the stored problem +
submission data. Every generation is appended as a new version, never
overwriting prior ones (see storage.AIPrefillStorage).

Entry point: AIPrefillGenerator (generator.py), used by `notes prefill` in
modules/cli/notes.py. The AI backend itself is pluggable — see
providers/registry.py and AI_PREFILL_PROVIDER in modules/ai_prefill/settings.py.
"""

from .generator import AIPrefillGenerator, PrefillGenerationError
from .providers.base import AIProviderError
from .schema import PrefillContent
from .storage import AIPrefillStorage, PrefillVersion

__all__ = [
    "AIPrefillGenerator",
    "PrefillGenerationError",
    "AIProviderError",
    "PrefillContent",
    "AIPrefillStorage",
    "PrefillVersion",
]
