"""`render` command: render a stored question into Markdown notes."""

from pathlib import Path

import click
import structlog

from modules.render.markdown_problem import LeetCodeDSAProblemMarkdownRender
from modules.render.utils import FileVariant

from .common import get_manager, print_batch_summary
from .root import cli

logger = structlog.get_logger(__name__)


@cli.command()
@click.argument("slug", required=False)
@click.option(
    "--all", "run_all", is_flag=True,
    help="Render every slug that already has problem data populated.",
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
        with structlog.contextvars.bound_contextvars(slug=slug, stage="render"):
            log = logger.bind()
            record = mgr.storage.get_combined_by_slug(slug)
            if record is None or not record.raw_question_html:
                log.warning("render_command_skipped", reason="no_problem_data_stored")
                raise click.ClickException(f"no problem data found for '{slug}', run 'populate problem {slug}' first")
            log.info("render_command_started")
            renderer.save(record)
            log.info("render_command_succeeded")
            click.echo(f"[done] rendered {slug}")
        return

    records = [r for r in mgr.storage.list_all_combined() if r.raw_question_html]
    if not records:
        logger.info("render_command_batch_completed", stage="render", reason="no_problem_data_stored")
        click.echo("Nothing to render — no slugs have problem data populated yet.")
        return

    logger.info("render_command_batch_started", stage="render", record_count=len(records))
    succeeded, failed = [], []
    for record in records:
        with structlog.contextvars.bound_contextvars(slug=record.slug, stage="render"):
            try:
                renderer.save(record)
            except Exception as exc:
                logger.exception("render_command_failed")
                click.echo(f"[fail] {record.slug}: {exc}")
                failed.append(record.slug)
            else:
                logger.info("render_command_succeeded")
                click.echo(f"[done] {record.slug}")
                succeeded.append(record.slug)

    logger.info(
        "render_command_batch_completed",
        stage="render",
        succeeded_count=len(succeeded),
        failed_count=len(failed),
    )
    print_batch_summary(succeeded, failed)
