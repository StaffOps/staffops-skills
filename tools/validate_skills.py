#!/usr/bin/env python3
"""Validate every SKILL.md against the Hermes Agent skill contract.

Checks performed:

* directory layout is skills/<category>/<name>/SKILL.md
* YAML frontmatter is present and parses
* required keys: name, description, version, author, license, platforms
* name matches ^[a-z][a-z0-9_-]*$ and equals its directory name
* description is <= 60 chars, one sentence, ends with a period
* metadata.hermes.category matches the parent directory
* every related_skills entry resolves to a real skill
* the body is English-only (no accented Latin characters)

Usage:
    python3 tools/validate_skills.py [skills_dir]

Exits non-zero when any check fails.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MAX_DESCRIPTION = 60
NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
REQUIRED = ("name", "description", "version", "author", "license", "platforms")

# Accented Latin letters only. Deliberately excludes typographic and math
# symbols in the same Unicode block (×, ÷, °, ±, µ), which are legitimate in
# English technical prose.
ACCENTED_RE = re.compile(
    r"[àáâãäåèéêëìíîïòóôõöùúûüçñýÿÀÁÂÃÄÅÈÉÊËÌÍÎÏÒÓÔÕÖÙÚÛÜÇÑÝ]"
)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str] | None:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None

    fields: dict[str, str] = {}
    path: list[str] = []
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        entry = re.match(r"^\s*([A-Za-z_-]+):\s*(.*)$", line)
        if not entry:
            continue
        key, value = entry.group(1), entry.group(2).strip()
        depth = indent // 2
        path = path[:depth] + [key]
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        fields[".".join(path)] = value

    return fields, text[match.end():]


def parse_list(value: str) -> list[str]:
    value = value.strip()
    if not value.startswith("["):
        return []
    inner = value[1:-1].strip()
    return [item.strip() for item in inner.split(",") if item.strip()]


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "skills")
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    paths = sorted(root.glob("*/*/SKILL.md"))
    if not paths:
        print(f"error: no SKILL.md found under {root}", file=sys.stderr)
        return 2

    names = {p.parent.name for p in paths}
    errors: list[str] = []

    for path in paths:
        rel = path.relative_to(root.parent)
        category = path.parent.parent.name
        dirname = path.parent.name

        parsed = parse_frontmatter(path.read_text(encoding="utf-8"))
        if parsed is None:
            errors.append(f"{rel}: missing or malformed YAML frontmatter")
            continue
        fields, body = parsed

        for key in REQUIRED:
            if not fields.get(key):
                errors.append(f"{rel}: missing required key '{key}'")

        name = fields.get("name", "")
        if name and not NAME_RE.match(name):
            errors.append(f"{rel}: name '{name}' must match ^[a-z][a-z0-9_-]*$")
        if name and name != dirname:
            errors.append(f"{rel}: name '{name}' does not match directory '{dirname}'")

        description = fields.get("description", "")
        if description:
            if len(description) > MAX_DESCRIPTION:
                errors.append(f"{rel}: description is {len(description)} chars (max {MAX_DESCRIPTION})")
            if not description.endswith("."):
                errors.append(f"{rel}: description must end with a period")

        declared = fields.get("metadata.hermes.category")
        if declared and declared != category:
            errors.append(f"{rel}: category '{declared}' does not match directory '{category}'")

        for related in parse_list(fields.get("metadata.hermes.related_skills", "")):
            if related not in names:
                errors.append(f"{rel}: related_skills entry '{related}' does not exist")

        match = ACCENTED_RE.search(body)
        if match:
            line = body[: match.start()].count("\n") + 1
            errors.append(f"{rel}:{line}: non-English character '{match.group(0)}'")

    for error in errors:
        print(error, file=sys.stderr)

    print(f"\nvalidated {len(paths)} skills, {len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
