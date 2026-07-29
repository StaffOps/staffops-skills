---
name: python-cli-tools
description: "Build distributable CLIs with Click or Typer."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, cli, click, typer, argparse, entry-points]
    category: development
    related_skills: [python-scripting, python-packaging, shell-cli-design]
---
# Python CLI Tools

Building a Python command-line tool that's genuinely distributable and
installable — not just a script with `argparse`, but a package with a real
entry point, subcommands, and the same interface discipline covered in
`shell-cli-design` (streams, exit codes) applied in Python. Reach for this
once a tool has outgrown a single-file script, per `bash-scripting`'s
comparison table and `python-scripting`'s skeleton.

## When to Use

Use when a script needs to be installed and run as a real command (not
`python script.py`), when it needs multiple subcommands with distinct
options, or when packaging a tool for others to `pip install`.

## Click vs Typer vs argparse

| Library | Style | When to choose it |
| --- | --- | --- |
| `argparse` | Stdlib, imperative, verbose | No dependency wanted; a single simple script — see `python-scripting` |
| `click` | Decorator-based, mature, huge ecosystem | The de facto standard for a real CLI package |
| `typer` | Type-hint-driven, built on Click | Prefer type hints as the source of truth; less boilerplate |

`click` is the safe, most broadly compatible default for a distributable
tool. `typer` generates the same underlying Click machinery from function
signatures and type hints, which is less code for the equivalent behavior —
a reasonable modern choice when the project's dependency list already
leans toward type-hint-first style throughout.

## A Click CLI with subcommands

```python
# src/mytool/cli.py
import click


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """mytool -- does useful things."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=str))
@click.option("-o", "--output", type=click.Path(), help="Output file.")
@click.option("--format", type=click.Choice(["json", "text"]), default="text")
@click.pass_context
def process(ctx: click.Context, path: str, output: str | None, format: str) -> None:
    """Process PATH and produce output."""
    if ctx.obj["verbose"]:
        click.echo(f"processing {path}", err=True)
    # ... actual work ...


@cli.command()
@click.confirmation_option(prompt="Are you sure you want to delete everything?")
def clean() -> None:
    """Remove generated files."""
    click.echo("cleaned")


if __name__ == "__main__":
    cli()
```

`click.Path(exists=True)` validates the argument is an actually-existing
path **before** the command function even runs — free validation with a
clear, consistent error message, instead of manually checking
`os.path.exists()` inside every command and writing a custom error for
each. `click.Choice([...])` is the same idea for enumerated options,
directly analogous to `argparse`'s `choices=`.

## Entry points: making it a real installed command

```toml
# pyproject.toml
[project]
name = "mytool"
dependencies = ["click>=8.1"]

[project.scripts]
mytool = "mytool.cli:cli"
```

```bash
pip install -e .
mytool process data.csv --format json      # now a real command, not `python -m mytool`
```

The `[project.scripts]` entry — see `python-packaging` for the full
`pyproject.toml` picture — is what turns a Python function into an
installed shell command available on `PATH`. Without it, users would need
`python -m mytool.cli` or similar, which is a materially worse experience
for anyone installing the tool.

## Streams and exit codes: the same discipline as shell-cli-design

```python
import click
import sys

@cli.command()
@click.argument("path")
def process(path: str) -> None:
    try:
        result = do_work(path)
    except FileNotFoundError:
        click.echo(f"error: file not found: {path}", err=True)
        sys.exit(1)

    click.echo(result.summary)          # DATA -> stdout
    click.echo("processing complete", err=True)   # DIAGNOSTICS -> stderr
```

`click.echo(..., err=True)` routes to stderr — the exact same stream
discipline covered in `shell-cli-design`: data the tool produces goes to
stdout so it composes in a pipeline, diagnostics go to stderr so they don't
pollute that data. This matters just as much for a Python CLI as it does
for a shell script; the language doesn't change the contract other tools
and scripts expect.

```python
import sys

def main() -> int:
    try:
        run()
    except KeyboardInterrupt:
        return 130                       # matches the shell convention: 128 + SIGINT
    except SomeSpecificError as e:
        click.echo(f"error: {e}", err=True)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

Click commands `sys.exit()` with the code passed to `sys.exit()`/`raise
SystemExit()` inside them automatically — but for consistency with shell
tooling's conventions (0 success, 1 general error, 2 usage error, 130 for
Ctrl-C), it's worth being deliberate about which code a given failure
returns rather than always defaulting to a bare `sys.exit(1)`.

## Reading from stdin

```python
import click
import sys

