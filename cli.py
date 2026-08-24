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

if __name__ == "__main__":
    configure_logging()
    cli()
