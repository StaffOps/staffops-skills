---
name: skill-authoring
description: "Structure and validate a new catalog skill before it ships."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [skill, authoring, description, structure, catalog, workflows]
    category: workflows
    related_skills: [skill-eval-harness, markdown-docs]
---
# Skill Authoring

The mechanical companion to `CONTRIBUTING.md`: how to structure a new skill's
files, how to write a description that actually triggers, when a piece of
prose has earned its way into `scripts/` or `references/`, and the checklist
to clear before a skill is ready for review. It deliberately stops at "is
this skill well-formed and does it plausibly trigger correctly" — it does
not cover running paired evals or measuring whether a behavior change helped;
that is `skill-eval-harness`'s job, and this skill exists so that harness has
something well-structured to test in the first place.

## When to Use

Use when drafting a brand-new `SKILL.md`, splitting an overgrown skill into
`references/`, deciding whether a workaround belongs in prose or in a bundled
script, or second-guessing a description that might not trigger the way you
expect. Also use as a pre-flight pass right before handing a new or edited
skill to `skill-eval-harness` — this skill's checklist is what that harness
assumes you already did.

Do not use this for typo fixes with no structural or triggering impact —
just run `tools/validate_skills.py` per `CONTRIBUTING.md` and move on.

## Relationship to skill-eval-harness

These two skills split one job in half. This one answers "is the skill
built correctly and worded to trigger on the right prompts" — a structural
and descriptive-quality question you can answer by reading the file and
running two fast, free checks. `skill-eval-harness` answers "did this
specific edit measurably help or hurt" — a behavioral question that requires
actually running the skill against cases, which costs tokens and money and
needs its budget-capped, paired-run machinery. Do not re-derive that
machinery here; every workflow below that touches evaluation points at that
skill instead of re-describing it.

## Step 1 (mandatory, not an afterthought): run the real validator

Before writing a word of body content, know what `tools/validate_skills.py`
checks, because it constrains every choice you make below:

- Directory layout is `skills/<category>/<name>/SKILL.md`.
- `name` matches `^[a-z][a-z0-9_-]*$` and equals the directory name.
- Required frontmatter keys are present: `name`, `description`, `version`,
  `author`, `license`, `platforms`.
- `description` is 60 characters or fewer and ends with a period (the
  validator checks length and the trailing period mechanically; "reads as
  one sentence" is a style expectation the validator does not itself parse
  for, so a human read-through still matters here).
- `metadata.hermes.category` matches the parent directory name.
- Every `metadata.hermes.related_skills` entry resolves to a real skill
  directory elsewhere in the catalog.
- The body contains no accented Latin characters (English-only, per
  `CONTRIBUTING.md`).

```bash
python3 tools/validate_skills.py
```

Run it after your first draft of the frontmatter, not just once at the end —
fixing a name mismatch or a category typo before you write 150 lines of body
around it is cheaper than fixing it after. Run it again as your last step,
because it is the one check in this workflow that is both mandatory and
free.

## Structuring a new skill

This catalog's progressive-disclosure model has three tiers, the same shape
the rest of the industry converged on independently, but the specific layout
below is this repo's own (see `README.md`'s "Skill Format" and "Layout"
sections and `CONTRIBUTING.md`):

1. **Frontmatter** — `name` + `description`, held in context for every skill
   at all times. This is the only tier with a hard character budget in this
   catalog (60 characters), so it has to carry the least information: what
   the skill covers, nothing more.
2. **SKILL.md body** — loaded in full once the skill triggers. This repo's
   convention trends toward roughly 200 navigable lines rather than the
   500-line ceiling some skill formats allow; several apm-metrics skills
   in `skills/apm-metrics/` are useful models for "substantive but scannable."
3. **Bundled resources** — `references/`, `scripts/`, `examples/`, loaded or
   executed only when the body points to them. Per `README.md`, only
   `SKILL.md` is required; the other three "are added when they earn their
   place, not as a template to fill in for every skill."

```
skills/<category>/<name>/
├── SKILL.md          required — keep it navigable
├── references/        long-form tables, per-variant docs, specs
├── scripts/            runnable helpers (shellcheck-clean where present)
└── examples/           worked input/output pairs
```

Use `references/` for tables and specs long enough to dilute the body if
inlined — a metric-name reference table, a per-cloud-provider variant, a
full JSON schema. Point to it from the body with a one-line pointer that
says when to open it, so the model doesn't load it speculatively.

### The three-instance rule for promoting to `scripts/`

If you notice the same helper command, parser, or multi-step workaround
would need to be reconstructed identically by three independent uses of the
skill, write it once and put it in `scripts/` instead of leaving it as prose
the model re-derives every time. This catalog already has a working example
of this discipline: `skills/shell/` and, in `skills/linux/`,
`linux-command-line`, `linux-filesystem`, `linux-process-management`, and
`systemd-services` ship shellcheck/shfmt-clean `scripts/` and `examples/`
that were executed against a real Ubuntu 24.04 container during authoring,
per `README.md`'s "Depth varies by skill" section — that section names
exactly these skills, so check it directly rather than assuming a sibling
skill in the same directory (like `ubuntu-administration`, which has no
`examples/` at all) automatically belongs to the same tier. That
depth is valuable but expensive — it is an option to grow into for a skill
that is proving itself, not a bar every new skill must clear on day one.
The signal to promote is repetition, not ambition: prose that would have to
say the same eight-command sequence three different ways for three different
scenarios is prose that should be one script instead.

