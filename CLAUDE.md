# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A pipeline that syncs a user's solved LeetCode problems (via LeetCode's REST + GraphQL
endpoints), stores them as structured JSON, and renders them as Markdown notes — optionally
mirrored into an Obsidian vault.

## Commands

- Install deps: `uv sync`
- Run any script/module: `uv run python -m <module>` or `uv run python -c "..."`
- There is currently no CLI entrypoint wired up: `manage.py` exists but is an empty stub
  (`click` is a declared dependency, suggesting a CLI is planned there but not yet built).
  Until it exists, exercise the pipeline by importing `LeetCodeSyncManager` directly, e.g.:
  ```python
  from modules.leetcode.pipeline import LeetCodeSyncManager
  mgr = LeetCodeSyncManager()
  slugs = mgr.sync_solved_questions_data_entry()
  ```
- No test suite and no lint/type-check config exist in this repo yet — don't assume `pytest`,
  `ruff`, or `mypy` are configured; check `pyproject.toml` before inventing commands.
- Requires Python >=3.14 (managed via `uv`, see `uv.lock`).

## Configuration

Settings are `pydantic-settings` classes reading from a single root `.env` file
(see `.env.example` for required keys). `settings.py` (repo root) defines
`BaseProjectSettings`, which just fixes `PROJECT_ROOT_DIR`. Every module-level settings
class subclasses it and adds its own `env_prefix`:

- `modules/leetcode/settings.py` — `LeetCodeSettings` (`env_prefix="LEETCODE_"`): auth
  (`SESSION`, `CSRF_TOKEN` cookies copied from an authenticated browser session against
  leetcode.com), and on-disk paths for the JSON "database" and cached assets
  (`LEETCODE_DATA/dsa_problems/db.json`, `.../solved_slugs_cache.json`, `.../assets/`).
- `modules/render/settings.py` — `RendererSettings`: template dir, default output dir
  (`LOCAL_RENDER/` in the project root), and an optional `OUTPUT_BASE_DIR` override (no
  `LEETCODE_` prefix — a different env var namespace than the leetcode settings). Base-dir
  resolution priority, via `RendererSettings.resolve_base_dir()`: a CLI `--output-base` >
  `OUTPUT_BASE_DIR` (.env) > `DEFAULT_WRITE_DIR`. Point `OUTPUT_BASE_DIR` at (a folder inside)
  an Obsidian vault to have problems/notes render straight into it — there's no separate
  vault-mirroring mechanism.

When adding a new module that needs config, follow this same pattern: subclass
`BaseProjectSettings` from the root `settings.py`, give it its own `env_prefix`.

## Architecture: three-part resumable sync pipeline

The core design is in `modules/leetcode/pipeline.py` (`LeetCodeSyncManager`). Fetching data
for one solved problem is split into three independent, idempotent, individually-resumable
parts, because LeetCode API calls are slow/rate-limited and a full sync can be interrupted:

1. **question** — `populate_question_metadata`: fetches problem metadata + description HTML
   via GraphQL, converts it to plain text and Markdown.
2. **images** — `populate_question_images`: downloads `<img>` tags referenced in the question
   HTML and rewrites the content to use local relative paths. Depends on part 1 having run
   first (needs `raw_question_html`). A question with zero images still marks this part done.
3. **submission** — `populate_submission_code`: fetches the latest *accepted* submission's
   code. Deliberately does **not** mark this part complete if no accepted submission exists
   yet, since the user may submit a passing solution later.

Each `populate_*` method is a no-op if its data already exists, unless `force_update=True`.

Progress is tracked in a small separate JSON cache (`solved_slugs_cache.json`, managed by
`LeetCodeDSAStorage`) mapping `slug -> {question, images, submission: bool}`. A slug is
dropped from this cache automatically once all three parts are `True`
(`storage.mark_part_fetched`). `sync_solved_questions_data_entry()` reads this cache to
return pending slugs without hitting the network, unless `force_refresh=True` (or the cache
is empty), in which case it re-fetches the full solved-problems list from LeetCode and merges
in newly-solved slugs.

### Layer breakdown (`modules/leetcode/`)

- `client.py` — `LeetCodeClient`: thin `requests.Session` wrapper with rate limiting
  (`requests_ratelimiter`) and retry/backoff (`urllib3.Retry`) for LeetCode's REST (solved
  list) and GraphQL (question details, submission list, submission details) endpoints.
  Auth is via `LEETCODE_SESSION` / `csrftoken` cookies, not a login flow.
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
- `storage.py` — `LeetCodeDSAStorage`: the JSON "database" (`db.json`, keyed by slug) plus the
  pending-parts cache described above. Both files use atomic writes (write to a `.tmp` sibling,
  then `Path.replace`).
- `models.py` — pydantic models: `QuestionRecord` (the central per-problem record),
  `QuestionContent` (remote/local markdown+html+text variants), `SubmissionDetails`.

### Rendering (`modules/render/`)

`markdown_problem.py` (`LeetCodeDSAProblemMarkdownRender`) turns a `QuestionRecord` into a
Markdown note via `templates/leetcode_problem.md.j2`, in one or both of two variants
(`modules/render/utils.py::FileVariant`):
- `remote` — uses `content.remote_markdown` (hotlinked LeetCode image URLs)
- `local` — uses `content.local_markdown` (rewritten to the locally-downloaded image paths)
  and also copies that problem's `assets/` folder alongside the note.

`markdown_notes.py` (`LeetCodeDSAProblemNotesRender`) renders a separate, personal study-notes
file per problem — frontmatter (tags = personal pattern tags + LeetCode topic-tag slugs,
deduped) plus a link back to the rendered problem/solution file(s); the content sections
(pattern, core idea, invariant, trap, ...) are prefillable but currently always left blank for
the user to fill in by hand (AI prefill is a later task). Four styles
(`modules/render/utils.py::NotesStyle`): `plain` and `obsidian` are implemented; `plain+ai` and
`obsidian+ai` raise `NotImplementedError` until prefill exists. `obsidian` always links *both*
the remote and local problem files via `[[wikilink]]`, using the path relative to `output_base`
(disambiguating them, since they share a filename); `plain` links whichever single variant
`--link-variant` picks, via a relative Markdown link.

Both renderers write under one resolved base directory (`RendererSettings.resolve_base_dir()`
— see Configuration above) in a fixed internal structure:
```
<base>/Leetcode Problems/remote/<file>.md
<base>/Leetcode Problems/local/<slug>/<file>.md   (+ assets/)
<base>/Leetcode Notes/<file>.md
```
There's one notes file per problem regardless of style — regenerating with a different
`--style` overwrites it rather than creating a separate file.

### Logging

`logging_config.py` (repo root) configures `structlog` on top of stdlib `logging` — colored
console output plus daily-rotating JSON file logs under `logs/`. Call
`configure_logging()` once at a process entrypoint before anything else runs. It is not yet
called anywhere in the pipeline — wire it up if you build the `manage.py` CLI or any other
entrypoint script.
