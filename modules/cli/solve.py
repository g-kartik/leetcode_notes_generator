"""`solve` command: the "I just solved this, get me a ready note" one-shot
pipeline. Chains the steps that otherwise have to be typed out by hand —
`problems data fetch --part description/images/submission`, `problems
render`, optionally `notes prefill`, and `notes render` — for one or more
slugs.

Each underlying step is still independently idempotent/resumable (see
CLAUDE.md's three-part pipeline and modules/leetcode/pipeline.py), so `solve`
is just a thin sequencing layer on top of them: it's always safe to re-run,
and never re-does work that's already done unless --force is passed.
"""

import time
from pathlib import Path

import click
import structlog

from modules.ai_prefill import AIPrefillGenerator, AIProviderError, PrefillGenerationError
from modules.ai_prefill.settings import ai_prefill_settings
from modules.leetcode.pipeline import LeetCodeSyncManager
from modules.render.markdown_notes import LeetCodeDSAProblemNotesRender
from modules.render.markdown_problem import LeetCodeDSAProblemMarkdownRender
from modules.render.utils import AI_STYLE, NotesStyle

from .common import CircuitBreaker, get_manager, print_batch_summary
from .picker import label_slugs, pick_slugs
from .root import cli

logger = structlog.get_logger(__name__)


def _candidate_slugs(mgr: LeetCodeSyncManager) -> list[str]:
    """Every slug worth offering: still-pending ones, plus everything already
    in the DB — re-running solve on an already-done slug is a safe refresh,
    not an error, so it stays offered too."""
    pending = set(mgr.storage.read_pending_cache().keys())
    done = {r.slug for r in mgr.storage.list_all() if r.slug}
    return sorted(pending | done)


def _solve_one(
    mgr: LeetCodeSyncManager,
    slug: str,
    *,
    style: NotesStyle,
    output_base: Path | None,
    force: bool,
    ai: bool,
    rate_limit_delay: float,
) -> str:
    """Runs the full pipeline for one slug. Returns the final notes save
    status ('written'/'skipped'). Raises if problem metadata genuinely
    couldn't be fetched — nothing downstream can proceed without it."""
    log = logger.bind(slug=slug)

    click.echo("  -> fetch description/images/submission")
    mgr.populate_question_metadata(slug, force_update=force)
    record = mgr.storage.problems_get_by_slug(slug)
    if record is None or not record.raw_question_html:
        raise RuntimeError("could not fetch problem metadata")
    mgr.populate_question_images(slug, force_update=force)
    mgr.populate_submission_code(slug, force_update=force)

    combined = mgr.storage.get_combined_by_slug(slug)

    click.echo("  -> render problem file")
    LeetCodeDSAProblemMarkdownRender(output_base=output_base).save(combined)

    target_style = style
    if ai:
        generator = AIPrefillGenerator()
        if force or not generator.storage.exists(slug):
            click.echo("  -> generating AI prefill content...")
            try:
                generator.generate(combined)
            except (AIProviderError, PrefillGenerationError) as exc:
                log.warning("solve_prefill_failed", error=str(exc))
                click.echo(f"     (failed: {exc})")
            else:
                if rate_limit_delay:
                    time.sleep(rate_limit_delay)
        if generator.storage.exists(slug):
            target_style = AI_STYLE[style]
        else:
            log.warning("solve_ai_style_skipped", reason="no_prefill_content_available")
            click.echo("     (no prefill content available — writing without it)")

    click.echo(f"  -> render notes file ({target_style.value})")
    notes_renderer = LeetCodeDSAProblemNotesRender(
        style=target_style, output_base=output_base
    )
    _, status = notes_renderer.save(combined, force=force)
    return status


