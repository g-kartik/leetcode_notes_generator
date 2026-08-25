"""Helpers shared across more than one command module."""

import random
import time

import click
import structlog

from modules.leetcode.pipeline import LeetCodeSyncManager

logger = structlog.get_logger(__name__)

_manager_instance: LeetCodeSyncManager | None = None


def get_manager() -> LeetCodeSyncManager:
    """Lazily builds the shared sync manager, so `--help` never touches disk/network setup."""
    global _manager_instance
    if _manager_instance is None:
        logger.info("sync_manager_initialized")
        _manager_instance = LeetCodeSyncManager()
    return _manager_instance


class CircuitBreaker:
    """Trips after too many consecutive failures in a batch loop.

    Guards against grinding through hundreds of remaining slugs once we're
    actually being rate-limited or blocked rather than hitting isolated,
    one-off errors — a stray failure resets the counter, but a sustained run
    of them trips it so the caller can stop early instead of burning through
    the rest of the batch on a lost cause.
    """

    def __init__(self, max_consecutive_failures: int):
        self.max_consecutive_failures = max_consecutive_failures
        self._consecutive_failures = 0

    def record(self, failed: bool) -> None:
        self._consecutive_failures = self._consecutive_failures + 1 if failed else 0

    @property
    def tripped(self) -> bool:
        if self.max_consecutive_failures <= 0:
            return False  # disabled
        return self._consecutive_failures >= self.max_consecutive_failures


class BatchPacer:
    """Inserts a randomized cooldown after every `batch_size` items in a big
    --all run.

    Without this, a large backlog (e.g. hundreds of pending problems) runs as
    one long, uninterrupted burst of requests — itself a suspicious traffic
    shape regardless of error rate. Breaking it into several short,
    human-shaped sessions automatically means the user doesn't have to
    babysit and re-invoke the command themselves to get the same effect.
    """

    def __init__(self, batch_size: int, cooldown_range: tuple[float, float] = (60, 120)):
        self.batch_size = batch_size
        self.cooldown_range = cooldown_range

    def should_pause_after(self, position: int, total: int) -> bool:
        """`position` is 1-based — the count of items processed so far."""
        if self.batch_size <= 0 or position >= total:
            return False
        return position % self.batch_size == 0

    def pause(self, stage: str, position: int, total: int) -> None:
        """Sleeps a random duration within `cooldown_range`, logging + echoing progress."""
        duration = random.uniform(*self.cooldown_range)
        batch_num = position // self.batch_size
        total_batches = -(-total // self.batch_size)  # ceil division

        logger.info(
            "populate_batch_cooldown_started",
            stage=stage,
            batch=batch_num,
            total_batches=total_batches,
            seconds=round(duration, 1),
        )
        click.echo(
            f"\n[pause] batch {batch_num}/{total_batches} done for '{stage}' — "
            f"cooling down {duration:.0f}s before continuing..."
        )
        time.sleep(duration)


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
