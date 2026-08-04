#!/usr/bin/env python3
"""Scaffold, validate, package, and announce a catalog skill.

This is the mechanical packaging/distribution half of shipping a skill in
this catalog. It deliberately does not judge whether a skill's content is
good, well-scoped, or worded to trigger correctly — that is
`skill-authoring`'s job (see its `SKILL.md` and pre-flight checklist), and
this tool assumes that pass already happened. It also does not re-implement
the structural/frontmatter validator that already exists at
`tools/validate_skills.py`, and it does not re-implement the trigger-overlap
scan that already exists in `skill-eval-harness`'s `collision-check`
subcommand — both are called out by name, at the exact command a user should
run, rather than duplicated here.

Subcommands:
    scaffold    Create a new skills/<category>/<name>/SKILL.md with
                correct frontmatter pre-filled and CONTRIBUTING.md's body
                template in place.
    validate    Thin wrapper around tools/validate_skills.py, scoped to one
                skill, plus a dangling-reference check that tool does not
                perform: every `references/...` or `scripts/...` path
                mentioned as inline code in the body must exist on disk.
    package     Zip a skill directory into a distributable archive, after
                running `validate` as a hard gate — packaging a skill that
                fails validation is refused, not warned about.
    announce    Format a short, copy-pasteable announcement of a skill
                (name, description, what it does) to stdout or a file. This
                deliberately does not send it anywhere — plug the output
                into whatever channel your team actually uses instead of
                hardcoding one vendor's chat API here.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import zipfile
from pathlib import Path

# Path.parents[4] from scripts/skill_share.py -> .../skill-share/scripts/skill_share.py
#   [0] scripts  [1] skill-share  [2] workflows  [3] skills  [4] repo root
HERE = Path(__file__).resolve()
SKILL_ROOT = HERE.parents[1]
REPO_ROOT = HERE.parents[4] if len(HERE.parents) > 4 else SKILL_ROOT
DEFAULT_SKILLS_DIR = REPO_ROOT / "skills"
VALIDATE_SKILLS_TOOL = REPO_ROOT / "tools" / "validate_skills.py"
COLLISION_CHECK_SCRIPT = (
    REPO_ROOT / "skills" / "workflows" / "skill-eval-harness" / "scripts" / "eval_harness.py"
)

NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")

# ---------------------------------------------------------------------------
# Minimal frontmatter reader, deliberately self-contained (same convention
# skill-eval-harness's eval_harness.py follows): a skill's scripts/
# directory should keep working if the skill folder is copied elsewhere, so
# this does not import tools/validate_skills.py across the repo root.
# ---------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


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


def resolve_skill_md(raw_path: Path) -> Path:
    """Accept either a skill directory or a direct path to its SKILL.md."""
    path = raw_path.resolve()
    if path.is_file() and path.name == "SKILL.md":
        return path
    candidate = path / "SKILL.md"
    if candidate.is_file():
        return candidate
    raise SystemExit(f"error: no SKILL.md found at or under {raw_path}")


# ---------------------------------------------------------------------------
# scaffold
# ---------------------------------------------------------------------------

FRONTMATTER_TEMPLATE = """---
name: {name}
description: "TODO: describe this skill in one sentence."
version: 1.0.0
author: {author}
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [TODO, TODO, TODO]
    category: {category}
    related_skills: []
---
"""

# Body shape is CONTRIBUTING.md's own template, copied verbatim so a
# scaffolded skill and a hand-written one are structurally identical.
BODY_TEMPLATE = """# {title}

TODO: two or three sentences on what this covers and what it deliberately
does not.

## When to Use

TODO: the trigger conditions -- the symptoms or tasks that should make an
agent reach for this skill.

## ...substance...

## Anti-patterns

