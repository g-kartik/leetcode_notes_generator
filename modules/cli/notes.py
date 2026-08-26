"""`notes` command group: render personal study-notes files, and generate
AI prefill content (pattern/core idea/invariant/...) for them."""

import time
from pathlib import Path

import click
import structlog

from modules.ai_prefill import AIPrefillGenerator, AIProviderError, PrefillGenerationError
from modules.ai_prefill.settings import ai_prefill_settings
from modules.render.markdown_notes import LeetCodeDSAProblemNotesRender, PrefillMissingError
from modules.render.utils import AI_STYLE, NotesStyle

from .common import CircuitBreaker, get_manager, print_batch_summary
from .picker import label_records, pick_slugs
from .root import cli

logger = structlog.get_logger(__name__)


@cli.group()
def notes() -> None:
    """Render personal study-notes files, and generate AI prefill content for them."""


@notes.command("render")
@click.argument("slug", required=False)
@click.option(
    "--all",
    "run_all",
    is_flag=True,
    help="Render notes for every slug that already has problem data populated.",
)
@click.option(
    "--style",
    type=click.Choice([NotesStyle.PLAIN.value, NotesStyle.OBSIDIAN.value]),
    default=NotesStyle.PLAIN.value,
    show_default=True,
    help="Base notes style. With --ai, the '+ai' variant of this is used instead.",
)
@click.option(
    "--ai", is_flag=True,
    help="Pull in the latest stored AI prefill content for this slug and "
    "render the '+ai' variant of --style using it. Run 'notes prefill SLUG' "
    "first, or generation fails with a clear error.",
)
@click.option(
    "--output-base",
    "output_base",
    type=click.Path(path_type=Path),
    default=None,
    help="Priority: this flag > OUTPUT_BASE_DIR (.env) > render_settings.DEFAULT_WRITE_DIR.",
)
@click.option(
    "--force", is_flag=True,
    help="Regenerate even if a notes file already exists — the existing file "
    "is backed up first (Leetcode Notes/backups/<id>-<slug>/), since it "
    "may contain hand-written content.",
)
def notes_render(
    slug: str | None,
    run_all: bool,
    style: str,
    ai: bool,
    output_base: Path | None,
    force: bool,
) -> None:
    """Render a stored question into a study-notes file (frontmatter + problem link only, for now).

    The note always links whichever problem file variant was actually
    rendered for it — local when the problem has downloaded images, remote
    otherwise (see LeetCodeDSAProblemMarkdownRender). Omit both SLUG and
    --all to pick interactively instead — a searchable, multi-select prompt
    over every slug with problem data populated.
    """
    if slug and run_all:
        raise click.UsageError("Pass either SLUG or --all, not both.")

    mgr = get_manager()
    target_style = AI_STYLE[NotesStyle(style)] if ai else NotesStyle(style)
    renderer = LeetCodeDSAProblemNotesRender(
        style=target_style,
        output_base=output_base,
    )

    if slug:
        with structlog.contextvars.bound_contextvars(slug=slug, stage="notes"):
            log = logger.bind()
            record = mgr.storage.get_combined_by_slug(slug)
            if record is None or not record.raw_question_html:
                log.warning("notes_command_skipped", reason="no_problem_data_stored")
                raise click.ClickException(
                    f"no problem data found for '{slug}', run 'problems data fetch {slug}' first"
                )
            log.info("notes_command_started")
            try:
                _, status = renderer.save(record, force=force)
            except PrefillMissingError as exc:
                log.warning("notes_command_failed", reason="prefill_missing")
                raise click.ClickException(str(exc))
            log.info("notes_command_succeeded", status=status)
            label = "done" if status == "written" else "skip"
            suffix = (
                ""
                if status == "written"
                else " (already exists, use --force to regenerate)"
            )
            click.echo(f"[{label}] notes({target_style.value}) {slug}{suffix}")
        return

    records = [r for r in mgr.storage.list_all_combined() if r.raw_question_html]

    if not run_all:
        if not records:
            click.echo("Nothing to pick from — no slugs have problem data populated yet.")
            return
        picked = pick_slugs(label_records(records))
        if not picked:
            click.echo("Nothing selected.")
            return
        records = [r for r in records if r.slug in picked]

    if not records:
        logger.info(
            "notes_command_batch_completed",
            stage="notes",
            reason="no_problem_data_stored",
        )
        click.echo("Nothing to render — no slugs have problem data populated yet.")
        return

    logger.info("notes_command_batch_started", stage="notes", record_count=len(records))
    succeeded, skipped, failed = [], [], []
    for record in records:
        with structlog.contextvars.bound_contextvars(slug=record.slug, stage="notes"):
            try:
                _, status = renderer.save(record, force=force)
            except Exception as exc:
                logger.exception("notes_command_failed")
                click.echo(f"[fail] {record.slug}: {exc}")
                failed.append(record.slug)
            else:
                logger.info("notes_command_succeeded", status=status)
                if status == "written":
                    click.echo(f"[done] {record.slug}")
                    succeeded.append(record.slug)
                else:
                    click.echo(
                        f"[skip] {record.slug} (already exists, use --force to regenerate)"
                    )
                    skipped.append(record.slug)

    logger.info(
        "notes_command_batch_completed",
        stage="notes",
        succeeded_count=len(succeeded),
        skipped_count=len(skipped),
        failed_count=len(failed),
    )
    print_batch_summary(succeeded, failed, skipped)