@cli.command()
@click.argument("input", type=click.File("r"), default="-")
def process(input: click.utils.LazyFile) -> None:
    """Process INPUT (use - for stdin)."""
    content = input.read()
```

```bash
mytool process data.txt
cat data.txt | mytool process -        # the "-" convention, same as most Unix tools
```

`click.File("r")` with `default="-"` gives the same `-` means stdin
convention that `shell-cli-design` covers for shell scripts — supporting it
is what makes a tool composable in a pipeline rather than only usable
against a named file.

## Progress bars and interactive prompts

```python
import click
import time

@cli.command()
@click.argument("items", nargs=-1)
def process_all(items: tuple[str, ...]) -> None:
    with click.progressbar(items, label="Processing") as bar:
        for item in bar:
            time.sleep(0.1)   # actual work here

@cli.command()
def configure() -> None:
    name = click.prompt("Enter your name")
    confirmed = click.confirm("Proceed?")
```

Both `click.progressbar` and `click.prompt`/`click.confirm` automatically
detect whether stdout/stdin is a real terminal and degrade gracefully when
not (no progress bar spinner corrupting piped output; `confirm()` needs an
explicit non-interactive path for CI, similar to `shell-cli-design`'s
`[[ -t 0 ]]` TTY check before prompting).

```python
@cli.command()
@click.option("--force", is_flag=True, help="Skip the confirmation prompt.")
def delete(force: bool) -> None:
    if not force and not click.confirm("Delete everything?"):
        click.echo("aborted", err=True)
        sys.exit(1)
```

A `--force` flag that bypasses only the *prompt*, not any underlying
validation — the same principle from `shell-cli-design`'s treatment of
`--force` in shell tools.

## Testing a Click CLI

```python
from click.testing import CliRunner
from mytool.cli import cli

def test_process_command():
    runner = CliRunner()
    result = runner.invoke(cli, ["process", "data.csv", "--format", "json"])
    assert result.exit_code == 0
    assert "processed" in result.output

def test_missing_file():
    runner = CliRunner()
    result = runner.invoke(cli, ["process", "/nonexistent"])
    assert result.exit_code != 0
```

`CliRunner` invokes the CLI in-process (no actual subprocess spawned),
capturing `stdout`/`stderr` and the exit code directly — fast, and avoids
the overhead and platform-dependence of testing through real subprocess
invocation. This pairs directly with the fixture and assertion patterns in
`python-testing`.

## Configuration precedence, same as shell-cli-design

```python
import os
import click

@cli.command()
@click.option("--format", envvar="MYTOOL_FORMAT", default="text")
def process(format: str) -> None:
    ...
```

```bash
mytool process --format json          # flag wins
MYTOOL_FORMAT=json mytool process      # env var, if no flag given
mytool process                          # falls back to the default
```

`envvar=` on a Click option implements the same flags-override-environment
precedence documented in `shell-cli-design` — flag beats environment
variable beats built-in default, in that order, matching what users expect
from command-line tools regardless of implementation language.

## Pitfalls

- **Skipping `[project.scripts]`** — the tool never becomes a real
  installed command; users are stuck with `python -m` invocations.
- **Writing diagnostics to stdout** (`click.echo(msg)` without `err=True`)
  — breaks piping the tool's actual output, exactly as in shell scripts.
- **A `--force` flag that also skips genuine validation**, not just the
  confirmation prompt.
- **Not testing via `CliRunner`** — falling back to spawning real
  subprocesses in tests, which is slower and less portable.
- **Choosing `argparse` for a genuinely multi-command distributable tool**
  — workable, but `click`'s subcommand and validation machinery removes a
  lot of boilerplate `argparse` requires to be written by hand.
- **Not supporting `-` for stdin** on a command that reads a file — breaks
  composability with the rest of a pipeline.

## Reference

- `shell-cli-design` — the interface conventions (streams, exit codes,
  config precedence) this skill applies in Python
- `python-scripting` — `argparse`-based single-script CLIs, before a
  project outgrows that
- `python-packaging` — the `pyproject.toml`/entry-point mechanics in full
- `python-testing` — `pytest` patterns applicable to `CliRunner`-based tests