@cli.command()
@click.argument("slug", required=False)
@click.option(
    "--all", "run_all", is_flag=True,
    help="Run for every known slug (pending or already-populated). Can be a "
    "long-running batch, especially combined with --ai — consider picking "
    "interactively (omit both SLUG and --all) instead for anything but a "
    "small backlog.",
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
    help="Also generate AI prefill content (if not already generated) and "
    "render the '+ai' variant of --style using it.",
)
@click.option(
    "--output-base", "output_base", type=click.Path(path_type=Path), default=None,
    help="Priority: this flag > OUTPUT_BASE_DIR (.env) > render_settings.DEFAULT_WRITE_DIR.",
)
@click.option(
    "--force", is_flag=True,
    help="Refetch/re-render every step even if already done. For the notes "
    "file specifically, the existing one is backed up first (same as "
    "'notes render --force').",
)
@click.option(
    "--no-rate-limit", "no_rate_limit", is_flag=True,
    help="With --ai, skip the AI_PREFILL_RATE_LIMIT_SECONDS pause between AI generations.",
)
@click.option(
    "--max-failures", "max_failures", type=int, default=5, show_default=True,
    help="With --all, abort the run after this many consecutive failures. 0 disables.",
)
def solve(
    slug: str | None,
    run_all: bool,
    style: str,
    ai: bool,
    output_base: Path | None,
    force: bool,
    no_rate_limit: bool,
    max_failures: int,
) -> None:
    """Populate, render, and note a problem in one go — the "I just solved
    this" command. Omit both SLUG and --all to pick interactively.
    """
    if slug and run_all:
        raise click.UsageError("Pass either SLUG or --all, not both.")

    mgr = get_manager()
    rate_limit_delay = 0.0 if no_rate_limit else ai_prefill_settings.RATE_LIMIT_SECONDS
    kwargs = dict(
        style=NotesStyle(style),
        output_base=output_base,
        force=force,
        ai=ai,
        rate_limit_delay=rate_limit_delay,
    )

    if slug:
        with structlog.contextvars.bound_contextvars(slug=slug, stage="solve"):
            log = logger.bind()
            log.info("solve_command_started")
            try:
                status = _solve_one(mgr, slug, **kwargs)
            except Exception as exc:
                log.warning("solve_command_failed", error=str(exc))
                raise click.ClickException(f"could not solve '{slug}': {exc}")
            log.info("solve_command_succeeded", status=status)
            click.echo(f"[{'done' if status == 'written' else 'skip'}] solve {slug}")
        return

    if run_all:
        slugs = _candidate_slugs(mgr)
        if not slugs:
            click.echo("Nothing to do — no known slugs.")
            return
    else:
        candidates = _candidate_slugs(mgr)
        if not candidates:
            click.echo("Nothing to pick from — no known slugs.")
            return
        known = {r.slug: r for r in mgr.storage.list_all() if r.slug}
        slugs = pick_slugs(label_slugs(candidates, known))
        if not slugs:
            click.echo("Nothing selected.")
            return

    logger.info("solve_batch_started", slug_count=len(slugs))
    succeeded, failed = [], []
    breaker = CircuitBreaker(max_failures)
    total = len(slugs)
    for idx, target_slug in enumerate(slugs):
        click.echo(f"[{idx + 1}/{total}] {target_slug}")
        with structlog.contextvars.bound_contextvars(slug=target_slug, stage="solve"):
            try:
                status = _solve_one(mgr, target_slug, **kwargs)
            except Exception as exc:
                logger.exception("solve_command_failed")
                click.echo(f"  [fail] {exc}")
                failed.append(target_slug)
                breaker.record(True)
            else:
                click.echo(f"  [{'done' if status == 'written' else 'skip'}]")
                succeeded.append(target_slug)
                breaker.record(False)

        if breaker.tripped:
            remaining = total - idx - 1
            logger.warning(
                "solve_batch_aborted",
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
        "solve_batch_completed",
        succeeded_count=len(succeeded),
        failed_count=len(failed),
    )
    print_batch_summary(succeeded, failed)