@notes.command("prefill")
@click.argument("slug", required=False)
@click.option(
    "--all",
    "run_all",
    is_flag=True,
    help="Generate prefill content for every slug that already has problem data populated.",
)
@click.option(
    "--force", is_flag=True,
    help="Generate a new version even if prefill content already exists for this "
    "slug. Prior versions are kept either way — see AIPrefillStorage.",
)
@click.option(
    "--no-rate-limit", "no_rate_limit", is_flag=True,
    help="With --all, skip the AI_PREFILL_RATE_LIMIT_SECONDS pause between "
    "generations. Only worth it on a plan without tight usage limits.",
)
@click.option(
    "--limit",
    "limit",
    type=int,
    default=None,
    help="With --all, cap the run to at most this many slugs.",
)
@click.option(
    "--max-failures",
    "max_failures",
    type=int,
    default=5,
    show_default=True,
    help="With --all, abort the run after this many consecutive failures. 0 disables.",
)
def notes_prefill(
    slug: str | None,
    run_all: bool,
    force: bool,
    no_rate_limit: bool,
    limit: int | None,
    max_failures: int,
) -> None:
    """Generate AI prefill content (pattern/core idea/invariant/...) for stored problem(s).

    Uses whichever CLI AI tool is configured via AI_PREFILL_PROVIDER (Claude
    Code's `claude -p` by default — see modules/ai_prefill/providers). Every
    generation is appended to that slug's version history rather than
    overwriting a previous attempt.

    Omit both SLUG and --all to pick interactively instead — a searchable,
    multi-select prompt over every slug with problem data populated.
    """
    if slug and run_all:
        raise click.UsageError("Pass either SLUG or --all, not both.")

    mgr = get_manager()
    generator = AIPrefillGenerator()
    delay = 0.0 if no_rate_limit else ai_prefill_settings.RATE_LIMIT_SECONDS

    if slug:
        with structlog.contextvars.bound_contextvars(slug=slug, stage="prefill"):
            log = logger.bind()
            record = mgr.storage.get_combined_by_slug(slug)
            if record is None or not record.raw_question_html:
                log.warning("prefill_command_skipped", reason="no_problem_data_stored")
                raise click.ClickException(
                    f"no problem data found for '{slug}', run 'problems data fetch {slug}' first"
                )
            if not force and generator.storage.exists(slug):
                log.info("prefill_command_skipped", reason="prefill_already_exists")
                click.echo(
                    f"[skip] prefill {slug} (already has prefill content, "
                    f"use --force to add another version)"
                )
                return
            try:
                generator.generate(record)
            except (AIProviderError, PrefillGenerationError) as exc:
                log.warning("prefill_command_failed", error=str(exc))
                raise click.ClickException(f"prefill generation failed for '{slug}': {exc}")
            log.info("prefill_command_succeeded")
            click.echo(f"[done] prefill {slug}")
        return

    records = [r for r in mgr.storage.list_all_combined() if r.raw_question_html]

    if run_all:
        if limit:
            records = records[:limit]
    else:
        if not records:
            click.echo("Nothing to pick from — no slugs have problem data populated yet.")
            return
        picked = pick_slugs(label_records(records))
        if not picked:
            click.echo("Nothing selected.")
            return
        records = [r for r in records if r.slug in picked]

    if not records:
        logger.info("prefill_command_batch_completed", reason="no_problem_data_stored")
        click.echo("Nothing to do — no slugs have problem data populated yet.")
        return

    logger.info("prefill_command_batch_started", record_count=len(records))
    succeeded, skipped, failed = [], [], []
    breaker = CircuitBreaker(max_failures)
    total = len(records)
    for idx, record in enumerate(records):
        with structlog.contextvars.bound_contextvars(slug=record.slug, stage="prefill"):
            if not force and generator.storage.exists(record.slug):
                click.echo(
                    f"[skip] {record.slug} (already has prefill content, "
                    f"use --force to add another version)"
                )
                skipped.append(record.slug)
                breaker.record(False)
            else:
                try:
                    generator.generate(record)
                except (AIProviderError, PrefillGenerationError) as exc:
                    logger.exception("prefill_command_failed")
                    click.echo(f"[fail] {record.slug}: {exc}")
                    failed.append(record.slug)
                    breaker.record(True)
                else:
                    click.echo(f"[done] {record.slug}")
                    succeeded.append(record.slug)
                    breaker.record(False)
                    if delay and idx < total - 1:
                        time.sleep(delay)

        if breaker.tripped:
            remaining = total - idx - 1
            logger.warning(
                "prefill_batch_aborted",
                reason="too_many_consecutive_failures",
                max_consecutive_failures=max_failures,
                remaining_slug_count=remaining,
            )
            click.echo(
                f"\n[abort] {max_failures} consecutive failures — stopping early, "
                f"{remaining} slug(s) left unprocessed."
            )
            break

    logger.info(
        "prefill_command_batch_completed",
        succeeded_count=len(succeeded),
        skipped_count=len(skipped),
        failed_count=len(failed),
    )
    print_batch_summary(succeeded, failed, skipped)
