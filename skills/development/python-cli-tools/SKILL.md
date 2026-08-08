---
name: python-cli-tools
description: "Use when building a pip-installable CLI with subcommands using Click or Typer, configuring entry points, or migrating from argparse to a proper CLI framework. Covers Click decorators, Typer type-hint patterns, testing CLIs, and packaging."
version: 1.1.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, cli, click, typer, argparse, entry-points]
    category: development
    related_skills: [python-scripting, python-packaging, python-testing]
---

# Python CLI Tools

Building installable CLIs with Click or Typer — subcommands, options, and proper exit codes.

## When to Use

- Script needs to be `pip install`-able as a real command
- Tool needs multiple subcommands (`mytool init`, `mytool run`, `mytool status`)
- Need --help auto-generated from code
- Outgrew single-file argparse script

## When NOT to Use

- Single script, no install needed → `python-scripting` (argparse skeleton)
- Interactive TUI with widgets → use `textual` or `rich`
- Just wrapping shell commands → Bash script may suffice

---

## Click vs Typer — Decision

| | Click | Typer |
|--|-------|-------|
| Style | Decorators + explicit types | Type hints as source of truth |
| Maturity | 10+ years, huge ecosystem | Built on Click, newer |
| Boilerplate | More explicit | Less code |
| When | Complex CLIs, plugins, legacy | New projects, type-hint-first |

**Default choice**: Click (broader ecosystem, more docs). Typer if team already uses type hints everywhere.

---

## Click — Complete Example

```python
# src/mypackage/cli.py
import click
import sys


@click.group()
@click.version_option()
def cli():
    """My tool — does useful things."""
    pass


@cli.command()
@click.argument("name")
@click.option("--count", "-c", default=1, help="Number of greetings")
@click.option("--shout/--no-shout", default=False, help="Uppercase output")
def hello(name: str, count: int, shout: bool):
    """Greet NAME."""
    msg = f"Hello, {name}!"
    if shout:
        msg = msg.upper()
    for _ in range(count):
        click.echo(msg)


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.File("w"), default="-")
@click.option("--format", "fmt", type=click.Choice(["json", "yaml"]), default="json")
def convert(path: str, output, fmt: str):
    """Convert file at PATH to specified format."""
    import json
    from pathlib import Path as P

    data = json.loads(P(path).read_text())
    
    if fmt == "json":
        output.write(json.dumps(data, indent=2))
    elif fmt == "yaml":
        import yaml
        output.write(yaml.dump(data))
    
    click.echo(f"✓ Converted to {fmt}", err=True)


if __name__ == "__main__":
    cli()
```

### Click patterns cheat sheet

```python
# Required argument
@click.argument("name")

# Optional with default
@click.option("--port", "-p", default=8080, type=int)

# Boolean flag
@click.option("--verbose/--quiet", default=False)

# Choice enum
@click.option("--env", type=click.Choice(["dev", "prd", "hml"]))

# File (auto-opens, handles "-" as stdin/stdout)
@click.option("--output", type=click.File("w"), default="-")

# Path (validates existence)
@click.argument("config", type=click.Path(exists=True, dir_okay=False))

# Password (hidden input)
@click.option("--password", prompt=True, hide_input=True)

# Progress bar
with click.progressbar(items) as bar:
    for item in bar:
        process(item)

# Colored output
click.secho("Error!", fg="red", bold=True, err=True)
click.secho("Success!", fg="green")

# Exit with code
raise SystemExit(1)  # or ctx.exit(1)
```

---

## Typer — Complete Example

```python
# src/mypackage/cli.py
from pathlib import Path
from typing import Annotated, Optional

import typer

app = typer.Typer(help="My tool — does useful things.")


@app.command()
def hello(
    name: str,
    count: Annotated[int, typer.Option("--count", "-c", help="Greetings")] = 1,
    shout: Annotated[bool, typer.Option("--shout/--no-shout")] = False,
):
    """Greet NAME."""
    msg = f"Hello, {name}!"
    if shout:
        msg = msg.upper()
    for _ in range(count):
        typer.echo(msg)


@app.command()
def convert(
    path: Annotated[Path, typer.Argument(help="Input file", exists=True)],
    output: Annotated[Path, typer.Option("-o", "--output")] = Path("-"),
    fmt: Annotated[str, typer.Option(help="Format")] = "json",
):
    """Convert file to specified format."""
    import json

    data = json.loads(path.read_text())
    result = json.dumps(data, indent=2)
    
    if str(output) == "-":
        typer.echo(result)
    else:
        output.write_text(result)
        typer.echo(f"✓ Written to {output}", err=True)


if __name__ == "__main__":
    app()
```

---

## Packaging the CLI

```toml
# pyproject.toml
[project.scripts]
mytool = "mypackage.cli:cli"      # Click
# mytool = "mypackage.cli:app"    # Typer (needs typer[all] or typer.main.get_command())
```

After `pip install -e .`:
```bash
mytool --help
mytool hello World --count 3
mytool convert data.json -o output.yaml --format yaml
```

---

## Testing CLIs

### Click (CliRunner)

```python
from click.testing import CliRunner
from mypackage.cli import cli

def test_hello():
    runner = CliRunner()
    result = runner.invoke(cli, ["hello", "World", "--count", "2"])
    assert result.exit_code == 0
    assert "Hello, World!" in result.output
    assert result.output.count("Hello, World!") == 2

def test_hello_shout():
    runner = CliRunner()
    result = runner.invoke(cli, ["hello", "World", "--shout"])
    assert "HELLO, WORLD!" in result.output

def test_missing_arg():
    runner = CliRunner()
    result = runner.invoke(cli, ["hello"])  # missing NAME
    assert result.exit_code != 0
```

### Typer (CliRunner from typer.testing)

```python
from typer.testing import CliRunner
from mypackage.cli import app

runner = CliRunner()

def test_hello():
    result = runner.invoke(app, ["hello", "World"])
    assert result.exit_code == 0
    assert "Hello, World!" in result.output
```

---

## Pitfalls

| Mistake | Fix |
|---------|-----|
| `print()` instead of `click.echo()` | `echo` handles encoding/piping correctly |
| Mixing stdout data with status messages | Data → stdout, status → stderr (`err=True`) |
| No `--help` on subcommands | Add docstrings to every command function |
| Hard-coding colors without checking terminal | Use `click.style()` which respects `NO_COLOR` |
| No exit codes | Return/raise appropriate codes (0=ok, 1=user error, 2=system error) |
| Not testing the CLI end-to-end | Use `CliRunner` — it catches regressions in arg parsing |

---
## Decision tree

```
Python CLI design?
├── Framework choice?
│   ├── Type-hint native + auto-complete? → Typer
│   ├── Maximum flexibility + plugins? → Click
│   └── Minimal / stdlib only? → argparse (avoid for new projects)
├── Subcommands?
│   ├── Single command? → @app.command() (Typer) / @click.command()
│   ├── Grouped commands? → app.add_typer() / @click.group()
│   └── Nested groups? → Group hierarchy (max 2 levels deep)
├── Options pattern?
│   ├── Required value? → Argument (positional)
│   ├── Optional flag? → Option with default
│   ├── Boolean toggle? → --flag / --no-flag
│   └── Environment fallback? → envvar= parameter
└── Output?
    ├── Human-readable? → rich.console + rich.table
    ├── Machine-parseable? → --output json/yaml flag
    └── Progress? → rich.progress or tqdm
```


## Related Skills

- `python-scripting` — single-file argparse for simple scripts
- `python-packaging` — pyproject.toml entry points
- `python-testing` — testing patterns (CliRunner tests live in your test suite)
