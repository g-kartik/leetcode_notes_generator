"""`notes` command: render a stored question into a personal study-notes file."""

from pathlib import Path

import click
import structlog

from modules.render.markdown_notes import LeetCodeDSAProblemNotesRender
from modules.render.utils import FileVariant, NotesStyle

from .common import get_manager, print_batch_summary
from .root import cli

logger = structlog.get_logger(__name__)

_AI_STYLES = {NotesStyle.PLAIN_AI.value, NotesStyle.OBSIDIAN_AI.value}


@cli.command()
@click.argument("slug", required=False)
@click.option(
    "--all", "run_all", is_flag=True,
    help="Render notes for every slug that already has problem data populated.",
)
@click.option(
    "--style",
    type=click.Choice([s.value for s in NotesStyle]),
    default=NotesStyle.PLAIN.value,
    show_default=True,
    help="'plain' and 'obsidian' are implemented; the '+ai' styles are reserved for a later prefill step.",
)
@click.option(
    "--link-variant",
    type=click.Choice([FileVariant.REMOTE.value, FileVariant.LOCAL.value]),
    default=FileVariant.REMOTE.value,
    show_default=True,
    help="Which already-rendered problem file variant the note links to.",
)
@click.option(
    "--output-base", "output_base", type=click.Path(path_type=Path), default=None,
    help="Defaults to render_settings.DEFAULT_WRITE_DIR.",
)
@click.option("--obsidian/--no-obsidian", "obsidian", default=False)
def notes(
    slug: str | None,
    run_all: bool,
    style: str,
    link_variant: str,
    output_base: Path | None,
    obsidian: bool,
) -> None:
    """Render a stored question into a study-notes file (frontmatter + problem link only, for now)."""
    if slug and run_all:
        raise click.UsageError("Pass either SLUG or --all, not both.")
    if not slug and not run_all:
        raise click.UsageError("Pass either SLUG or --all.")
    if style in _AI_STYLES:
        raise click.ClickException(
            f"'{style}' is not implemented yet — AI prefill is a later task. "
            f"Use '{NotesStyle.PLAIN.value}' or '{NotesStyle.OBSIDIAN.value}' for now."
        )

    mgr = get_manager()
    renderer = LeetCodeDSAProblemNotesRender(
        style=NotesStyle(style),
        output_base=output_base,
        write_to_obsidian_vault=obsidian,
        link_variant=FileVariant(link_variant),
    )

    if slug:
        with structlog.contextvars.bound_contextvars(slug=slug, stage="notes"):
            log = logger.bind()
            record = mgr.storage.get_combined_by_slug(slug)
            if record is None or not record.raw_question_html:
                log.warning("notes_command_skipped", reason="no_problem_data_stored")
                raise click.ClickException(f"no problem data found for '{slug}', run 'populate problem {slug}' first")
            log.info("notes_command_started")
            renderer.save(record)
            log.info("notes_command_succeeded")
            click.echo(f"[done] notes({style}) {slug}")
        return

    records = [r for r in mgr.storage.list_all_combined() if r.raw_question_html]
    if not records:
        logger.info("notes_command_batch_completed", stage="notes", reason="no_problem_data_stored")
        click.echo("Nothing to render — no slugs have problem data populated yet.")
        return

    logger.info("notes_command_batch_started", stage="notes", record_count=len(records))
    succeeded, failed = [], []
    for record in records:
        with structlog.contextvars.bound_contextvars(slug=record.slug, stage="notes"):
            try:
                renderer.save(record)
            except Exception as exc:
                logger.exception("notes_command_failed")
                click.echo(f"[fail] {record.slug}: {exc}")
                failed.append(record.slug)
            else:
                logger.info("notes_command_succeeded")
                click.echo(f"[done] {record.slug}")
                succeeded.append(record.slug)

    logger.info(
        "notes_command_batch_completed",
        stage="notes",
        succeeded_count=len(succeeded),
        failed_count=len(failed),
    )
    print_batch_summary(succeeded, failed)
