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

    This call should reason only over the prompt text it's handed — nothing
    from this machine's Claude Code configuration should leak in or be
    actionable:
      - `--safe-mode` disables CLAUDE.md (project *and* user-global),
        skills, plugins, hooks, and MCP servers for the session.
      - `--disallowedTools` additionally locks down the built-in tools
        --safe-mode leaves enabled (Bash, file I/O, web access, ...) — a
        prefill call has no legitimate reason to touch any of them.
      - Running from a neutral temp dir (not the project root) is
        redundant with --safe-mode's CLAUDE.md handling, but kept as
        cheap defense in depth against anything that still consults cwd.
    Deliberately does NOT use `--bare` — bare mode only accepts
    ANTHROPIC_API_KEY/apiKeyHelper auth and never reads the OAuth session a
    plain subscription relies on; --safe-mode keeps normal auth working.
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
                "--safe-mode",
                "--disallowedTools",
                _DISALLOWED_TOOLS,
            ],
            system_prompt_flag="--system-prompt",
            envelope_key="result",
            timeout=timeout,
            cwd=Path(tempfile.gettempdir()),
        )
