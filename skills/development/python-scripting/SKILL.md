---
name: python-scripting
description: "Use when writing standalone Python scripts that need argument parsing, safe file/path handling, subprocess calls, or structured logging. Covers the complete script skeleton, pathlib idioms, subprocess patterns, and logging setup."
version: 1.1.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, scripting, argparse, pathlib, subprocess, logging]
    category: development
    related_skills: [python-cli-tools, python-testing, python-packaging]
---

# Python Scripting

Standalone Python scripts that behave correctly: argument parsing, cross-platform paths, safe subprocess calls, and structured logging.

## When to Use

- Task outgrows Bash (structured data, error handling, testability)
- Utility script others will run
- Shell one-liner grew past maintainable
- Need to process JSON/YAML/CSV files with real error handling

## When NOT to Use

- Tool needs subcommands → use `python-cli-tools` (Click/Typer)
- Distributable package → use `python-packaging`
- Simple file manipulation → Bash with `jq`/`yq` may suffice
- One-off data exploration → Jupyter or `ipython`

---

## The Complete Script Skeleton

```python
#!/usr/bin/env python3
"""One-line description of what this script does."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def main(args: argparse.Namespace) -> int:
    """Core logic. Returns exit code (0=success)."""
    log.info("Processing %s", args.input)
    
    input_path = Path(args.input)
    if not input_path.exists():
        log.error("Input not found: %s", input_path)
        return 1
    
    # --- Your logic here ---
    
    log.info("Done. Output: %s", args.output)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", help="Input file path")
    p.add_argument("-o", "--output", default="-", help="Output (default: stdout)")
    p.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    return p.parse_args(argv)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    sys.exit(main(args))
```

---

## Pathlib — The 10 Patterns You Need

```python
from pathlib import Path

# Construction
p = Path("data") / "input" / "file.csv"   # OS-agnostic joining
p = Path.home() / ".config" / "myapp"       # ~/
p = Path(__file__).parent                   # script's own directory

# Queries
p.exists()                    # True/False
p.is_file()                   # is regular file?
p.is_dir()                    # is directory?
p.suffix                      # ".csv"
p.stem                        # "file" (without extension)
p.name                        # "file.csv"

# Reading/writing
text = p.read_text(encoding="utf-8")
p.write_text(content, encoding="utf-8")
data = p.read_bytes()

# Directory ops
p.mkdir(parents=True, exist_ok=True)
list(p.glob("*.json"))             # direct children
list(p.rglob("*.py"))              # recursive

# Manipulation
new = p.with_suffix(".bak")        # change extension
new = p.with_name("other.csv")     # change filename
```

---

## Subprocess — Safe Patterns

```python
import subprocess

# ✅ Basic: capture output, check errors
result = subprocess.run(
    ["git", "status", "--porcelain"],
    capture_output=True,
    text=True,
    check=True,  # raises CalledProcessError on non-zero exit
)
print(result.stdout)

# ✅ With timeout
result = subprocess.run(
    ["curl", "-s", url],
    capture_output=True, text=True,
    timeout=30,  # seconds
    check=True,
)

# ✅ Pipe input
result = subprocess.run(
    ["jq", ".name"],
    input='{"name": "alice"}',
    capture_output=True, text=True, check=True,
)

# ❌ NEVER use shell=True with user input
subprocess.run(f"rm -rf {user_input}", shell=True)  # INJECTION RISK
```

### Error handling

```python
try:
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
except subprocess.CalledProcessError as e:
    log.error("Command failed (exit %d): %s", e.returncode, e.stderr)
    return 1
except subprocess.TimeoutExpired:
    log.error("Command timed out after %ds", timeout)
    return 1
```

---

## Logging — Not print()

```python
import logging

log = logging.getLogger(__name__)

# Levels (use these, not print)
log.debug("Variable x=%r", x)           # development only
log.info("Processing %d items", count)   # normal operation
log.warning("Retrying after %s", err)    # recoverable issue
log.error("Failed to connect: %s", err)  # operation failed
log.exception("Unexpected error")        # includes traceback

# ❌ WRONG
print(f"DEBUG: x = {x}")           # not filterable
logging.info(f"count={count}")     # f-string in log = no lazy eval
```

---

## Common Patterns

### Read JSON/YAML safely

```python
import json
from pathlib import Path

def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError) as e:
        log.error("Failed to load %s: %s", path, e)
        raise SystemExit(1) from e
```

### Stdin/stdout aware

```python
import sys

def get_output(path: str):
    """Return file handle or stdout."""
    if path == "-":
        return sys.stdout
    return open(path, "w", encoding="utf-8")
```

### Retry pattern

```python
import time

def retry(fn, max_attempts=3, delay=1.0):
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:
            if attempt == max_attempts:
                raise
            log.warning("Attempt %d failed: %s. Retrying in %.1fs", attempt, e, delay)
            time.sleep(delay)
            delay *= 2  # exponential backoff
```

---

## Pitfalls

| Mistake | Fix |
|---------|-----|
| `os.path.join` everywhere | Use `pathlib.Path` / operator |
| `shell=True` in subprocess | Always use list form `["cmd", "arg"]` |
| Bare `except:` | Catch specific exceptions |
| `print()` for diagnostics | Use `logging` module |
| Hardcoded paths | Use `Path(__file__).parent` or args |
| No exit code | Return int from main, use `sys.exit()` |

---

## Related Skills

- `python-cli-tools` — when script needs subcommands or pip-installable entry point
- `python-testing` — test your script's `main()` by calling `main(parse_args([...]))`
- `python-packaging` — when script becomes a package
