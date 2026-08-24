"""Root `cli` click group. Every command module in this package registers onto it."""

import click

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.group(context_settings=CONTEXT_SETTINGS)
def cli() -> None:
    """LeetCode notes generator."""
