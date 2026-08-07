---
name: agent-skills-specs-authoring
description: "Where planning artefacts go, and what makes one valid."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [specs, adr, prd, planning, documentation]
    category: aws
    related_skills: [agent-skills-adversarial-review, agent-instruction-authoring, spec-writing, adr-template]
---
# Authoring Specs, Architecture Decision Records and Product Requirements

A planning layer is only useful if each artefact has one owner and every claim in it is checkable. This covers placement, format, and the bar a document has to clear.

It does not cover writing agent instructions or skills — that is a different artefact with different failure modes.

## When to Use

- Adding a feature spec, a decision record, or amending a requirements document
- Deciding whether something belongs in a spec, a backlog, a changelog or a skill
- Reviewing a spec someone else wrote

## Layout

```
specs/
├── README.md              # Reading order. Every document reachable from here
├── CAPABILITY-MATRIX.md   # The boundary: what we control, what is impossible, cost envelope
├── PRD.md                 # Thesis, milestones, success metrics, risks, open questions
├── MARKET-ANALYSIS.md     # Where we sit; which techniques we borrow
├── VALIDATION-PLAN.md     # How each milestone is proven in the real environment
├── decisions/             # Decision records, sequentially numbered
└── <feature>/             # requirements.md, design.md, tasks.md
```

Specs live at the repository root, not inside a tool-specific directory — tool-agnostic and versioned. A single canonical agent guide sits at the root; tool-specific files are one-line pointers to it.

## A capability boundary constrains everything

Before proposing work, check what the platform actually permits. When you consume a managed agent rather than author it, a spec proposing to change how it reasons, or to read secrets from a sandboxed context, or to ship executable files where the API rejects them, cannot land. Those are product boundaries, and they belong in one document with the evidence attached.

If a spec needs something the boundary document says is impossible, either the spec is wrong or the boundary is out of date. Resolve that before writing further.

## Which document owns what

| Content | Goes in | Not in |
|---------|---------|--------|
| Strategic why, what, boundary | A spec | The backlog |
| A decision with legitimate alternatives | A numbered decision record | A comment inside a spec |
| Detailed execution plan for a milestone | The feature's tasks file | The backlog |
| The immediate work queue | The backlog, one line per item pointing at the spec | Duplicated detail |
| What shipped, past tense | The changelog | Anywhere pending work lives |
| Tactical how-to, API quirks, exact commands | A skill | A spec |

The boundary that keeps these from drifting: **a skill changes when the API changes; a spec changes when the strategy changes.** Someone sitting down to do a task reads the skill. Someone deciding what to do next reads the spec.

## The requirements, design and tasks triplet

### requirements.md — what, in falsifiable form

Use a conditional form that names the observable:

```markdown
WHEN a skill asserts a metric name
THEN it SHALL exist in the live backend, or carry an explicit annotation that it does not
```

Then acceptance criteria as a checklist, and an explicit out-of-scope section. A requirement nobody can fail is not a requirement.

### design.md — how, and why

This is where most design documents fall short. Four levels exist:

| Level | Content | Reality |
|-------|---------|---------|
| 1 | Some documentation exists | — |
| 2 | Describes **what** exists: components, flows, configuration | most documents stop here |
| 3 | Describes **why** each decision was taken | required when a decision has alternatives |
| 4 | Describes **when to reverse** it | required for any deliberate simplification |

A design document that lists components and data flows without explaining why those components is Level 2, and becomes fiction the moment someone reads it without the context of the day it was written.

For each significant decision:

```markdown
### Decision N: <the choice, in a phrase>

**Choice**: <one sentence>

**Justification, strongest first**:
1. <the reason that would hurt most to reverse>

**Trade-offs accepted**:
| Cost | Why acceptable |

**When this decision would be wrong**:
- <a concrete signal that would justify reopening it>

**Reversal action**: <what to do when that signal fires>

**Alternatives rejected**: <alternative> — because <reason>
```

The **reversal action** is what makes it Level 4. "This would be wrong if X" without saying what to do about X is a Level 3 document wearing a Level 4 heading.

### tasks.md — the execution plan

Discrete, traceable, with explicit dependencies. Plus a status table mapping every task to its real state, and a promotion trigger wherever something is deliberately deferred:

```markdown
| Task | State | Promotion trigger |
|------|-------|------------------|
| T3 Seed memories | Deferred | Unblocks when T4 confirms the API works programmatically |
```

An implementation that was deliberately simplified must say so here. Silent simplification is how a spec becomes a lie.

## Decision records

### When a decision earns one

Any of these is sufficient:

- The choice has legitimate alternatives
- Reversing it would cost more than a day
- It creates recurring cost — operational, financial or latency
- It blocks or enables future decisions
- It trades away a standing rule for another gain

Trivial choices do not get one. Documenting everything dilutes the ones that matter.

**Heuristic**: if a new engineer would look at this and think *"why like that?"*, it needs one.

### Format

```markdown
# ADR-NNN: <title in the imperative>

**Status**: Accepted | **Date**: YYYY-MM-DD | **Deciders**: <who>

## Context
<the situation that forced a decision, with concrete evidence — quote the
 error message, cite the measurement, name the run identifier>

## Decision
<one or two sentences>

## Rationale
<ordered by strength, strongest first>

## Consequences
### Positive
### Negative
### Neutral

## When this decision would be wrong
<concrete signals>

## Alternatives considered
| Alternative | Why rejected |

## References
```

Then index it, and link it from the requirements document if it constrains scope.

### Evidence, not recollection

A decision record's context should be checkable. "The API rejected it" is weak; the actual validation error text is strong. Run identifiers, measured values and quoted errors are what let a future reader verify rather than trust.

## No invented numbers

`unmeasured` is an acceptable value and often the honest one. A metrics table with plausible-looking figures nobody measured is worse than one that admits the gap — it removes the motivation to go and measure.

Where a figure comes from a single observation, say so. Where it is a range because the metering basis is unknown, give the range.

## Before committing

- Reachable from the spec index
- Nothing proposed that the capability boundary rules out
- Every exit criterion has a value that would fail it
- Every design decision reaches Level 3, and Level 4 where something was deferred
- Counts and costs agree with every other document that states them
- Relative links resolve
- Run adversarial review

The last item is not optional for a document that will shape months of work. The first pass over one real spec set found a live security issue, two nonexistent metric families and a cost figure wrong by three to four times.

## Anti-patterns

- A design document that documents mechanics but not decisions
- An exit criterion that is an activity rather than a threshold
- Duplicating task detail between the backlog and the spec, so both drift
- Inventing plausible figures instead of writing `unmeasured`
- A decision record whose context cannot be verified by a later reader
- Committing a spec set without independent review
