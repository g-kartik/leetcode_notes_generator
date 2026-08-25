"""Command-line interface entrypoint for the LeetCode notes generator.

Thin wrapper around `LeetCodeSyncManager` (fetch/store) and
`LeetCodeDSAProblemMarkdownRender` (render). All commands are safe to re-run:
each `populate` step only does network work when the target data is missing
or `--force` is passed.

Command implementations live in `modules/cli/`, split by area: sync,
populate, render, cache, db.
"""

from logging_config import configure_logging
from modules.cli import cli

# Fixed regardless of how this file is actually invoked (`python cli.py`,
# `uv run python cli.py`, a symlink, ...), so shell tab-completion (see
# shell/leetnotes.fish) always binds to the same command name. Purely
# cosmetic otherwise — it only changes what --help calls itself.
PROG_NAME = "leetnotes"

if __name__ == "__main__":
    configure_logging()
    cli(prog_name=PROG_NAME)
