# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A pipeline that syncs a user's solved LeetCode problems (via LeetCode's REST + GraphQL
endpoints), stores them as structured JSON, renders them as Markdown notes — optionally
mirrored into an Obsidian vault — and can prefill personal study-notes content via a
pluggable AI provider. Driven by a `click`-based CLI (`cli.py`).

## Commands

- Install deps: `uv sync`
- Run the CLI: `uv run python cli.py <command> ...`, or `uv run python -m <module>` /
  `uv run python -c "..."` for one-off scripting against the library directly, e.g.:
  ```python
  from modules.sync.pipeline import LeetCodeSyncManager
  mgr = LeetCodeSyncManager()
  result = mgr.sync_pending_cache()
  ```
- `uv run python cli.py -H` (or `--help-all`) prints help for every command and subcommand,
  recursively, with a visible separator line between each block — the fastest way to see the
  whole command tree at once. `uv run python cli.py <command> -h` for one command's help.
- `shell/leetnotes` + `shell/README.md`: an optional wrapper executable + shell-completion
  setup so `leetnotes <TAB>` works from any directory (see that README for setup). Click
  generates the completion script dynamically from whatever commands are registered, so it
  never goes stale — no code changes needed there when commands change.
- No test suite and no lint/type-check config exist in this repo yet — don't assume `pytest`,
  `ruff`, or `mypy` are configured; check `pyproject.toml` before inventing commands.
- Requires Python >=3.14 (managed via `uv`, see `uv.lock`).

## Configuration

