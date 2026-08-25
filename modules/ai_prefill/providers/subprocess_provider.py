import json
import subprocess
from pathlib import Path

from .base import AIProvider, AIProviderError


class SubprocessJSONProvider(AIProvider):
    """
    Generic adapter for any CLI-based AI tool: runs a fixed argv, sends the
    prompt on stdin, and returns stdout — optionally unwrapping a JSON
    envelope first (e.g. Claude Code's `claude -p --output-format json`
    wraps the real answer inside {"result": "..."}).

    This is what makes providers pluggable without writing new Python code:
    point AI_PREFILL_COMMAND at any other CLI model runner (ollama, llm, a
    local script...) via settings/env, and this class drives it. A tool
    needing genuinely different behavior (auth handshake, no stdin support,
    a non-JSON envelope) can still subclass AIProvider directly instead.
    """

    name = "command"

    def __init__(
        self,
        command: list[str],
        *,
        system_prompt_flag: str | None = None,
        envelope_key: str | None = None,
        timeout: float = 120.0,
        cwd: Path | None = None,
    ):
        if not command:
            raise ValueError("command must be a non-empty argv list")
        self.command = command
        self.system_prompt_flag = system_prompt_flag
        self.envelope_key = envelope_key
        self.timeout = timeout
        self.cwd = cwd

    def _build_argv(self, system_prompt: str) -> list[str]:
        argv = list(self.command)
        if self.system_prompt_flag:
            argv += [self.system_prompt_flag, system_prompt]
        return argv

    def _stdin_payload(self, system_prompt: str, user_prompt: str) -> str:
        # No dedicated system-prompt flag configured for this tool — fold it
        # into stdin instead of silently dropping it.
        if self.system_prompt_flag:
            return user_prompt
        return f"{system_prompt}\n\n{user_prompt}"

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        argv = self._build_argv(system_prompt)
        stdin_payload = self._stdin_payload(system_prompt, user_prompt)

        try:
            result = subprocess.run(
                argv,
                input=stdin_payload,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.cwd,
            )
        except subprocess.TimeoutExpired as exc:
            raise AIProviderError(f"'{argv[0]}' timed out after {self.timeout}s") from exc
        except FileNotFoundError as exc:
            raise AIProviderError(f"'{argv[0]}' not found on PATH") from exc

        if result.returncode != 0:
            raise AIProviderError(
                f"'{argv[0]}' exited {result.returncode}: {result.stderr.strip()[:500]}"
            )

        raw = result.stdout.strip()
        if not raw:
            raise AIProviderError(f"'{argv[0]}' produced no output")

        if self.envelope_key:
            try:
                envelope = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise AIProviderError(f"expected a JSON envelope, got: {raw[:500]}") from exc
            raw = envelope.get(self.envelope_key)
            if not raw:
                raise AIProviderError(f"envelope missing '{self.envelope_key}' key: {envelope}")

        return raw
