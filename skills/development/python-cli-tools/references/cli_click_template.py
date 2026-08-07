"""CLI entry point using Click — copy-paste starter.

Usage after `pip install -e .`:
    mytool --help
    mytool greet World --count 3
    mytool convert data.json -o output.yaml
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click


@click.group()
@click.version_option(package_name="mypackage")
def cli():
    """My tool — short description of what it does."""
    pass


@cli.command()
@click.argument("name")
@click.option("--count", "-c", default=1, type=int, help="Number of greetings")
@click.option("--shout/--no-shout", default=False, help="Uppercase output")
def greet(name: str, count: int, shout: bool):
    """Greet NAME."""
    msg = f"Hello, {name}!"
    if shout:
        msg = msg.upper()
    for _ in range(count):
        click.echo(msg)


@cli.command()
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", type=click.File("w"), default="-", help="Output file")
@click.option("--format", "fmt", type=click.Choice(["json", "yaml"]), default="json")
def convert(path: str, output, fmt: str):
    """Convert file at PATH to specified format."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    if fmt == "json":
        output.write(json.dumps(data, indent=2, ensure_ascii=False))
    elif fmt == "yaml":
        try:
            import yaml
            output.write(yaml.dump(data, default_flow_style=False))
        except ImportError:
            click.secho("Error: PyYAML not installed", fg="red", err=True)
            raise SystemExit(1)

    click.secho(f"✓ Converted to {fmt}", fg="green", err=True)


if __name__ == "__main__":
    cli()
