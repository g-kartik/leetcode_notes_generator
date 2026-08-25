# Shell tab-completion

`cli.py` (invoked as `uv run python cli.py ...`) is built with
[Click](https://click.palletsprojects.com/), which supports shell
tab-completion out of the box — but only for a single, fixed command name,
which `uv run python cli.py` doesn't give it on its own (the shell only
completes based on the first word you type, and that's `uv`).

`shell/leetnotes` is a small wrapper executable that solves that: it finds
this repo (even called through a symlink from elsewhere on your PATH) and
runs `uv run python cli.py "$@"` from inside it. Point your PATH at it under
the name `leetnotes`, generate one completion script, and `leetnotes <TAB>`
will walk you through every command, subcommand, and flag from then on — no
more checking `--help` to remember them.

Setup is two steps: put `leetnotes` on your PATH (same for every shell),
then generate the completion script (shell-specific). Redo step 2 any time a
command is added/renamed.

## 1. Put `leetnotes` on your PATH

```bash
mkdir -p ~/.local/bin
ln -s "$(pwd)/shell/leetnotes" ~/.local/bin/leetnotes
```

(Make sure `~/.local/bin` is actually on your `$PATH` — most distros/shell
setups already add it by default.)

## 2. Generate completions for your shell

**fish**

```fish
_LEETNOTES_COMPLETE=fish_source leetnotes > ~/.config/fish/completions/leetnotes.fish
```

Fish autoloads this by filename — nothing else to add to `config.fish`.

**bash** — add to `~/.bashrc`:

```bash
eval "$(_LEETNOTES_COMPLETE=bash_source leetnotes)"
```

**zsh** — add to `~/.zshrc`:

```zsh
eval "$(_LEETNOTES_COMPLETE=zsh_source leetnotes)"
```

## Using it

`leetnotes` works exactly like `uv run python cli.py` (same commands, same
flags) — and unlike that form, it works from any directory, not just this
project's:

```
leetnotes <TAB>                 # -> cache  db  notes  populate  recent  render  sync
leetnotes notes <TAB>           # -> prefill  render
leetnotes notes prefill --<TAB> # -> --all  --force  --limit  --max-failures  --rate-limit/--no-rate-limit
```
