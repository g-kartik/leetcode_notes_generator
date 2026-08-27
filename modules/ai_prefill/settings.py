import shlex
from pathlib import Path

from pydantic_settings import SettingsConfigDict

from settings import BaseProjectSettings


class AIPrefillSettings(BaseProjectSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_PREFILL_",
        env_file=(".env.defaults", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Which AIProvider to build — see providers/registry.py. 'claude_code'
    # shells out to `claude -p` (no separate API key needed, billed against
    # the Claude Code subscription). 'command' is the generic escape hatch
    # for any other CLI AI tool (ollama, llm, a local script...).
    PROVIDER: str = "claude_code"

    # Only used by the 'claude_code' provider.
    MODEL: str = "sonnet"

    TIMEOUT_SECONDS: float = 120.0

    # Only used by the 'command' provider — a shell-splittable argv template
    # for any other CLI AI tool, e.g. "ollama run llama3". SYSTEM_PROMPT_FLAG
    # is the CLI flag that tool uses to accept a system prompt (omit if it
    # has none — the system prompt is then folded into stdin instead).
    # ENVELOPE_KEY unwraps a JSON envelope around the real answer (like
    # Claude Code's `--output-format json` wraps it in {"result": "..."});
    # leave unset if the tool prints the raw answer directly.
    COMMAND: str | None = None
    SYSTEM_PROMPT_FLAG: str | None = None
    ENVELOPE_KEY: str | None = None

    # Pause between consecutive generations in a `notes prefill --all` run.
    # Exists so a free/rate-limited plan doesn't get throttled; a Pro-plan
    # user can pass --no-rate-limit (or set this to 0) to skip it entirely.
    RATE_LIMIT_SECONDS: float = 3.0

    # How much of the question description / accepted solution to include in
    # the prompt — keeps a single generation call fast and bounded even for
    # unusually long problems or solutions.
    MAX_DESCRIPTION_CHARS: int = 6000
    MAX_CODE_CHARS: int = 6000

    PROMPTS_DIR: Path = BaseProjectSettings.PROJECT_ROOT_DIR / "resources" / "prompts" / "ai_prefill"

    DATA_STORAGE_DIR: Path = BaseProjectSettings.PROJECT_ROOT_DIR / "LEETCODE_DATA"
    PREFILL_JSON_DB: Path = DATA_STORAGE_DIR / "dsa_problems" / "ai_prefill.json"

    def command_argv(self) -> list[str]:
        """Splits COMMAND into an argv list for the generic 'command' provider."""
        if not self.COMMAND:
            raise ValueError(
                "AI_PREFILL_COMMAND must be set when AI_PREFILL_PROVIDER=command"
            )
        return shlex.split(self.COMMAND)


ai_prefill_settings = AIPrefillSettings()
