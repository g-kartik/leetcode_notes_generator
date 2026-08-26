"""
CLI command implementations for the LeetCode notes generator, split by area:
problems (data fetch + pending cache, db, render, recent), notes, solve.
Importing this package registers every subcommand onto the root `cli` group
defined in `root.py`.
"""

from .root import cli

from . import (  # noqa: F401  (side effect: registers commands onto `cli`)
    notes,
    problems,
    problems_data,
    problems_db,
    problems_recent,
    problems_render,
    solve,
)

__all__ = ["cli"]
