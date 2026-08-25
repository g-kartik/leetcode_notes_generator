import tempfile
from pathlib import Path

from .subprocess_provider import SubprocessJSONProvider

# Tool names disallowed for the headless call — it should only reason over
# the prompt text it's handed, never read/write/execute anything. Passed as
# one space-separated string (matches `claude -p --help`'s own example).
_DISALLOWED_TOOLS = (
    "Bash Read Write Edit Glob Grep WebFetch WebSearch NotebookEdit Task"
)


class ClaudeCodeProvider(SubprocessJSONProvider):
    """
    Runs Claude Code itself in headless mode (`claude -p`) as the prefill
    backend — no separate API key needed, usage is billed against the
    Claude Code subscription instead of a metered API key.

    Tool access is disabled (see _DISALLOWED_TOOLS) and the subprocess runs
    from a neutral temp directory rather than the project root, so this call
    never picks up this repo's CLAUDE.md / hooks / auto-memory, and can't
    read or touch project files even if a tool call somehow slipped through.
    Deliberately does NOT use `--bare` — bare mode only accepts
    ANTHROPIC_API_KEY/apiKeyHelper auth and never reads the OAuth session a
    plain subscription relies on.
    """

    name = "claude_code"

    def __init__(self, *, model: str = "sonnet", timeout: float = 120.0):
        super().__init__(
            command=[
                "claude",
                "-p",
                "--output-format",
                "json",
                "--model",
                model,
                "--disallowedTools",
                _DISALLOWED_TOOLS,
            ],
            system_prompt_flag="--system-prompt",
            envelope_key="result",
            timeout=timeout,
            cwd=Path(tempfile.gettempdir()),
        )
