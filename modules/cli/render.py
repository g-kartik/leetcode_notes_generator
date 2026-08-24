"""`render` command: render a stored question into Markdown notes."""

from pathlib import Path

import click

from modules.render.markdown_problem import LeetCodeDSAProblemMarkdownRender
from modules.render.utils import FileVariant

from .common import get_manager, print_batch_summary
from .root import cli


@cli.command()
@click.argument("slug", required=False)
@click.option(
    "--all", "run_all", is_flag=True,
    help="Render every slug that already has metadata populated.",
)
@click.option(
    "--variant",
    type=click.Choice([v.value for v in FileVariant]),
    default=FileVariant.ALL.value,
    show_default=True,
)
@click.option(
    "--output-base", "output_base", type=click.Path(path_type=Path), default=None,
    help="Defaults to render_settings.DEFAULT_WRITE_DIR.",
)
@click.option("--obsidian/--no-obsidian", "obsidian", default=False)
def render(
    slug: str | None,
    run_all: bool,
    variant: str,
    output_base: Path | None,
    obsidian: bool,
) -> None:
    """Render a stored question into Markdown notes."""
    if slug and run_all:
        raise click.UsageError("Pass either SLUG or --all, not both.")
    if not slug and not run_all:
        raise click.UsageError("Pass either SLUG or --all.")

    mgr = get_manager()
    renderer = LeetCodeDSAProblemMarkdownRender(
        variant=FileVariant(variant),
        output_base=output_base,
        write_to_obsidian_vault=obsidian,
    )

    if slug:
        record = mgr.storage.get_combined_by_slug(slug)
        if record is None or not record.raw_question_html:
            raise click.ClickException(f"no metadata found for '{slug}', run 'populate metadata {slug}' first")
        renderer.save(record)
        click.echo(f"[done] rendered {slug}")
        return

    records = [r for r in mgr.storage.list_all_combined() if r.raw_question_html]
    if not records:
        click.echo("Nothing to render — no slugs have metadata populated yet.")
        return

    succeeded, failed = [], []
    for record in records:
        try:
            renderer.save(record)
        except Exception as exc:
            click.echo(f"[fail] {record.slug}: {exc}")
            failed.append(record.slug)
        else:
            click.echo(f"[done] {record.slug}")
            succeeded.append(record.slug)

    print_batch_summary(succeeded, failed)
