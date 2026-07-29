---
name: python-scripting
description: "Write robust Python scripts: argparse, pathlib, subprocess."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, scripting, argparse, pathlib, subprocess, logging]
    category: development
    related_skills: [python-cli-tools, python-testing, bash-scripting]
---
# Python Scripting

Writing standalone Python scripts that behave correctly: proper argument
parsing, path handling that works across platforms, safe subprocess
invocation, and structured logging instead of scattered `print()` calls.
This is the "reach for Python instead of Bash" skill referenced from
`bash-scripting` — the idioms that make that switch pay off.

## When to Use

Use when a task outgrows Bash (structured data, real error handling,
testability — see `bash-scripting`'s comparison table), when writing a
utility script that others will run, or when a shell one-liner has grown
past the point of being maintainable as a one-liner.

## The script skeleton

```python
#!/usr/bin/env python3
"""One-line description of what this script does."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Input file")
    parser.add_argument("-o", "--output", type=Path, help="Output file (default: stdout)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    if not args.input.exists():
        logger.error("input not found: %s", args.input)
        return 1

    # ... actual work ...

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Three details worth calling out: `main(argv)` accepts an explicit argument
list (defaulting to `None`, which `argparse` interprets as `sys.argv`) so
the script's logic is directly callable from a test without spawning a
subprocess; `sys.exit(main())` propagates the actual return code instead of
always exiting 0; and `from __future__ import annotations` allows modern
type-hint syntax (`list[str] | None`) even on Python versions where it
wouldn't otherwise be valid at runtime.

## argparse

```python
parser = argparse.ArgumentParser(description="Process some files.")
parser.add_argument("files", nargs="+", type=Path, help="One or more input files")
parser.add_argument("-o", "--output", type=Path, default=Path("out.txt"))
parser.add_argument("-n", "--dry-run", action="store_true")
parser.add_argument("--format", choices=["json", "csv", "text"], default="text")
parser.add_argument("--retries", type=int, default=3)
parser.add_argument("-v", "--verbose", action="count", default=0,
                     help="-v for INFO, -vv for DEBUG")

subparsers = parser.add_subparsers(dest="command", required=True)
build = subparsers.add_parser("build")
build.add_argument("--target", required=True)
deploy = subparsers.add_parser("deploy")
deploy.add_argument("--env", choices=["staging", "prod"], required=True)
```

`action="count"` for `-v`/`-vv` is the idiomatic way to support graduated
verbosity. `choices=[...]` gives free validation and a self-documenting
`--help` output, instead of validating the string manually after parsing.
Subparsers are the direct Python equivalent of the shell CLI subcommand
pattern from `shell-cli-design`.

```python
args = parser.parse_args()
if args.command == "build":
    do_build(args.target)
elif args.command == "deploy":
    do_deploy(args.env)
```

## pathlib over os.path

```python
from pathlib import Path

p = Path("data") / "reports" / "output.csv"    # / composes paths, cross-platform
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text("content\n")
content = p.read_text()

for f in Path("logs").glob("*.log"):
    print(f.name, f.stat().st_size)

for f in Path(".").rglob("*.py"):               # recursive glob
    print(f)

p.suffix       # '.csv'
p.stem          # 'output'
p.with_suffix(".json")
p.resolve()      # absolute path, symlinks resolved
p.exists()
p.is_file()
```

`pathlib` composes paths with `/` correctly on both POSIX and Windows (`\`
vs `/` handled automatically), which `os.path.join` also does but with more
verbose syntax — `pathlib`'s object-oriented API (`.exists()`, `.read_text()`
directly on the path object) is the modern idiomatic choice for new code.

## subprocess: running external commands safely

```python
import subprocess

result = subprocess.run(
    ["ls", "-la", str(some_path)],
    capture_output=True,
    text=True,
    check=True,       # raises CalledProcessError on non-zero exit
    timeout=30,
)
print(result.stdout)
```

**Never build a shell command as a string with `shell=True`** when any part
of it comes from user input or a variable — this is the direct Python
equivalent of the shell-injection risk covered in `bash-scripting`'s
quoting reference:

```python
# DANGEROUS: shell=True + string interpolation is command injection.
subprocess.run(f"ls {user_input}", shell=True)

# Correct: a list of arguments, no shell involved, no injection risk.
subprocess.run(["ls", user_input])
```

`check=True` is important and easy to forget — without it, a failed command
returns a non-zero `returncode` silently, and the script continues as if it
succeeded unless that return code is checked explicitly:

```python
try:
    result = subprocess.run(["mycommand"], capture_output=True, text=True, check=True)
except subprocess.CalledProcessError as e:
    logger.error("command failed (exit %d): %s", e.returncode, e.stderr)
    return 1
except subprocess.TimeoutExpired:
    logger.error("command timed out")
    return 1
```

## Logging instead of print

```python
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)-8s %(message)s",
    stream=sys.stderr,      # diagnostics to stderr -- same discipline as shell-cli-design
)

