"""
CLI command implementations for the LeetCode notes generator, split by area:
sync, populate, render, notes, cache, db, recent. Importing this package
registers every subcommand onto the root `cli` group defined in `root.py`.
"""

from .root import cli

from . import cache, db, notes, populate, recent, render, sync  # noqa: F401  (side effect: registers commands onto `cli`)

__all__ = ["cli"]