Settings are `pydantic-settings` classes reading from a single root `.env` file (gitignored —
see `.env.example` for every field; it's a template only, never loaded at runtime). Every field
already has a sensible default baked into its settings class, so `.env` only needs an entry for
a value you're actually overriding on this machine/account — secrets
(`LEETCODE_SESSION`/`LEETCODE_CSRF_TOKEN`) included, since there's nowhere else they could go,
but also anything else that's genuinely personal/machine-specific (e.g. `OUTPUT_BASE_DIR`).
Don't add a project-wide default to a committed file — if a default is worth changing for
everyone, change the field's default in its settings class instead, like any other code change.
`settings.py` (repo root) defines `BaseProjectSettings`, which fixes `PROJECT_ROOT_DIR` and the
shared `model_config`. Every module-level settings class subclasses it and adds its own
`env_prefix`:

- `modules/leetcode/settings.py` — `LeetCodeSettings` (`env_prefix="LEETCODE_"`): auth
  (`SESSION`, `CSRF_TOKEN` cookies copied from an authenticated browser session against
  leetcode.com, plus an optional `USERNAME` used only by the recent-accepted-submissions
  query), and on-disk paths for the JSON "database" and cached assets under
  `LEETCODE_DATA/dsa_problems/` — `problems.json`, `submissions.json`,
  `solved_slugs_cache.json`, `assets/`.
- `modules/render/settings.py` — `RendererSettings`: template dir (`resources/templates/` at
  the repo root), default output dir (`LOCAL_RENDER/` in the project root), and an optional
  `OUTPUT_BASE_DIR` override (no `LEETCODE_` prefix — a different env var namespace than the
  leetcode settings). Base-dir resolution priority, via `RendererSettings.resolve_base_dir()`:
  a CLI `--output-base` > `OUTPUT_BASE_DIR` (.env) > `DEFAULT_WRITE_DIR`. Point
  `OUTPUT_BASE_DIR` at (a folder inside) an Obsidian vault to have problems/notes render
  straight into it — there's no separate vault-mirroring mechanism. `DEFAULT_NOTES_STYLE`
  (`plain` or `obsidian`) sets the default for `notes render --style`, same override priority
  (CLI `--style` > `DEFAULT_NOTES_STYLE` (.env) > `"plain"`).
- `modules/ai_prefill/settings.py` — `AIPrefillSettings` (`env_prefix="AI_PREFILL_"`): which
  `AIProvider` to use (`PROVIDER`, default `claude_code` — shells out to `claude -p`, billed
  against the Claude Code subscription; `command` is a generic escape hatch for any other CLI
  AI tool), rate-limit/timeout knobs, and its own JSON store path (`ai_prefill.json`).

When adding a new module that needs config, follow this same pattern: subclass
`BaseProjectSettings` from the root `settings.py`, give it its own `env_prefix`.

## Architecture: three-part resumable sync pipeline

The core design is in `modules/sync/pipeline.py` (`LeetCodeSyncManager`) — the orchestration
layer, kept separate from `modules/leetcode/` (the data layer it coordinates: client, storage,
parsers, image processing) so the "what to fetch and when" logic doesn't sit flat alongside the
low-level primitives it depends on. Fetching data for one solved problem is split into three
independent, idempotent, individually-resumable parts, because LeetCode API calls are
slow/rate-limited and a full sync can be interrupted:

1. **description** — `populate_question_metadata`: fetches problem metadata + description HTML
   via GraphQL, converts it to plain text and Markdown.
2. **images** — `populate_question_images`: downloads `<img>` tags referenced in the question
   HTML and rewrites the content to use local relative paths. Depends on part 1 having run
   first (needs `raw_question_html`). A question with zero images still marks this part done.
3. **submission** — `populate_submission_code`: fetches the latest *accepted* submission's
   code. Deliberately does **not** mark this part complete if no accepted submission exists
   yet, since the user may submit a passing solution later.

Each `populate_*` method is a no-op if its data already exists, unless `force_update=True`.
The CLI exposes these as `problems data fetch --part {description,images,submission,full}
[SLUG]` (`full`, the default, runs all three in order; the CLI's own `--refetch` flag maps to
`force_update`). `notes render [SLUG]` also runs this full three-part fetch itself (each part
still a no-op if already populated) before rendering, so it never requires a separate fetch step
first — see CLI below.

Progress is tracked in a small separate JSON cache (`solved_slugs_cache.json`, managed by
`LeetCodeDSAStorage`) mapping `slug -> {description, images, submission: bool}`. A slug is
dropped from this cache automatically once all three parts are `True`
(`storage.mark_part_fetched`). `sync_pending_cache()` is always a live, two-endpoint refresh —
it reconciles the cache against stored data, hits LeetCode's complete solved-problems list to
merge in any newly-solved slugs, then reconciles against the recent-accepted-submissions feed
(`reconcile_recent_accepted()`) to catch resubmits of already-stored problems (the complete
list has no timestamps, so it can't detect those on its own). There's no cache-only/read-only
mode on the manager — for a free, local view of the cache, read `storage.read_pending_cache()`
directly instead (CLI: `problems data pending list/count/show`, vs. the always-live
`problems data pending sync`).

### Layer breakdown (`modules/leetcode/`)

- `client.py` — `LeetCodeClient`: thin `requests.Session` wrapper with rate limiting
  (`requests_ratelimiter`) and retry/backoff (`urllib3.Retry`) for LeetCode's REST (solved
  list) and GraphQL (question details, submission list, submission details, recent-accepted
  submissions) endpoints. Auth is via `LEETCODE_SESSION` / `csrftoken` cookies, not a login
  flow. `recentAcSubmissionList` appears to cap out around 20 results regardless of the
  requested `limit` — don't rely on a higher limit to widen a reconciliation window.
- `parsers/api_response_parsers.py` — pure functions that flatten raw GraphQL JSON into plain
  dicts matching the model fields.
- `parsers/question_content/` — HTML → Markdown (`html_to_markdown.py`, via a
  `markdownify.MarkdownConverter` subclass with LeetCode-specific tweaks for `<sub>`/`<sup>`/
  `<pre>`/`<code>`/`<font>`) and HTML → plain text (`html_to_plain_text.py`, custom
  block-tag-aware whitespace normalization). Both degrade gracefully (return the raw HTML) on
  parse failure.
- `image_processor.py` — `LeetCodeImageProcessor`: downloads images referenced in question
  HTML into `DSA_PROBLEMS_ASSETS_DIR/<slug>/assets/`, resolving extensions from the URL path
  or the response `Content-Type`, and rewrites `<img src>` to the local relative path.
- `storage/` — `LeetCodeDSAStorage` (in `__init__.py`): a facade over three separate JSON
  stores, each with atomic writes (write to a `.tmp` sibling, then `Path.replace`):
  `problems.py` (`problems.json`, community/public data — safe to export), `submissions.py`
  (`submissions.json`, personal — never exported), and `cache.py` (`PendingCacheStore`, the
  pending-parts cache described above). `combined.py` defines `CombinedQuestionRecord`, the
  only place problem + submission data are joined into one read-only view (`get_combined_by_slug`
  / `list_all_combined`).
- `models.py` — pydantic models: `ProblemRecord` (the central per-problem record),
  `QuestionContent` (remote/local markdown+html+text variants), `SubmissionRecord`.
- `recent_activity.py` — pure data transforms (`filter_today`, `dedupe_latest_per_slug`) over
  the recentAcSubmissionList feed's parsed `{slug, title, timestamp}` dicts. Lives here rather
  than in `modules/sync/` since it's plain data shaping, same category as `parsers/` — no
  network/storage I/O, no orchestration.

### Orchestration (`modules/sync/`)

- `pipeline.py` — `LeetCodeSyncManager`, the three-part sync pipeline described above. The only
  consumer of `modules/leetcode/`'s client/storage/image-processor/parsers/models together in
  one place; nothing in `modules/leetcode/` imports back from here. `modules/cli/` only ever
  reaches the LeetCode data layer through this manager (`cli/common.py::get_manager()`), never
  by importing `modules/leetcode/` directly.

### AI prefill (`modules/ai_prefill/`)

Generates the personal study-notes content (pattern, core idea, invariant, trap, ...) via a
pluggable CLI AI tool, instead of leaving it fully blank for hand-writing.

- `generator.py` — `AIPrefillGenerator`: builds a prompt (`prompt_builder.py`), calls the
  configured `AIProvider`, validates the JSON response against `schema.PrefillContent`, and
  appends it as a new version via `storage.py`.
- `providers/` — `AIProvider` is a small interface (`generate(system_prompt, user_prompt) ->
  str`); `claude_code.py` runs `claude -p` headless (`--safe-mode` + `--disallowedTools` so the
  call only reasons over the handed prompt text, nothing from this machine's Claude Code
  config); `subprocess_provider.py` is the generic base for any other CLI tool via
  `AI_PREFILL_COMMAND`. `registry.py` selects one by `AI_PREFILL_PROVIDER`.
- `storage.py` — `AIPrefillStorage`: its own JSON store (`ai_prefill.json`, separate from
  problems/submissions.json since it's regenerable and optional). Keyed by slug -> version
  history (oldest first) — re-running generation appends a new version rather than overwriting,
  so nothing is ever silently lost.

CLI: `notes prefill [SLUG]` generates content standalone (`--regenerate` to add another version
even if one exists). `notes render --ai` pulls the latest stored version in when rendering the
notes file, generating one first if none exists yet; `--regenerate-ai` always generates a fresh
version first (implies `--ai`).

### Rendering (`modules/render/`)

`markdown_problem.py` (`LeetCodeDSAProblemMarkdownRender`) turns a `ProblemRecord`/
`CombinedQuestionRecord` into a Markdown note via `resources/templates/leetcode_problem.md.j2`, in one or
both of two variants (`modules/render/utils.py::FileVariant`):
- `remote` — uses `content.remote_markdown` (hotlinked LeetCode image URLs)
- `local` — uses `content.local_markdown` (rewritten to the locally-downloaded image paths)
  and also copies that problem's `assets/` folder alongside the note.

`markdown_notes.py` (`LeetCodeDSAProblemNotesRender`) renders a separate, personal study-notes
file per problem — frontmatter (tags = personal pattern tags + LeetCode topic-tag slugs,
deduped) plus a link back to the rendered problem/solution file(s); the content sections
(pattern, core idea, invariant, trap, ...) are left blank by default, or filled from the latest
AI prefill content when rendered with `--ai` (see AI prefill above — the CLI's `notes render`
generates prefill content on demand if none exists yet, so `PrefillMissingError` is only ever
raised by lower-level, direct use of `LeetCodeDSAProblemNotesRender.render()`). Two base styles
(`modules/render/utils.py::NotesStyle`: `plain`, `obsidian`), each with a `+ai` variant
(`AI_STYLE` in the same module maps base -> `+ai`) — the CLI exposes these as independent
`--style {plain,obsidian}` + `--ai` flags rather than four separate style choices. `obsidian`
always links *both* the remote and local problem files via `[[wikilink]]`, using the path
relative to `output_base` (disambiguating them, since they share a filename); `plain` links
whichever single variant was actually rendered for that problem — local when the problem has
downloaded images, remote otherwise.

Both renderers write under one resolved base directory (`RendererSettings.resolve_base_dir()`
— see Configuration above) in a fixed internal structure:
```
<base>/Leetcode Problems/remote/<file>.md
<base>/Leetcode Problems/local/<slug>/<file>.md   (+ assets/)
<base>/Leetcode Notes/<file>.md
```
There's one notes file per problem regardless of style — regenerating with a different
`--style`/`--ai` overwrites it (backing up the previous version first — see `--replace-existing`
below) rather than creating a separate file.

### CLI (`modules/cli/`, entrypoint `cli.py`)

`root.py` defines the bare `cli` click group (plus `-H`/`--help-all`, the recursive help
described above); every other module in this package registers commands onto it as a side
effect of being imported by `modules/cli/__init__.py`. Every batch (`--all`) command shares
`common.py`'s `CircuitBreaker` (abort after N consecutive failures) and (in `problems_data.py`)
`BatchPacer` (randomized cooldown every N slugs) so a large run doesn't look like abusive
traffic; commands invoked with neither `SLUG` nor `--all` fall back to `picker.py`'s fuzzy
multi-select instead of erroring.

Flags that regenerate/replace something are named after what they do rather than a bare
`--force`, since the effect differs by command: `--refetch` (`problems data fetch`, re-hits the
network for a part that's already stored), `--replace-existing` (`notes render`, backs up and
overwrites an existing notes file), `--regenerate`/`--regenerate-ai` (`notes prefill` / `notes
render`, appends a new AI prefill version — prior versions are never overwritten), and
`--skip-confirm` (`problems delete`, skips the destructive-action confirmation prompt).

- `problems.py` — the `problems` group itself (fetch/store/render problem data).
- `problems_data.py` — `problems data fetch` (the merged `--part` command described above) and
  `problems data pending {sync,count,list,show,clear}` (the pending cache).
- `problems_db.py` — flat `problems {list,show,count,delete}` over the stored problem+submission
  records.
- `problems_render.py` — `problems render [SLUG]` (the Markdown problem file).
- `problems_recent.py` — `problems recent` (read-only report of LeetCode's recent-accepted feed;
  shows the full ~20-item batch by default, `--today` narrows it to local-time today).
- `notes.py` — the everyday entrypoint. `notes render [SLUG]` fetches whatever's missing for that
  slug (all three parts — a no-op for anything already stored), renders the problem file,
  optionally generates/uses AI prefill content (`--ai`/`--regenerate-ai`), and renders the
  notes file; this is the former `solve` command's pipeline, now folded in here rather than kept
  as a separate top-level command. Omit `SLUG` for an interactive multi-select, or pass `--all`
  to run every known slug non-interactively. `--recent`/`--today` scope that batch (interactive
  or `--all`) to LeetCode's recent-accepted-submissions feed instead of the local slug set,
  syncing from LeetCode first (`LeetCodeSyncManager.sync_pending_cache()`) so brand-new slugs and
  resubmits are picked up before rendering — a resubmit's problem file is re-rendered for free as
  part of the same per-slug pipeline, since `populate_submission_code` already refetches
  automatically once the pending cache reopens that part. `notes prefill [SLUG]` remains a
  standalone way to generate AI prefill content without rendering anything yet.

### Logging

`logging_config.py` (repo root) configures `structlog` on top of stdlib `logging` — colored
console output plus daily-rotating JSON file logs under `logs/`. `cli.py` calls
`configure_logging()` once before invoking the click group — the only entrypoint that needs to.