logger.debug("detailed value: %r", some_value)   # %-style formatting, evaluated LAZILY
logger.info("processing %s", filename)
logger.warning("retrying after failure")
logger.error("could not connect to %s", host, exc_info=True)   # include the traceback
```

Use `%s`-style lazy formatting (`logger.info("x=%s", x)`), **not** an
f-string (`logger.info(f"x={x}")`), in the log call itself — the f-string
version always pays the formatting cost even when that log level is
disabled, while the `%s` form only formats if the message will actually be
emitted. For a hot path with debug logging normally disabled, this
difference is real.

`exc_info=True` inside an `except` block attaches the full traceback to the
log record — far more useful for debugging than a bare error message with no
stack trace.

## Environment and configuration

```python
import os

api_key = os.environ["API_KEY"]              # raises KeyError if missing -- fail loudly
timeout = int(os.environ.get("TIMEOUT", "30"))   # optional, with a default

from dataclasses import dataclass

@dataclass
class Config:
    api_key: str
    timeout: int = 30
    debug: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            api_key=os.environ["API_KEY"],
            timeout=int(os.environ.get("TIMEOUT", "30")),
            debug=os.environ.get("DEBUG", "").lower() == "true",
        )
```

`os.environ[...]` (raising `KeyError` on a missing required variable) is
preferable to `os.environ.get(...)` returning `None` and failing later with
a confusing error somewhere downstream — fail at the point the requirement
is actually known, not wherever the `None` eventually causes a problem.

## Context managers for resource cleanup

```python
with open("file.txt") as f:
    content = f.read()
# file is closed automatically, even if an exception occurs inside the block

from contextlib import contextmanager

@contextmanager
def timer(label: str):
    import time
    start = time.monotonic()
    try:
        yield
    finally:
        logger.info("%s took %.2fs", label, time.monotonic() - start)

with timer("processing"):
    do_work()
```

A custom context manager (via `@contextmanager`) is the Python equivalent of
a Bash `trap ... EXIT` cleanup handler — guaranteed to run the `finally`
block whether the `with` body succeeds, raises, or returns early.

## Error handling: specific over broad

```python
try:
    value = risky_operation()
except (ValueError, KeyError) as e:
    logger.error("invalid input: %s", e)
    return 1
except FileNotFoundError as e:
    logger.error("file not found: %s", e)
    return 1
```

A bare `except:` or `except Exception:` catches things it shouldn't — a
genuine bug elsewhere in the code, a `KeyboardInterrupt`, or a
`SystemExit` — and silently continues as if nothing happened. Catch the
*specific* exceptions the code is actually prepared to handle.

## Pitfalls

- **`shell=True` with interpolated input** — command injection, the direct
  Python equivalent of unquoted shell variable expansion.
- **f-strings inside logging calls** — pays the formatting cost even when
  that log level is disabled; use `%s` lazy formatting instead.
- **`subprocess.run` without `check=True`** — a failed command is silently
  treated as success unless the return code is checked explicitly.
- **A bare `except:`** — swallows `KeyboardInterrupt`/`SystemExit` along with
  genuine bugs.
- **`os.environ.get()` for a genuinely required variable** — fails later,
  confusingly, instead of immediately and clearly.
- **Not making `main()` accept an explicit `argv`** — harder to test the
  script's logic without actually spawning a subprocess.

## Reference

- `python-cli-tools` — building a distributable, installable CLI (beyond a standalone script)
- `python-testing` — testing the functions this skeleton wraps
- `bash-scripting` — when to reach for Bash instead of Python