TODO: what not to do, and why.
"""


def cmd_scaffold(args: argparse.Namespace) -> int:
    name = args.name
    category = args.category
    if not NAME_RE.match(name):
        print(f"error: name '{name}' must match ^[a-z][a-z0-9_-]*$", file=sys.stderr)
        return 2
    if not NAME_RE.match(category):
        print(f"error: category '{category}' must match ^[a-z][a-z0-9_-]*$", file=sys.stderr)
        return 2

    skills_dir = args.skills_dir
    skill_dir = skills_dir / category / name
    skill_md = skill_dir / "SKILL.md"

    if skill_md.exists() and not args.force:
        print(f"error: {skill_md} already exists (pass --force to overwrite)", file=sys.stderr)
        return 1

    skill_dir.mkdir(parents=True, exist_ok=True)
    title = name.replace("-", " ").replace("_", " ").title()
    content = FRONTMATTER_TEMPLATE.format(name=name, author=args.author, category=category)
    content += "\n" + BODY_TEMPLATE.format(title=title)
    skill_md.write_text(content, encoding="utf-8")

    print(f"scaffolded {skill_md}")
    if not (skills_dir / category).is_dir() or not any(
        p.name != name for p in (skills_dir / category).iterdir() if p.is_dir()
    ):
        print(
            f"note: '{category}' has no other skills under {skills_dir} yet -- "
            "confirm this is the right category before filling it in."
        )
    print(
        "\nnext: replace every TODO in the frontmatter and body, then run:\n"
        f"  python3 {SKILL_ROOT_RELATIVE_SCRIPT()} validate {skill_dir}"
    )
    _print_collision_reminder(skill_md)
    return 0


def SKILL_ROOT_RELATIVE_SCRIPT() -> str:
    try:
        return str(HERE.relative_to(REPO_ROOT))
    except ValueError:
        return str(HERE)


# ---------------------------------------------------------------------------
# validate: thin wrapper around tools/validate_skills.py + dangling refs
# ---------------------------------------------------------------------------

FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
# Only treat an inline-code span as a file reference if it looks like a
# bundled-resource path with an extension -- this avoids false positives on
# bare mentions like `references/` or shell commands that merely contain a
# path as one argument among several (those have spaces and won't match).
PATH_REF_RE = re.compile(r"^(?:references|scripts|examples)/[\w.\-/]+\.\w+$")


def find_dangling_references(skill_dir: Path, body: str) -> list[str]:
    """Inline-code paths under references/, scripts/, examples/ that don't exist.

    This is the one gap skill-authoring's own text flags in the existing
    tooling: tools/validate_skills.py checks frontmatter and English-only
    prose, but never confirms that a `references/foo.md` or `scripts/bar.py`
    mentioned in the body actually exists on disk.
    """
    stripped = FENCE_RE.sub("", body)
    issues: list[str] = []
    seen: set[str] = set()
    for match in INLINE_CODE_RE.finditer(stripped):
        ref = match.group(1).strip()
        if ref in seen or not PATH_REF_RE.match(ref):
            continue
        seen.add(ref)
        if not (skill_dir / ref).exists():
            issues.append(ref)
    return sorted(issues)


def _print_collision_reminder(skill_md: Path) -> None:
    if not COLLISION_CHECK_SCRIPT.is_file():
        return
    try:
        rel_script = COLLISION_CHECK_SCRIPT.relative_to(REPO_ROOT)
    except ValueError:
        rel_script = COLLISION_CHECK_SCRIPT
    print(
        "recommended: run skill-eval-harness's collision-check against the "
        f"real catalog before shipping this skill:\n"
        f"  python3 {rel_script} collision-check --skill {skill_md}"
    )


def run_validation(skill_md: Path, skills_dir_override: Path | None) -> tuple[bool, list[str]]:
    """Run tools/validate_skills.py scoped to one skill, plus dangling refs.

    Returns (ok, report_lines). Does not print -- callers decide how much
    of the report to show.
    """
    skill_dir = skill_md.parent
    # Default scope: the skill's own grandparent-of-grandparent, i.e. the
    # "skills/" analog directory it actually lives under. For a real
    # catalog skill that IS skills/; for a throwaway single-skill copy
    # under /tmp it is that copy's own skills/ directory, so the wrapped
    # validator only ever sees what's actually there.
    skills_root = skills_dir_override or skill_md.parents[2]

    report: list[str] = []
    ok = True

    if not VALIDATE_SKILLS_TOOL.is_file():
        report.append(f"error: {VALIDATE_SKILLS_TOOL} not found -- cannot run the real validator")
        return False, report

    result = subprocess.run(
        [sys.executable, str(VALIDATE_SKILLS_TOOL), str(skills_root)],
        capture_output=True,
        text=True,
    )
    # validate_skills.py reports paths relative to skills_root.parent, which
    # always reconstructs as "<skills_root.name>/<category>/<name>/SKILL.md".
    rel = (Path(skills_root.name) / skill_md.relative_to(skills_root)).as_posix()
    stderr_lines = [line for line in result.stderr.splitlines() if line.strip()]
    own_errors = [line for line in stderr_lines if line.startswith(rel + ":")]
    summary = next((line for line in result.stdout.splitlines() if line.startswith("validated ")), "")

    report.append(f"catalog validator (tools/validate_skills.py) scoped to {skills_root}:")
    if own_errors:
        ok = False
        for line in own_errors:
            report.append(f"  {line}")
    else:
        report.append("  no frontmatter/structure errors for this skill.")
    if summary:
        report.append(f"  ({summary} -- includes any other skills under {skills_root})")

    dangling = find_dangling_references(skill_dir, skill_md.read_text(encoding="utf-8"))
    if dangling:
        ok = False
        report.append("dangling references (mentioned in the body, missing on disk):")
        for ref in dangling:
            report.append(f"  {skill_dir / ref}  (referenced as `{ref}`)")
    else:
        report.append("dangling references: none found.")

    return ok, report


def cmd_validate(args: argparse.Namespace) -> int:
    skill_md = resolve_skill_md(args.path)
    ok, report = run_validation(skill_md, args.skills_dir)
    for line in report:
        print(line)
    print()
    _print_collision_reminder(skill_md)
    if not ok:
        print("\nFAIL", file=sys.stderr)
        return 1
    print("PASS")
    return 0


# ---------------------------------------------------------------------------
# package
# ---------------------------------------------------------------------------

EXCLUDE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".git", ".mypy_cache"}
EXCLUDE_FILE_NAMES = {".DS_Store"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def build_zip(skill_dir: Path, output_path: Path) -> list[str]:
    included: list[str] = []
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(skill_dir.rglob("*")):
            if path.is_dir():
                continue
            rel_parts = path.relative_to(skill_dir).parts
            if any(part in EXCLUDE_DIR_NAMES for part in rel_parts):
                continue
            if path.name in EXCLUDE_FILE_NAMES or path.suffix in EXCLUDE_SUFFIXES:
                continue
            arcname = str(Path(skill_dir.name) / path.relative_to(skill_dir))
            zf.write(path, arcname)
            included.append(arcname)
    return included


def cmd_package(args: argparse.Namespace) -> int:
    skill_md = resolve_skill_md(args.path)
    skill_dir = skill_md.parent

    ok, report = run_validation(skill_md, args.skills_dir)
    for line in report:
        print(line)
    if not ok:
        print(
            "\nrefusing to package: validation failed. Fix the errors above and "
            "re-run `validate` before packaging.",
            file=sys.stderr,
        )
        return 1

    parsed = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    fields = parsed[0] if parsed else {}
    version = fields.get("version", "0.0.0")

    output_dir = args.output_dir or Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{skill_dir.name}-{version}.zip"

    included = build_zip(skill_dir, output_path)
    print(f"\npackaged {len(included)} file(s) -> {output_path}")
    for name in included:
        print(f"  {name}")
    return 0


# ---------------------------------------------------------------------------
# announce
# ---------------------------------------------------------------------------


def _first_paragraph_after_title(body: str) -> str:
    lines = body.strip("\n").splitlines()
    # Skip the H1 title line itself.
    start = 1 if lines and lines[0].startswith("# ") else 0
    paragraph: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped:
            if paragraph:
                break
            continue
        if stripped.startswith("#"):
            break
        paragraph.append(stripped)
    return " ".join(paragraph)


def cmd_announce(args: argparse.Namespace) -> int:
    skill_md = resolve_skill_md(args.path)
    text = skill_md.read_text(encoding="utf-8")
    parsed = parse_frontmatter(text)
    if parsed is None:
        print(f"error: {skill_md} has no valid frontmatter", file=sys.stderr)
        return 1
    fields, body = parsed

    name = fields.get("name", skill_md.parent.name)
    description = fields.get("description", "").strip()
    category = fields.get("metadata.hermes.category", skill_md.parent.parent.name)
    version = fields.get("version", "0.0.0")
    intro = _first_paragraph_after_title(body)

    try:
        rel_path = skill_md.relative_to(REPO_ROOT)
    except ValueError:
        rel_path = skill_md

    lines = [
        f"New skill: {name} (v{version})",
        description,
        "",
    ]
    if intro:
        lines.append("What it does:")
        lines.append(intro)
        lines.append("")
    lines.append(f"Category: {category}")
    lines.append(f"Path: {rel_path}")

    message = "\n".join(lines).rstrip() + "\n"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(message, encoding="utf-8")
        print(f"wrote announcement -> {args.output}")
    else:
        print(message, end="")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scaffold = subparsers.add_parser("scaffold", help="Create a new skill from the CONTRIBUTING.md template")
    scaffold.add_argument("category", help="Category directory under skills/ (e.g. workflows)")
    scaffold.add_argument("name", help="Skill name, must match ^[a-z][a-z0-9_-]*$")
    scaffold.add_argument("--skills-dir", type=Path, default=DEFAULT_SKILLS_DIR, help="Root skills/ directory to scaffold under (default: this catalog's skills/).")
    scaffold.add_argument("--author", default="TODO: your name")
    scaffold.add_argument("--force", action="store_true", help="Overwrite an existing SKILL.md.")
    scaffold.set_defaults(handler=cmd_scaffold)

    validate = subparsers.add_parser(
        "validate", help="Run tools/validate_skills.py scoped to one skill, plus a dangling-reference check"
    )
    validate.add_argument("path", type=Path, help="Skill directory or path to its SKILL.md")
    validate.add_argument(
        "--skills-dir",
        type=Path,
        default=None,
        help="Catalog root to validate against (default: auto-detected as the skill's own skills/ directory).",
    )
    validate.set_defaults(handler=cmd_validate)

    package = subparsers.add_parser("package", help="Zip a skill directory after validation passes")
    package.add_argument("path", type=Path, help="Skill directory or path to its SKILL.md")
    package.add_argument("--skills-dir", type=Path, default=None, help="Same override as `validate`.")
    package.add_argument("--output-dir", type=Path, default=None, help="Where to write the zip (default: current directory).")
    package.set_defaults(handler=cmd_package)

    announce = subparsers.add_parser("announce", help="Format a copy-pasteable announcement for a skill")
    announce.add_argument("path", type=Path, help="Skill directory or path to its SKILL.md")
    announce.add_argument("--output", type=Path, default=None, help="Write to this file instead of stdout.")
    announce.set_defaults(handler=cmd_announce)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
