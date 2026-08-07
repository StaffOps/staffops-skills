# Skill Template — Copy-Paste Ready

Copy this entire file as your starting point. Replace all `<placeholders>`.

---

## The file: `skills/<category>/<name>/SKILL.md`

```markdown
---
name: <skill-name>
description: "Use when <concrete trigger 1>, <trigger 2>, or <symptom-phrasing that a user would type>. Covers <what the skill teaches — tools, patterns, decisions>."
---
# <Human-Friendly Title>

<1-3 sentences: what this skill covers and what it deliberately does NOT.
Keep it tight — this is the first thing loaded after triggering.>

## When to use

- <Concrete situation 1>
- <Concrete situation 2>
- <Symptom-shaped phrasing: what the user says/sees that should route here>

## When NOT to use

- **<Wrong-use case 1>** — use <other-skill> instead
- **<Wrong-use case 2>** — that's a <steering/runbook/README> concern

## <Core Content Section — name it by what it teaches>

<The actual knowledge. Be copy-paste ready. Use tables, short code blocks,
decision trees. No walls of text.>

### Subsection if needed

<Keep subsections to 2 levels max (## and ###). Deeper = refactor.>

## Decision tree (optional — include when routing logic helps)

```
Is <condition A>?
├── YES → <action/recommendation>
└── NO → Is <condition B>?
    ├── YES → <different action>
    └── NO → <fallback>
```

## Anti-patterns

- **<Mistake 1>.** <Why it's wrong — explain, don't just forbid.>
- **<Mistake 2>.** <What breaks and how to do it right.>
- **<Mistake 3>.** <Concrete consequence of the anti-pattern.>

## Related skills

- [<skill-name>](<relative-path>) — <one-line reason to reach for it>.
- [<skill-name>](<relative-path>) — <when to use this instead>.
```

---

## Frontmatter rules

| Field | Required | Constraint |
|-------|----------|-----------|
| `name` | ✅ | Must match directory name. Pattern: `^[a-z][a-z0-9_-]*$` |
| `description` | ✅ | 100-1024 chars. Starts with `Use when...`. Agent's POV. |
| `version` | Optional | SemVer for attribution. Not enforced by tooling. |
| `author` | Optional | For attribution only. |
| `license` | Optional | Default: MIT. |

---

## Description formula

```
"Use when <trigger-situation-1>, <trigger-2>, or <symptom-the-user-would-type>.
Covers <concrete-things-taught: tools, commands, patterns, decisions>."
```

### Good examples

```yaml
description: "Use when diagnosing OTel Collector pipeline health — data loss, backpressure, queue saturation, export failures. Covers receiver/processor/exporter/process self-telemetry metrics with VictoriaMetrics query names."

description: "Use when creating a new SKILL.md, rewriting a description that doesn't trigger correctly, splitting an overgrown skill into references/, or deciding whether something belongs as a skill vs steering vs runbook."

description: "Use when troubleshooting .NET services via runtime metrics, interpreting GC/ThreadPool/JIT/HTTP telemetry, or building Grafana dashboards for .NET 6-10 workloads."
```

### Bad examples

```yaml
# ❌ Too short, no triggers
description: "OTel Collector metrics reference."

# ❌ Doesn't start with 'Use when'
description: "This skill helps engineers understand collector internals."

# ❌ Restates the name
description: "Use when you need the skill-authoring skill to author skills."
```

---

## When to create `references/`

Create `references/` only when content EARNS it:

| Move to `references/` | Keep inline |
|-----------------------|-------------|
| Lookup table >20 rows | Short tables |
| Full JSON schema | Brief schema snippet |
| Reusable template (like this file!) | One-liner examples |
| Per-variant docs (per-cloud, per-language) | Universal instructions |
| Script >30 lines | Quick commands |

**Never** scaffold an empty `references/` directory.

---

## Checklist before committing

```
[ ] name matches directory
[ ] description: 100-1024 chars, starts with "Use when..."
[ ] H1 title + intro present
[ ] ## When to use — includes symptom phrasing
[ ] ## When NOT to use — exists
[ ] ## Anti-patterns — exists
[ ] No org-specific data (use <placeholder>)
[ ] collision-check passed
[ ] validator passed
```
