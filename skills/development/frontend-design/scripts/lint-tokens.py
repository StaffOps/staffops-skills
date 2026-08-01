#!/usr/bin/env python3
"""Objective lint pass over built CSS (or any text output) for design tells.

This is a mechanical check, not a taste check -- it does not replace the
brainstorm/self-critique gate in SKILL.md, it catches the things that gate
relies on human judgment to remember: too many font families, an
uncontrolled number of accent colors, and the exact cliche hex values
leaking into the final output unchanged.

Usage:
    python3 lint-tokens.py <file> [<file> ...]

Exit code is 0 when no warnings fire, 1 when at least one does, 2 on a usage
error (no files given, or a file that could not be read -- that is a broken
invocation, not a design finding, so it does not share the warning exit
code). This is a signal to look closer, not a hard gate -- a legitimate
brief can justify 3 font families or a cliche hex value that happens to fit.
"""

from __future__ import annotations

import re
import sys

FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}\n]+)", re.IGNORECASE)
# 8-digit form first (CSS Color Module 4 alpha hex, e.g. #0f172aff) so an
# alpha-suffixed cliche color is not missed just because two extra digits
# follow it; the base 6 (or 3) digits are what gets compared/counted below.
HEX_COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")

# Exact hex values with a well-known association to a recognizable
# AI-generated-design fingerprint (see SKILL.md's named cliches section).
# Near-black-plus-neon-accent and the broadsheet layout are structural /
# fuzzy rather than one exact hex, so they are not checked here -- read
# them by eye instead.
CLICHE_HEXES = {
    "#f4f1ea": "warm cream background (cliche #1: cream + serif + terracotta)",
    "#0f172a": "Tailwind slate-900 (cliche #4: default shadcn/Tailwind look)",
    "#f8fafc": "Tailwind slate-50 (cliche #4: default shadcn/Tailwind look)",
    "#4f46e5": "Tailwind/shadcn indigo-600 primary (cliche #4)",
    "#8b5cf6": "generic violet used in purple-to-blue gradient hero (cliche #5)",
    "#3b82f6": "generic blue used in purple-to-blue gradient hero (cliche #5)",
}

FONT_FAMILY_WARN_THRESHOLD = 2
ACCENT_COLOR_WARN_THRESHOLD = 6


def normalize_family(raw: str) -> str:
    first = raw.split(",")[0].strip()
    return first.strip("'\" ")


def normalize_hex(raw: str) -> str:
    """Strip an 8-digit form's trailing alpha channel down to # + 6 hex
    digits, so #0f172aff and #0f172a compare and count as the same color."""
    value = raw.lower()
    if len(value) == 9:  # "#" + 8 hex digits (RRGGBBAA)
        return value[:7]
    return value


def lint_file(path: str) -> list[str]:
    warnings: list[str] = []
    text = open(path, encoding="utf-8").read()

    families = {normalize_family(m) for m in FONT_FAMILY_RE.findall(text)}
    families.discard("")
    hexes = {normalize_hex(m) for m in HEX_COLOR_RE.findall(text)}

    print(f"{path}:")
    print(f"  distinct font families: {len(families)} {sorted(families)}")
    print(f"  distinct hex colors:    {len(hexes)}")

    if len(families) > FONT_FAMILY_WARN_THRESHOLD:
        warnings.append(
            f"{path}: {len(families)} font families found (usually 2, rarely 3+) "
            f"-- confirm each one has a stated role"
        )

    if len(hexes) > ACCENT_COLOR_WARN_THRESHOLD:
        warnings.append(
            f"{path}: {len(hexes)} distinct hex colors found -- a 4-6 color token "
            f"system (SKILL.md Pass 1) usually means far fewer literals in the "
            f"built output; check for one-off colors that should reuse a token"
        )

    for hex_value in hexes:
        if hex_value in CLICHE_HEXES:
            warnings.append(f"{path}: found {hex_value} -- {CLICHE_HEXES[hex_value]}")

    return warnings


def main(argv: list[str]) -> int:
    if not argv or "-h" in argv or "--help" in argv:
        print(__doc__, file=sys.stderr)
        return 0 if argv else 2

    all_warnings: list[str] = []
    for path in argv:
        try:
            with open(path, encoding="utf-8"):
                pass
        except OSError as exc:
            print(f"usage error: could not read {path}: {exc}", file=sys.stderr)
            return 2
        all_warnings.extend(lint_file(path))

    if all_warnings:
        print("\nwarnings:")
        for warning in all_warnings:
            print(f"  - {warning}")
    else:
        print("\nno warnings")

    return 1 if all_warnings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
