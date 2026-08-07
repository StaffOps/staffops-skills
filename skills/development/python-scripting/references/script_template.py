#!/usr/bin/env python3
"""DESCRIPTION: What this script does in one line.

Usage:
    ./script_template.py input.json -o output.json
    ./script_template.py input.json -v  # verbose
    cat data.json | ./script_template.py -  # stdin
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def main(args: argparse.Namespace) -> int:
    """Core logic. Returns 0 on success, non-zero on failure."""
    input_path = Path(args.input) if args.input != "-" else None

    # Read input
    if input_path:
        if not input_path.exists():
            log.error("Input not found: %s", input_path)
            return 1
        data = json.loads(input_path.read_text(encoding="utf-8"))
    else:
        data = json.load(sys.stdin)

    log.info("Loaded %d items", len(data) if isinstance(data, list) else 1)

    # --- PROCESS ---
    result = data  # replace with actual logic

    # Write output
    output = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output == "-":
        print(output)
    else:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
        log.info("Written to %s", args.output)

    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input", help="Input file (or '-' for stdin)")
    p.add_argument("-o", "--output", default="-", help="Output file (default: stdout)")
    p.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    return p.parse_args(argv)


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,  # logs to stderr, output to stdout
    )


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    sys.exit(main(args))
