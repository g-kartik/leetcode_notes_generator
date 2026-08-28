from modules.ai_prefill.settings import AIPrefillSettings, ai_prefill_settings

from .base import AIProvider
from .claude_code import ClaudeCodeProvider
from .subprocess_provider import SubprocessJSONProvider

_BUILTIN_FACTORIES = {
    "claude_code": lambda s: ClaudeCodeProvider(
        model=s.MODEL, timeout=s.TIMEOUT_SECONDS
    ),
    "command": lambda s: SubprocessJSONProvider(
        command=s.command_argv(),
        system_prompt_flag=s.SYSTEM_PROMPT_FLAG,
        envelope_key=s.ENVELOPE_KEY,
        timeout=s.TIMEOUT_SECONDS,
    ),
}


def get_provider(settings: AIPrefillSettings = ai_prefill_settings) -> AIProvider:
    """
    Builds the configured AIProvider. 'claude_code' (default) shells out to
    `claude -p`. 'command' is the generic escape hatch for any other CLI AI
    tool (ollama, llm, a local script...) — point AI_PREFILL_COMMAND at it
    in .env, no new Python code required.
    """
    try:
        factory = _BUILTIN_FACTORIES[settings.PROVIDER]
    except KeyError:
        raise ValueError(
            f"unknown AI_PREFILL_PROVIDER '{settings.PROVIDER}' — "
            f"choices: {list(_BUILTIN_FACTORIES)}"
        ) from None
    return factory(settings)
