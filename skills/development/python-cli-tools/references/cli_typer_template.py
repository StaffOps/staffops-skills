#!/usr/bin/env python3
"""CLI entry point using Typer — copy-paste starter.

Usage after `pip install -e .`:
    mytool --help
    mytool greet World --count 3
    mytool convert data.json -o output.yaml
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

app = typer.Typer(help="My tool — short description of what it does.")


@app.command()
def greet(
    name: str,
    count: Annotated[int, typer.Option("--count", "-c", help="Number of greetings")] = 1,
    shout: Annotated[bool, typer.Option("--shout/--no-shout", help="Uppercase")] = False,
):
    """Greet NAME."""
    msg = f"Hello, {name}!"
    if shout:
        msg = msg.upper()
    for _ in range(count):
        typer.echo(msg)


@app.command()
def convert(
    path: Annotated[Path, typer.Argument(help="Input file", exists=True, dir_okay=False)],
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help="Output file")] = None,
    fmt: Annotated[str, typer.Option("--format", help="Output format")] = "json",
):
    """Convert file to specified format."""
    data = json.loads(path.read_text(encoding="utf-8"))

    if fmt == "json":
        result = json.dumps(data, indent=2, ensure_ascii=False)
    elif fmt == "yaml":
        import yaml
        result = yaml.dump(data, default_flow_style=False)
    else:
        typer.secho(f"Unknown format: {fmt}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    if output is None or str(output) == "-":
        typer.echo(result)
    else:
        output.write_text(result, encoding="utf-8")
        typer.secho(f"✓ Written to {output}", fg=typer.colors.GREEN, err=True)


if __name__ == "__main__":
    app()
