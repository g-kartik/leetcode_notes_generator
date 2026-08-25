# AI Prefill

This is the part of the project that writes a **first draft** of your study notes
(pattern, core idea, invariant, trap, complexity, takeaway...) by asking an AI to read
the problem + your accepted solution and fill those sections in for you. You still
review and rewrite it — it's a starting point, not the final note.

It does **not** need an API key or any paid API access. By default it runs
[Claude Code](https://claude.com/claude-code) itself in headless mode (`claude -p`),
so it uses whatever subscription you already use `claude` with in your terminal.

If you'd rather use a different tool (Ollama, a local model, some other CLI AI tool),
you can — see [Using a different AI tool](#using-a-different-ai-tool-no-code-needed)
below. That's the main point of this doc.

---

## How it works, in plain terms

There are two separate steps. They are separate on purpose — generating is slow and
you don't want to accidentally redo it every time you render a note.

**Step 1 — Generate.**

```bash
uv run python cli.py notes prefill two-sum
```

This reads the stored problem description + your accepted solution for `two-sum`,
sends them to the AI with instructions to answer in a specific JSON shape, checks the
answer actually matches that shape, and saves it.

Where it's saved: `LEETCODE_DATA/dsa_problems/ai_prefill.json`, one entry per problem
slug. Every time you generate again for the same slug, it's added as a **new version**
— nothing is ever deleted or overwritten. Handy if you want to try again after
tweaking a prompt, or just compare a couple of attempts.

**Step 2 — Render.**

```bash
uv run python cli.py notes render two-sum --style plain+ai
```

This writes the actual note file, using the **latest** saved version from step 1 to
fill in the draft sections. If you haven't generated anything yet for that slug, this
fails with a message telling you to run `notes prefill` first — it never silently
writes a blank note.

If you don't pass `+ai` (just `--style plain` or `--style obsidian`, the default),
those sections are left blank for you to fill in by hand, exactly like before this
feature existed. AI prefill is opt-in.

### Batch versions

Both commands support `--all` to run over every problem you've already fetched:

```bash
uv run python cli.py notes prefill --all
uv run python cli.py notes render --all --style obsidian+ai
```

Useful flags for `notes prefill --all`:

| Flag | What it does |
|---|---|
| `--force` | Generate a new version even for slugs that already have one. |
| `--no-rate-limit` | Skip the small pause between calls (see below). Fine if you're not on a rate-limited plan. |
| `--limit N` | Only process the first N pending slugs. |
| `--max-failures N` | Stop the batch after N calls in a row fail (default 5, catches something being broken early instead of grinding through hundreds of failures). |

---

## Where everything lives

| What | Where |
|---|---|
| Generated content (the actual data) | `LEETCODE_DATA/dsa_problems/ai_prefill.json` |
| The two prompts sent to the AI | `prompts/ai_prefill/system_prompt.txt` and `prompts/ai_prefill/user_prompt.txt` — plain text files, edit them directly to change the instructions or wording |
| The JSON shape the AI must answer in | `modules/ai_prefill/schema.py` (`PrefillContent`) |
| Settings (which AI tool, timeouts, etc.) | `.env` — see `.env.example`, everything is prefixed `AI_PREFILL_` |
| The code | `modules/ai_prefill/` |

The prompt files use `$placeholder` style variables (e.g. `$title`, `$description`,
`$code`) — you can reword everything around them freely, just keep the placeholders
that are already there.

---

## Using a different AI tool (no code needed)

By default, `.env` has:

```bash
AI_PREFILL_PROVIDER=claude_code
AI_PREFILL_MODEL=sonnet
```

To use **any other command-line AI tool** instead — Ollama, `llm`, a custom script,
anything you can run from a terminal — switch the provider to `command` and tell it
how to run your tool:

```bash
AI_PREFILL_PROVIDER=command
AI_PREFILL_COMMAND=ollama run llama3
```

That's it. No Python code to write. Here's what's actually happening: whatever you
put in `AI_PREFILL_COMMAND` gets run as a program, the prompt is sent to it on stdin,
and whatever it prints back is read as the answer.

Two more settings you may need, depending on the tool:

```bash
# Only set this if your tool has a dedicated flag for a "system prompt"
# (instructions) separate from the actual question. If you don't set it,
# the instructions are just added to the front of the same text sent on
# stdin, which works fine for most tools.
AI_PREFILL_SYSTEM_PROMPT_FLAG=

# Only set this if your tool wraps its answer inside a bigger JSON object,
# e.g. {"response": "...the actual answer..."} — put the key name here
# ("response" in that example) so it can be unwrapped. Leave empty if your
# tool just prints the answer directly.
AI_PREFILL_ENVELOPE_KEY=
```

The only real requirement for any tool you plug in this way: when asked, it must be
able to answer with **just the JSON object** described in
`prompts/ai_prefill/system_prompt.txt` — no extra commentary. Most instructable
models can do this if you tell them to (the default prompt already does).

### If your tool needs something more custom

The `command` provider covers "run a program, send text on stdin, read text back."
If your tool needs something that doesn't fit that (its own login step, a weird
non-JSON wrapper, whatever), you can write a small adapter instead. Every provider is
just one class with one method:

```python
# modules/ai_prefill/providers/base.py
class AIProvider(ABC):
    name: str

    @abstractmethod
    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        """Run the tool, return its raw text answer."""
```

Look at `modules/ai_prefill/providers/claude_code.py` for a real, small example (it's
about 40 lines). Once you've written your class, register it by name in
`modules/ai_prefill/providers/registry.py`, then point `AI_PREFILL_PROVIDER` at that
name in `.env`.

---

## Rate limiting

`AI_PREFILL_RATE_LIMIT_SECONDS` (default `3`) is how long `notes prefill --all` pauses
between each generation. This exists for accounts on a plan with tighter usage limits.
If you're on a plan without that concern, pass `--no-rate-limit` on the command, or
just set `AI_PREFILL_RATE_LIMIT_SECONDS=0` in `.env` to make it the default.

---

## A note on the default (Claude Code) provider specifically

Since the default provider runs `claude` itself as a subprocess, it's worth knowing
what it can and can't see or do, in case that matters to you:

- It runs with `--safe-mode`, which turns off this project's (and your global)
  `CLAUDE.md`, skills, plugins, hooks, and any configured MCP servers for that one
  call — it only ever sees the problem text and solution code you're asking about,
  nothing else from your setup.
- Its built-in tools (reading/writing files, running shell commands, browsing the
  web, etc.) are explicitly turned off — it can only answer in text, it can't take
  any actions.
- It runs from a temp folder rather than this project's folder, as an extra layer of
  the same protection.
- Auth still works normally — it uses the same login as your regular `claude`
  terminal sessions, so nothing extra to set up.

None of this applies if you switch to a different tool via `AI_PREFILL_PROVIDER=command`
— what that tool can see/do is entirely up to however you configured it yourself.