## Writing a description that actually triggers

The core idea — write descriptions that state both what the skill does and
concrete trigger contexts, anticipating phrasing a user would not naturally
use themselves — holds regardless of format. What changes in this catalog is
the budget: the frontmatter `description` is capped at 60 characters, far
tighter than formats that allow a paragraph there. That budget rules out
cramming trigger scenarios into the description itself. The adaptation:
keep `description` terse and factual (state the capability, skip trigger
language), and do the anticipatory work in `## When to Use` instead, which
has no length ceiling and is what actually surfaces once the skill is
triggered and read in full.

**Before** (name-anchored — only matches someone who already knows the
skill's own vocabulary):

```yaml
description: "Configure gRPC health checks for Kubernetes."
```
```markdown
## When to Use
Use when setting up gRPC health checks.
```

**After** (description stays within budget; the anticipatory phrasing —
including the symptom-shaped sentence a user would actually type, which
never mentions "gRPC" or "health check" — moves to the unbounded section):

```yaml
description: "Diagnose gRPC probe failures behind Kubernetes restarts."
```
```markdown
## When to Use
Use when a gRPC-only service fails its liveness or readiness probe, when
`grpc_health_probe` returns `UNIMPLEMENTED` or times out, or when the
symptom is reported as something like "the pod keeps restarting but the
app looks fine in the logs" for a service that never speaks HTTP.
```

Tags (`metadata.hermes.tags`) get the same treatment on a smaller scale:
they are search tokens, not a restatement of the name. A tag list that just
repeats the words already in `name` adds nothing a search index didn't
already have.

### Explain why, don't just shout

This applies to every skill's instructions, not only new ones. A body full
of `MUST`/`NEVER` in capitals with no stated reason is a yellow flag that the
author reached for a rule before understanding why it holds — and a rule
without a reason cannot generalize past the exact case the author had in
mind. A model with reasonable theory of mind extrapolates well from an
explained constraint ("do X because Y breaks under Z") and poorly from a
shouted one. Compare:

```markdown
NEVER read secret values into the conversation.
```
```markdown
Do not read secret values into the conversation — anything echoed back
becomes part of the transcript and can leak into logs, screen shares, or a
future context window that shouldn't have it. Read the key name and
confirm existence; if the caller explicitly needs the value, ask first.
```

Both forbid the same action. Only the second tells the model what actually
breaks, so it can reason correctly about a case the sentence didn't
explicitly cover.

## Collision check before you ship

Every metrics skill starts to look plausible for every metrics question once
a catalog passes a few dozen entries; this one has 170+, with dozens of
`*-metrics` skills alone. `CONTRIBUTING.md` and the original inspiration for
this catalog's format were written for a much smaller catalog and neither
says anything about this problem — it only becomes real at this scale. Run
the collision scan from `skill-eval-harness` against the description and
tags of any new or materially reworded skill before finalizing it:

```bash
python3 skills/workflows/skill-eval-harness/scripts/eval_harness.py \
  collision-check --skill skills/workflows/skill-authoring/SKILL.md
```

It strips catalog-wide boilerplate phrasing (words like "diagnose" or "use
when" that appear in most descriptions and therefore carry no signal),
computes Jaccard overlap of what is left against every other skill's
description and tags, and flags anything at or above the default 0.5
threshold. A hit does not automatically mean rename something — it means
decide: either narrow the wording so the two skills stop competing for the
same prompt, or confirm they are meant to compete and pick which one should
win by making the other's description more specific to what it uniquely
covers.

## Pre-flight checklist

Work through this before treating a new or edited skill as done. It is the
gate this skill exists to enforce, and it is what `skill-eval-harness`
assumes already passed before you get to its heavier machinery.

- [ ] Path is `skills/<category>/<name>/SKILL.md`; `name` matches the
      directory and `^[a-z][a-z0-9_-]*$`.
- [ ] `version`, `author`, `license: MIT`,
      `platforms: [linux, macos, windows]` all present.
- [ ] `description` is one sentence, 60 characters or fewer, ends with a
      period, and does not restate the skill name.
- [ ] `metadata.hermes.category` matches the parent directory.
- [ ] `metadata.hermes.tags` are real search tokens, not a copy of `name`.
- [ ] Every `metadata.hermes.related_skills` entry was opened and confirmed
      to exist — not guessed at.
- [ ] Body opens with an H1 title and a 2-3 sentence intro stating what the
      skill covers and what it deliberately does not.
- [ ] `## When to Use` states concrete trigger conditions, including at
      least one symptom-shaped phrasing that does not use the skill's own
      vocabulary.
- [ ] `## Anti-patterns` exists at the end of the body.
- [ ] No accented Latin characters anywhere in the body.
- [ ] No org-specific hostnames, account IDs, ARNs, or paths — placeholder
      vocabulary from `CONTRIBUTING.md` only.
- [ ] Any repeated, reconstructible workaround is in `scripts/`, not typed
      out in prose three different ways.
- [ ] `python3 tools/validate_skills.py` passes with zero errors.
- [ ] `skill-eval-harness`'s `collision-check` ran against this skill with
      no unresolved overlap at or above threshold.
- [ ] The category's `DESCRIPTION.md` lists the new skill, and `README.md`'s
      catalog table/badge reflects it too — run `python3
      tools/generate_catalog.py` from the repo root rather than hand-editing
      either file. It regenerates both from every `SKILL.md`'s frontmatter
      in one pass, which is the only way to guarantee they don't drift out
      of sync with each other (hand-edits from concurrent skill additions
      are exactly how that drift happens in practice).

## Choosing a validation depth

Everything above is free — reading, a linter, a tokenizer-based overlap
check. Whether to go further and actually run the skill against cases is a
cost/certainty tradeoff, and the default should be the cheap side of it.

**Lightweight default** (covers the large majority of changes):

1. The pre-flight checklist above.
2. `tools/validate_skills.py` passing.
3. `skill-eval-harness collision-check` passing.
4. A manual read-through against 2-3 realistic prompts — write out the
   sentences a real user would type, including one adjacent-domain prompt
   that should *not* trigger this skill, and check by reading whether the
   description and `## When to Use` would route each one correctly. No
   subagents, no tokens spent, no budget flag required.

**Escalate to `skill-eval-harness`'s full plan/run/grade/score pipeline**
when any of these hold, because a read-through can't settle them:

- Two skills plausibly compete for the same prompt and it genuinely is not
  obvious which should win in practice, not just on paper.
- The skill sits behind a lot of existing routing (a core catalog skill,
  one several others' `related_skills` point at) where a regression has
  wide blast radius.
- The edit restructures instructions or bundles a new script such that you
  cannot tell by reading alone whether behavior improved or just changed.

That escalation is optional rigor, not the default path — most single-skill
edits in a one-maintainer catalog do not need a budget-capped multi-trial
run to be shipped responsibly, and treating maximum rigor as mandatory for
every change would make the harness a chore people route around rather than
a check people actually run. Reach for it deliberately, for the changes
where being wrong is expensive; see `skill-eval-harness`'s own `SKILL.md`
for the full workflow once you decide it's warranted.

## Anti-patterns

- **Copying a sibling skill's description and tweaking one word.** This is
  exactly how the `*-metrics` family collides — verify with
  `collision-check` instead of assuming a small edit stayed distinct.
- **A wall of `MUST`/`NEVER` with no stated reason.** It signals the author
  didn't work out the reasoning, and it generalizes worse than an explained
  constraint — see "Explain why, don't just shout" above.
- **Restating the skill name inside the description**, or filling the
  60-character budget with marketing words instead of the capability.
- **Writing trigger language only in the author's own vocabulary.** If every
  test prompt you'd write sounds like something you would say, you haven't
  covered the phrasing a different engineer under a different vocabulary
  would actually use.
- **Adding empty `references/`, `scripts/`, `examples/` folders as a
  template "to fill in later."** Per `README.md`, these are added when they
  earn their place; an empty scaffold is worse than no scaffold.
- **Skipping `tools/validate_skills.py` "because it's just wording."**
  Wording changes are exactly what breaks the 60-character limit and the
  period-ending rule most often.
- **Skipping `collision-check` because the overlap "obviously" isn't
  there.** The whole reason this check exists is that overlap in a
  170+-skill catalog is rarely obvious by inspection.
- **Always running the full grader/comparator/analyst pipeline, even for a
  one-line rewording.** That is `skill-eval-harness`'s heaviest machinery
  spent on a change a read-through would have settled for free — match the
  validation depth to the actual risk of the edit.
- **Editing a shared file like a category's `DESCRIPTION.md` from a stale
  read.** Re-read it immediately before your edit; another concurrent
  change may have already landed.

## When NOT to use

- **Writing steering rules** — steering is always-active; skills are on-demand. Different format.
- **Documenting a one-off procedure** — use a runbook or HOW-TO, not a skill.
- **Platform-specific agent config** (MCP, agent JSON) — that's agent setup, not skill content.

## Related skills

- [how-this-agent-works](../workflows/how-this-agent-works/SKILL.md) — understanding where skills fit.
- [skill-eval-harness](../workflows/skill-eval-harness/SKILL.md) — testing newly authored skills.
- [skill-share](../workflows/skill-share/SKILL.md) — distributing skills across agents.
- [markdown-docs](../documentation/markdown-docs/SKILL.md) — writing well-structured markdown.
