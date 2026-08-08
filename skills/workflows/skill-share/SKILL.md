---
name: skill-share
description: "Use when scaffolding a new skill directory, running per-skill validation, packaging a skill as a zip for distribution, or formatting an announcement summary. Covers the scaffold/validate/package/announce lifecycle with vendor-agnostic distribution."
---
# Skill Share

The packaging/distribution half of shipping a skill. `skill-authoring` covers
whether content is well-structured; this skill covers generating the scaffold,
validating one skill in isolation, zipping for distribution, and formatting
announcements.

## When to use

- Starting a new skill and want frontmatter pre-filled correctly
- Running validation scoped to ONE skill (not the whole catalog)
- Packaging a skill directory as a distributable zip
- Formatting a plain-text announcement for any channel (Slack, PR, email)

## When NOT to use

- **Judging description quality or trigger accuracy** — that's `skill-authoring`
- **Behavioral testing** — that's `skill-eval-harness`
- **Sharing org-specific secrets/endpoints** — never distribute those
- **Sharing incomplete/draft skills** — validate first

## The four subcommands

### `scaffold` — generate the skeleton

```bash
python3 scripts/skill_share.py scaffold <category> <name> --author "Your Name"
```

Creates `skills/<category>/<name>/SKILL.md` with:
- `name` and directory matching
- `description` as `"Use when TODO. Covers TODO."` (placeholder to fill)
- Correct body structure (H1, intro placeholder, When to use, Anti-patterns)

The file is structurally valid out of the box — content is on you.

### `validate` — scoped validation + dangling reference check

```bash
python3 scripts/skill_share.py validate skills/<category>/<name>
```

Runs `tools/validate_skills.py` scoped to one skill, plus:
- **Dangling reference check**: any path mentioned in inline code (e.g.
  `references/foo.md`) is verified to exist in the skill directory
- Prints the `collision-check` command to run next

### `package` — zip for distribution (gated on validate)

```bash
python3 scripts/skill_share.py package skills/<category>/<name> --output-dir dist/
```

Runs validation first (hard gate — fails refuse packaging). On success:
- Zips to `<name>-<version>.zip` (or `<name>.zip` if no version)
- Excludes: `__pycache__/`, `.pytest_cache/`, `.git/`, `.DS_Store`, `*.pyc`
- Archive rooted at `<name>/`

### `announce` — vendor-agnostic summary

```bash
python3 scripts/skill_share.py announce skills/<category>/<name>
```

Formats name, description, and first paragraph into a plain-text block
on stdout. Copy-paste into whatever channel your team uses.
Does NOT call any API — no Slack/Teams coupling.

## Workflow

```
1. scaffold <category> <name>     → skeleton created
2. Write content (see skill-authoring)
3. validate <path>                → structural + reference check
4. collision-check (from eval-harness) → trigger overlap check
5. package <path>                 → distributable zip
6. announce <path>                → copy-paste summary
```

## Anti-patterns

- **Hand-writing frontmatter from memory instead of `scaffold`.** Typos in
  mechanical fields are exactly what scaffold prevents.
- **Reading full-catalog validator output to find your skill.** `validate`
  already scopes and filters for you.
- **Treating validate PASS as equivalent to skill-authoring's checklist.**
  Structural validity ≠ good triggering or well-written content.
- **Packaging without validation.** `package` gates on it anyway, but
  reading the report first saves a step on failure.
- **Skipping collision-check** because overlap "obviously isn't there."
- **Bolting a chat API onto announce.** Keep it plain-text; wire the
  delivery outside this tool.


## Decision tree

```
What phase of skill sharing?
├── Scaffold a new skill?
│   └── skill-share scaffold NAME → creates SKILL.md + metadata template
├── Validate before publishing?
│   ├── Format OK? → skill-share validate PATH (checks structure/frontmatter)
│   ├── Content quality? → run skill-eval-harness for precision + scenario
│   └── No collisions? → check skill catalog for overlapping triggers
├── Package for distribution?
│   ├── Single skill → skill-share package PATH → outputs .tar.gz
│   └── Batch (category) → skill-share package --category shell
└── Announce / publish?
    ├── Internal catalog → skill-share announce --catalog PATH
    └── Cross-team → PR to shared skills repo + CHANGELOG entry
```

## Related skills

- [skill-authoring](../skill-authoring/SKILL.md) — writing the content that scaffold sets up.
- [skill-eval-harness](../skill-eval-harness/SKILL.md) — behavioral testing before sharing.
- [how-this-agent-works](../how-this-agent-works/SKILL.md) — understanding skill registry architecture.
