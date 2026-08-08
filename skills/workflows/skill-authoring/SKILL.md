---
name: skill-authoring
description: "Use when creating a new SKILL.md, rewriting a description that doesn't trigger correctly, splitting an overgrown skill into references/, or deciding whether something belongs as a skill vs steering vs runbook. Covers the canonical template, frontmatter rules, description formula, collision checks, and pre-flight checklist."
---
# Skill Authoring

How to write a well-formed skill that triggers on the right prompts, stays
scannable, and doesn't collide with the 100+ others in the catalog. Stops at
"is this skill well-formed" — behavioral testing is `skill-eval-harness`.

## When to use

- Drafting a brand-new `SKILL.md`
- Rewriting a description that triggers on wrong prompts (or doesn't trigger at all)
- Deciding if content belongs in a skill, steering rule, or runbook
- Splitting a >200-line skill into `references/`
- Running a pre-flight pass before handing to `skill-eval-harness`

## When NOT to use

- **Typo fix with no triggering impact** — just validate and commit
- **Writing steering rules** — steering is always-active, different format
- **Documenting a one-off procedure** — use a runbook, not a skill
- **Agent config** (MCP, agent JSON) — that's setup, not skill content

## Decision tree: skill vs steering vs runbook?

```
Is it always-active knowledge the agent must follow on EVERY task?
├── YES → steering rule (.kiro/steering/*.md)
└── NO → Is it on-demand knowledge loaded only when relevant?
    ├── YES → SKILL (skills/<category>/<name>/SKILL.md)
    └── NO → Is it a step-by-step procedure for a specific incident/task?
        ├── YES → runbook (docs/ or runbooks/)
        └── NO → probably a README section or HOW-TO
```

## The SKILL.md template

See `references/skill-template.md` for a copy-paste ready version. Core structure:

```yaml
---
name: <skill-name>          # matches directory name, [a-z][a-z0-9_-]*
description: "<100-1024 chars, starts with 'Use when...', from agent's POV>"
---
```

```markdown
# Title (Human-Friendly)

1-3 sentence intro: what this covers, what it deliberately does NOT.

## When to use
Concrete trigger conditions. Include symptom-shaped phrasing.

## When NOT to use
What this is NOT for — prevents false triggers.

## Steps / Core content
The actual knowledge. Copy-paste ready. No walls of text.

## Decision tree (optional)
Quick routing logic for branching scenarios.

## Anti-patterns
What NOT to do — the mistakes this skill prevents.

## Related skills
- [name](relative-path) — one-line reason to reach for it instead/additionally.
```

## Writing a good description (the critical field)

The `description` is the ONLY thing loaded for ALL skills at all times.
It determines whether the skill triggers. Get it wrong = skill is dead.

### Formula

```
"Use when <concrete trigger situation>, <second trigger>, or <symptom-phrasing>.
Covers <what the skill actually teaches>."
```

### Rules

| Rule | Why |
|------|-----|
| 100-1024 characters | Too short = no signal; too long = wastes always-loaded context |
| Starts with `Use when...` | Agent's POV — matches how routing logic reads it |
| Names tools/symptoms/verbs | Search tokens for routing |
| Does NOT restate the skill name | Redundant — the name is already indexed |
| Written from the agent's perspective | "Use when diagnosing..." not "This skill helps users..." |

### Before/After

```yaml
# ❌ BAD — vague, name-echoing, no trigger signal
description: "How to author skills for the catalog."

# ✅ GOOD — concrete triggers, symptoms, tools named
description: "Use when creating a new SKILL.md, rewriting a description that doesn't trigger correctly, splitting an overgrown skill into references/, or deciding whether something belongs as a skill vs steering vs runbook."
```

## The `references/` convention

| Goes in `references/` | Stays inline in SKILL.md |
|-----------------------|--------------------------|
| Lookup tables >20 rows | Short tables (<20 rows) |
| Full JSON/YAML schemas | Brief schema snippets |
| Reusable script templates | One-liner commands |
| Detailed worked examples | Quick examples (3-5 lines) |
| Multi-page specs | Summary + pointer |

**Earn the directory.** Don't scaffold empty `references/`. Create it when:
- A table or spec exceeds ~50 lines and would dilute the body
- Content is pure lookup (no narrative needed to understand it)
- A template needs to be copy-pasted verbatim (put it in `references/`)

Point to references from the body with a one-line pointer:
```markdown
> Full schema: see `references/case-schema.md`
```

## Collision check before shipping

With 100+ skills, overlapping descriptions cause mis-routing. Always check:

```bash
python3 scripts/eval_harness.py collision-check \
  --skill skills/<category>/<name>/SKILL.md
```

A hit at ≥0.5 Jaccard overlap means: narrow your wording so the two skills
stop competing, OR confirm they should compete and adjust the loser to be
more specific about its unique coverage.

## Pre-flight checklist

Before treating a new or edited skill as done:

- [ ] Path is `skills/<category>/<name>/SKILL.md`
- [ ] `name` matches directory and `^[a-z][a-z0-9_-]*$`
- [ ] `description` is 100-1024 chars, starts with `Use when...`
- [ ] Description names concrete triggers/symptoms, not just the topic
- [ ] Body opens with H1 + 1-3 sentence intro
- [ ] `## When to use` has symptom-shaped phrasing (user's vocabulary, not yours)
- [ ] `## When NOT to use` exists (prevents false triggers)
- [ ] `## Anti-patterns` exists
- [ ] No org-specific hostnames, account IDs, or paths — use `<placeholder>`
- [ ] No empty `references/` scaffolded "for later"
- [ ] Repeated workaround (3+ uses) moved to `references/`, not typed out N ways
- [ ] `collision-check` ran with no unresolved overlap ≥0.5
- [ ] Validator passes: `python3 tools/validate_skills.py`

## Anti-patterns

- **Copying a sibling's description and tweaking one word.** Verify with
  collision-check — small edits rarely stay distinct in a large catalog.
- **Writing trigger language only in YOUR vocabulary.** Include how a
  different engineer would phrase the same need.
- **A wall of MUST/NEVER with no stated reason.** Explain WHY — the agent
  generalizes better from explained constraints.
- **Restating the skill name inside the description.** Wastes characters
  on information already indexed.
- **Empty `references/` or `scripts/` scaffolded "to fill later."** These
  earn their place through content, not through aspiration.
- **Skipping collision-check "because overlap is obviously not there."**
  Overlap in 100+ skills is rarely obvious by inspection.
- **>250 lines in SKILL.md without splitting.** If it's that long, lookup
  tables or schemas should move to `references/`.

## Related skills

- [skill-eval-harness](../skill-eval-harness/SKILL.md) — testing whether the skill actually behaves correctly.
- [skill-share](../skill-share/SKILL.md) — packaging and distributing skills.
- [how-this-agent-works](../how-this-agent-works/SKILL.md) — understanding where skills fit in the agent architecture.
