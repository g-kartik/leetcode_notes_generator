# LeetCode Notes Generator

Turn the LeetCode problems you've already solved into a tidy set of Markdown
notes — one file per problem, with the problem statement, your accepted
solution, and space to write down what you learned. Works as a stand-alone
folder of notes, or drops straight into an [Obsidian](https://obsidian.md)
vault if you use one.

---

## What it actually does

1. **Looks at your LeetCode account** and finds every problem you've solved.
2. **Downloads each problem** — the question text, any images in it, and your
   accepted (passing) solution code.
3. **Writes it all out as Markdown files** you can read, search, and edit
   like any other notes.
4. **Optionally asks an AI to draft your study notes for you** — things like
   "what pattern is this?" and "what's the trick to remember?" — so you're
   editing a draft instead of staring at a blank page.

Nothing is deleted from LeetCode and nothing is posted anywhere. It only
*reads* your solved problems and saves a local copy.

## What you end up with

For every problem you get **two files**:

- **The problem file** — the question itself plus your solution code, exactly
  as LeetCode has it.
- **The notes file** — a short template for *your own* thoughts, with
  sections like:

  ```
  Pattern:        (e.g. "Two pointers")
  Core idea:      (the one sentence that unlocks the problem)
  Invariant:      (what stays true throughout your solution)
  Trap:           (the mistake that's easy to make here)
  Recognition clue: (how to spot this pattern next time)
  Complexity:     Time / Space
  My takeaway:    (what you want to remember)
  ```

  These sections start out empty so you can fill them in yourself — or let
  the AI draft them for you (see below), and just clean up what it wrote.

## Before you start, you'll need

- **Python 3.14 or newer**
- **[uv](https://docs.astral.sh/uv/)** — a tool that installs Python
  dependencies and runs the project for you. If you don't have it yet:

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

- **A LeetCode account** with some problems already solved.

## Setting it up

**1. Get the project and install its dependencies:**

```bash
git clone <this repository's URL>
cd leetcode_notes_generator
uv sync
```

**2. Tell it who you are on LeetCode.**

This tool reads your solved problems the same way your browser does, so it
needs two values copied out of your browser while you're logged into
LeetCode:

1. Log into [leetcode.com](https://leetcode.com) in your browser.
2. Open your browser's developer tools (usually the `F12` key) and find the
   **Cookies** section (in Chrome: *Application* tab → *Cookies*; in
   Firefox: *Storage* tab → *Cookies*).
3. Find the cookie named `LEETCODE_SESSION` and copy its value.
4. Find the cookie named `csrftoken` and copy its value too.

**3. Create your settings file:**

```bash
cp .env.example .env
```

Open `.env` in a text editor and paste your two values in:

```
LEETCODE_SESSION=paste-the-long-value-here
LEETCODE_CSRF_TOKEN=paste-the-other-value-here
```

That's the only required setup. Everything else in `.env` is optional — see
the comments in that file if you want to change where your notes are saved,
or turn on AI-drafted notes later.

> **Keep `.env` private.** It contains a key that logs into your LeetCode
> account. It's already excluded from Git (`.gitignore`), so it won't get
> committed by accident — just don't share the file or paste its contents
> anywhere.

> Your session cookie will eventually expire (LeetCode logs you out
> periodically). If commands suddenly stop working with an authentication
> error, just repeat step 2 above and update `.env` with the fresh values.

## Your first run

The one command you'll use most is `notes render`. Run it with no arguments
and it will show you a searchable list of your solved problems to pick from:

```bash
uv run python cli.py notes render
```

- Type to search, `Tab` to select more than one, `Enter` to confirm.
- The first time you pick a problem, it downloads everything it needs — this
  can take a few seconds per problem, since LeetCode limits how fast it will
  answer requests.
- Your notes appear under `LOCAL_RENDER/` in this project folder (or
  wherever you've pointed `OUTPUT_BASE_DIR` at — see below).

## Everyday use

| I want to...                                            | Run this                              |
|----------------------------------------------------------|----------------------------------------|
| Pick problems from a searchable list                      | `uv run python cli.py notes render`   |
| Generate notes for one specific problem                   | `uv run python cli.py notes render two-sum` |
| Generate notes for *every* solved problem (first-time setup) | `uv run python cli.py notes render --all` |
| Catch up on problems solved recently                      | `uv run python cli.py notes render --recent` |
| Catch up on problems solved just today                    | `uv run python cli.py notes render --today` |

Problem names above (like `two-sum`) come from the last part of the
problem's LeetCode URL, e.g. `leetcode.com/problems/two-sum/` → `two-sum`.

Re-running any of these for a problem you already have notes for won't
touch your existing notes file, so it's always safe to run again — nothing
gets overwritten unless you explicitly ask for that with `--replace-existing`.

## Letting AI draft your notes

Writing "what's the pattern? what's the trick?" for every single problem by
hand is a lot of typing. Add `--ai` to have an AI take a first pass at those
sections for you, which you can then read over and adjust:

```bash
uv run python cli.py notes render --ai
```

By default this uses Claude Code itself to write the draft, so if you're
already running this tool from inside Claude Code, there's nothing extra to
set up or pay for separately. Want a fresh draft instead of the one already
saved? Use `--regenerate-ai` — your old draft is kept, not thrown away.

## Using it with Obsidian

If you keep your notes in an [Obsidian](https://obsidian.md) vault, point
this tool at a folder inside that vault and it will render straight into it,
with notes linked to their matching problem file automatically:

```
OUTPUT_BASE_DIR=/path/to/your/Obsidian Vault/LeetCode
```

Add that line to your `.env` file, then add `--style obsidian` (or set
`DEFAULT_NOTES_STYLE=obsidian` in `.env` so you don't have to type it every
time):

```bash
uv run python cli.py notes render --style obsidian
```

## Other handy commands

```bash
uv run python cli.py problems list              # see everything you've saved so far
uv run python cli.py problems count              # just the total count
uv run python cli.py problems show two-sum       # see everything stored for one problem
uv run python cli.py problems recent             # what LeetCode says you solved recently
uv run python cli.py problems delete two-sum     # remove a problem (and its solution) entirely
uv run python cli.py problems delete-submission two-sum   # keep the problem, just remove the saved solution code
```

Every command and option can be listed at any time with `-h`:

```bash
uv run python cli.py -h                # top-level commands
uv run python cli.py notes render -h   # options for one specific command
uv run python cli.py -H                # everything, all at once
```

## Where your files end up

```
LOCAL_RENDER/                          (or your own OUTPUT_BASE_DIR)
├── Leetcode Problems/
│   ├── remote/...                     problem + solution files
│   └── local/<problem>/...            same, with downloaded images
└── Leetcode Notes/
    └── ...                            your personal study notes, one per problem
```

## Frequently asked questions

**Does this ever change anything on LeetCode itself?**
No. It only reads your solved problems and your own submissions — nothing
is submitted, edited, or deleted on LeetCode's side.

**Will running it again lose my hand-written notes?**
No. Re-running a command for a problem you already have never overwrites
your notes file unless you explicitly pass `--replace-existing` — and even
then, your previous version is backed up first, not deleted.

**Commands are suddenly failing with a login/authentication error — what happened?**
Your LeetCode session cookie expired. Repeat the "get your login keys" step
above and update the two values in your `.env` file.

**A command feels stuck / slow.**
LeetCode limits how many requests it will answer per second, so fetching a
lot of problems for the first time (`--all`) is naturally slow. This is
expected — leave it running, or narrow it down to fewer problems at a time.
