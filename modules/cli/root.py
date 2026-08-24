"""Root `cli` click group. Every command module in this package registers onto it."""

import click


@click.group()
def cli() -> None:
    """LeetCode notes generator."""
