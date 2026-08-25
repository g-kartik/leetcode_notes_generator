"""Root `cli` click group. Every command module in this package registers onto it."""

from collections.abc import Iterator

import click

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


def _iter_full_help(command: click.Command, ctx: click.Context) -> Iterator[str]:
    """Yields the formatted --help text for `command`, then recurses into every subcommand.

    `ctx.command_path` (used in each help text's "Usage:" line) is built by Click
    by walking the `parent` chain, so each child context's `info_name` must be
    just its own segment (e.g. "cache"), not an already-accumulated full path —
    Click does that concatenation itself.
    """
    yield command.get_help(ctx)
    if isinstance(command, click.Group):
        for name in sorted(command.list_commands(ctx)):
            sub_command = command.get_command(ctx, name)
            if sub_command is None:
                continue
            sub_ctx = click.Context(sub_command, info_name=name, parent=ctx)
            yield from _iter_full_help(sub_command, sub_ctx)


def _print_full_help(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return
    for help_text in _iter_full_help(ctx.command, ctx):
        click.echo(help_text)
        click.echo()
    ctx.exit()


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option(
    "-H", "--help-all",
    is_flag=True, is_eager=True, expose_value=False, callback=_print_full_help,
    help="Show help for this command and every subcommand, recursively, then exit.",
)
def cli() -> None:
    """LeetCode notes generator."""
