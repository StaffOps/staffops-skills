#!/usr/bin/env python3
"""Compute the WCAG contrast ratio between two hex colors.

No dependencies -- stdlib only. Implements the WCAG 2.x relative luminance
and contrast ratio formulas directly so the check can run anywhere Python 3
runs, with no browser or extension required.

Usage:
    python3 contrast-check.py <foreground-hex> <background-hex> [--large]

    --large   evaluate against the 3:1 threshold (large text >=18pt, or
              >=14pt bold, and UI components/graphical objects) instead of
              the default 4.5:1 threshold (normal text).

Exit code is 0 when the pair passes WCAG AA at the requested size, 1 when it
fails, 2 on a usage/input error.
"""

from __future__ import annotations

import sys


def _srgb_to_linear(channel: float) -> float:
    if channel <= 0.03928:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(ch * 2 for ch in hex_color)
    if len(hex_color) != 6:
        raise ValueError(f"not a valid hex color: {hex_color!r}")

    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))
    r, g, b = (_srgb_to_linear(c) for c in (r, g, b))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    lum_a = relative_luminance(hex_a)
    lum_b = relative_luminance(hex_b)
    lighter, darker = max(lum_a, lum_b), min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    large = "--large" in argv

    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        return 2

    try:
        ratio = contrast_ratio(args[0], args[1])
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    threshold = 3.0 if large else 4.5
    passed = ratio >= threshold
    size_label = "large text / UI components (3:1)" if large else "normal text (4.5:1)"

    print(f"{args[0]} on {args[1]}: ratio = {ratio:.2f}:1, threshold = {size_label}")
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
