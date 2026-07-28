#!/usr/bin/env python3
"""Regenerate the per-category DESCRIPTION.md files and the README catalog.

Reads every skills/<category>/<name>/SKILL.md, then writes:

* skills/<category>/DESCRIPTION.md   — index for that category
* README.md                          — the block between the catalog markers,
                                       plus the skill-count badge

Run after adding or renaming any skill:

    python3 tools/generate_catalog.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

CATALOG_START = "<!-- catalog:start -->"
CATALOG_END = "<!-- catalog:end -->"

DESCRIPTION_RE = re.compile(r'^description:\s*"?(.*?)"?\s*$', re.MULTILINE)
BADGE_RE = re.compile(r"(\[!\[Skills\]\(https://img\.shields\.io/badge/skills-)\d+(-)")

# One line per category, shown in DESCRIPTION.md and the README summary.
BLURBS = {
    "apm-metrics": "Metric-by-metric diagnostic references for platform components.",
    "aws": "AWS service design and troubleshooting patterns.",
    "containers": "Docker, Compose, image building, and runtime debugging.",
    "development": "Language, framework, and instrumentation patterns.",
    "documentation": "Technical writing, diagrams, and docs-site conventions.",
    "finops": "Cost analysis, rightsizing, and commitment planning.",
    "infrastructure": "GitOps, Helm, service mesh, and cluster infrastructure.",
    "linux": "Command line, filesystem, processes, systemd, and performance.",
    "networking": "TCP/IP, DNS, TLS, firewalls, and packet-level debugging.",
    "observability": "Telemetry pipelines, query languages, and signal correlation.",
    "projects": "Working context for specific repositories.",
    "security": "Supply chain, hardening, compliance, and vulnerability management.",
    "shell": "Bash scripting, text processing, CLI design, and shell testing.",
    "sre": "Reliability engineering: SLOs, incidents, and error budgets.",
    "troubleshooting": "Systematic diagnosis across systems, network, and logs.",
    "workflows": "Team conventions and delivery workflows.",
}


def read_description(path: Path) -> str:
    match = DESCRIPTION_RE.search(path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"{path}: no description in frontmatter")
    return match.group(1)


def extra_assets(skill_dir: Path) -> list[str]:
    """Subdirectories that ship alongside SKILL.md, for the catalog note."""
    labels = []
    for sub in ("references", "scripts", "examples", "templates"):
        target = skill_dir / sub
        if target.is_dir() and any(target.iterdir()):
            labels.append(f"{sub}/")
    return labels


def collect() -> dict[str, list[tuple[str, str, list[str]]]]:
    catalog: dict[str, list[tuple[str, str, list[str]]]] = {}
    for skill_md in sorted(REPO.glob("skills/*/*/SKILL.md")):
        category = skill_md.parent.parent.name
        name = skill_md.parent.name
        catalog.setdefault(category, []).append(
            (name, read_description(skill_md), extra_assets(skill_md.parent))
        )
    for skills in catalog.values():
        skills.sort()
    return catalog


def write_descriptions(catalog) -> None:
    for category, skills in catalog.items():
        lines = [f"# {category}", ""]
        if blurb := BLURBS.get(category):
            lines += [blurb, ""]
        lines += [f"{len(skills)} skills.", ""]
        for name, description, assets in skills:
            suffix = f" _({', '.join(assets)})_" if assets else ""
            lines.append(f"- **{name}** — {description}{suffix}")
        lines.append("")
        (REPO / "skills" / category / "DESCRIPTION.md").write_text(
            "\n".join(lines), encoding="utf-8"
        )


def render_catalog(catalog) -> str:
    lines: list[str] = []
    for category, skills in sorted(catalog.items()):
        blurb = BLURBS.get(category, "")
        lines += [
            "<details>",
            f"<summary><strong>{category}</strong> ({len(skills)})"
            f"{' — ' + blurb if blurb else ''}</summary>",
            "",
            "| Skill | Description | Includes |",
            "| --- | --- | --- |",
        ]
        for name, description, assets in skills:
            includes = ", ".join(f"`{a}`" for a in assets) or "—"
            lines.append(f"| `{name}` | {description} | {includes} |")
        lines += ["", "</details>", ""]
    return "\n".join(lines)


def update_readme(catalog) -> None:
    readme = REPO / "README.md"
    text = readme.read_text(encoding="utf-8")
    total = sum(len(v) for v in catalog.values())

    if CATALOG_START not in text or CATALOG_END not in text:
        print(
            f"error: README.md is missing the {CATALOG_START} / {CATALOG_END} markers",
            file=sys.stderr,
        )
        raise SystemExit(1)

    before = text.split(CATALOG_START)[0]
    after = text.split(CATALOG_END)[1]
    text = f"{before}{CATALOG_START}\n\n{render_catalog(catalog)}\n{CATALOG_END}{after}"

    text = BADGE_RE.sub(rf"\g<1>{total}\g<2>", text)
    text = re.sub(
        r"A catalog of \d+ platform engineering skills",
        f"A catalog of {total} platform engineering skills",
        text,
    )
    readme.write_text(text, encoding="utf-8")


def main() -> int:
    catalog = collect()
    if not catalog:
        print("error: no skills found", file=sys.stderr)
        return 1

    write_descriptions(catalog)
    update_readme(catalog)

    total = sum(len(v) for v in catalog.values())
    print(f"catalog: {total} skills across {len(catalog)} categories")
    for category, skills in sorted(catalog.items()):
        print(f"  {category:<16} {len(skills)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
