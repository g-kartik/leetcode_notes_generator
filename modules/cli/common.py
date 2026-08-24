"""Helpers shared across more than one command module."""

import click

from modules.leetcode.pipeline import LeetCodeSyncManager

_manager_instance: LeetCodeSyncManager | None = None


def get_manager() -> LeetCodeSyncManager:
    """Lazily builds the shared sync manager, so `--help` never touches disk/network setup."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = LeetCodeSyncManager()
    return _manager_instance


def print_batch_summary(
    succeeded: list[str], failed: list[str], skipped: list[str] | None = None
) -> None:
    """Prints a one-line succeeded/skipped/failed summary for a batch command run."""
    parts = [f"{len(succeeded)} succeeded"]
    if skipped is not None:
        parts.append(f"{len(skipped)} skipped")
    parts.append(f"{len(failed)} failed")
    summary = ", ".join(parts)
    if failed:
        summary += f": {failed}"
    click.echo(f"\n{summary}")
