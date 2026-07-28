---
name: spec-writing
description: "Write requirements, design and task specs."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [spec, writing, workflows]
    category: workflows
    related_skills: []
---
# Staff-Level Spec Writing

A meta-skill defining the **posture** and **mental process** for writing specs that genuinely capture the behavior of a system, tool, or feature.

> The `spec-driven-workflow` steering doc defines the FORMAT (requirements.md, design.md, tasks.md).
> This skill defines the HOW — the mindset, the questions, the relentless curiosity.

---

## When to Use

Use when writing, ideating, or reviewing specs (requirements, design, tasks) for any project. Activates staff-level engineering posture — deeply questioning, curious, example-driven — to produce specs that capture real behavior, not surface assumptions.

## Core Posture

When writing a spec you are NOT a passive documenter. You are a **staff-level engineer who must understand the system deeply enough to make irreversible architectural decisions about it**.

### Three axioms

1. **You haven't understood it until you can give concrete examples** — if you can't produce a real usage scenario (with data, flow, outcome), you don't understand it yet.
2. **The first description is always incomplete** — edge cases, error states, concurrency, and non-obvious interactions always exist and are almost never volunteered.
3. **Vague specifications produce divergent implementations** — "the system should be fast" is not a spec; "P99 latency < 200ms for queries returning up to 1000 results" is.

---

## Questioning Protocol

Before writing any section of the spec, work through these layers of questioning.

### Layer 1: Understand the real PURPOSE

| Question | Why it matters |
|----------|----------------|
| What concrete problem does this solve? | Avoids features that serve nobody |
| Who is the direct user/consumer? | Sets the vocabulary and level of abstraction |
| What happens if this does NOT exist? | Reveals whether it's actually needed |
| Does anything today do something similar? | Avoids reinvention; surfaces existing expectations |

### Layer 2: Understand the real BEHAVIOR

| Question | Why it matters |
|----------|----------------|
| Give me a concrete end-to-end usage example | Anchors the spec in reality |
| What happens when input is invalid/empty/huge? | Reveals edge cases |
| What happens under concurrency (2 simultaneous requests)? | Reveals race conditions |
| Which intermediate states exist? Can they fail? | Reveals transitions and recovery |
| How long can this take? Is there a timeout? | Defines implicit SLOs |
| What is explicitly OUT of scope? | Avoids scope creep and ambiguity |

### Layer 3: Understand DEPENDENCIES and INVARIANTS

| Question | Why it matters |
|----------|----------------|
| What does this depend on? What if that dependency goes down? | Resilience, fallbacks |
| Who depends on this? What if it changes? | Blast radius of breaking changes |
| Is there a business rule that can NEVER be violated? | Invariants the spec must preserve |
| Is data created/mutated? Is it reversible? | Understanding side effects |

### Layer 4: Understand PRODUCTION OPERATION

| Question | Why it matters |
|----------|----------------|
| How do I know it's working? (metrics, logs, traces) | Observability by design |
| How do I know it broke? (alert, symptom, who notices first) | Failure detection |
| How do I roll back if it goes wrong? | Safety net before deploying |
| What load is expected? How does it scale? | Sizing and cost |

---

## Elicitation Techniques

### 1. Example-First Writing

**BEFORE** writing requirements or design, create concrete examples:

```markdown
## Usage example: User creates a new integration

1. User navigates to /integrations/new
2. Selects type "webhook" from the dropdown
3. Fills in URL: https://my-service.com/hook
4. Clicks "Test connection"
5. System POSTs a test payload to the URL
6. 200 response → shows "✓ Connection successful"
7. 4xx/5xx response → shows error with status code + body (truncated at 500 chars)
8. Timeout > 5s → shows "Connection timed out after 5 seconds"
9. User clicks "Save" → integration created with status "active"
```

This example reveals: timeout policy, user feedback, error states, test payload, truncation limit — everything a vague spec ("support webhooks") would leave out.

### 2. Counter-examples (what must NOT happen)

```markdown
## Counter-examples

- Must NOT allow saving an integration without testing the URL first
- Must NOT block the UI while testing (async with spinner)
- Must NOT expose authentication headers in the test log
- Must NOT retry automatically when the test fails (user's decision)
```

### 3. State table (for systems with a lifecycle)

```markdown
## Integration states

| State | Transitions to | Trigger | Reversible? |
|--------|---------------|---------|-------------|
| `draft` | `active` | Successful test + Save | Yes (edit) |
| `active` | `paused` | User pauses | Yes (reactivate) |
| `active` | `failing` | 5 consecutive failures | Auto (retry with backoff) |
| `failing` | `active` | Successful delivery | Automatic |
| `failing` | `disabled` | 24h without success | Auto (notifies owner) |
| `disabled` | `active` | User forces reactivation | Yes (manual) |
| ANY | `deleted` | User deletes | NO (soft-delete, 30 days) |
```

### 4. Socratic-architectural questions

When someone describes something vague, respond with questions that force precision:

| User says | Staff engineer asks |
|-------------|--------------------------|
| "It needs to be fast" | "How fast? What latency is acceptable? For whom?" |
| "Support high load" | "How many requests/s today? Expected growth in 6 months?" |
| "It needs to be secure" | "Against what threat? Sensitive data involved? Compliance?" |
| "Integrate with service X" | "Synchronous API? Async event? What contract? Retry?" |
| "Notify the user" | "Through which channel? At exactly what moment? Can it be eventual?" |
| "Handle errors" | "Which errors specifically? Retry? DLQ? Alert? User-facing?" |

### 5. Temporal inversion

Imagine the system has been in production for 6 months:

> "It's 3am and the on-call engineer just got paged. What do they need to know about the component we're specifying?"

This reveals:
- What needs a runbook
- Which metrics/alerts are required
- Which failure modes exist
- What needs logging

---

## Depth Levels by Spec Type

| Type | Minimum depth |
|------|---------------------|
| New feature (greenfield) | Layers 1-4 complete + 3 or more concrete examples |
| Bugfix | Current (broken) behavior + expected + unchanged |
| Refactor | Invariants that MUST be preserved + regression risks |
| External service integration | Contract, retry, timeout, fallback, payload example |
| Migration | Before state → after state → rollback → blast radius |
| Config/infra change | Who it affects, blast radius, validation, rollback |

---

## Spec Quality Checklist

Before considering a spec "ready for implementation":

- [ ] **Has concrete examples** (not just abstract description)
- [ ] **Edge cases documented** (empty, huge, concurrent, failing)
- [ ] **Out of scope stated explicitly** (what is NOT included)
- [ ] **Verifiable acceptance criteria** (can be tested with an assert)
- [ ] **Dependencies identified** (and fallbacks when they fail)
- [ ] **Observability considered** (how to know it works/broke)
- [ ] **Rationale for non-obvious decisions** (why this way and not another)
- [ ] **Rollback path** (what to do if it goes wrong in production)
- [ ] **Load/performance estimated** (volume, acceptable latency)
- [ ] **A new dev would understand it without spoken context** (the "I went on vacation" test)

---

## Posture While Writing

### Be annoyingly curious

- Don't accept the first answer — ask for a second example
- Ask "what if..." for every happy path described
- Challenge premises: "why X and not Y?"
- Ask for numbers: "how much? how many? how often?"

### Be generous with examples

- Offer examples even when nobody asks
- Propose failure scenarios: "what if the network drops here?"
- Suggest edge cases: "what if the input is 100MB?"
- Show the counter-example: "that would mean Z is also true — correct?"

### Be honest about uncertainty

- Explicitly mark what is an assumption vs a confirmed fact
- Use `[ASSUMPTION]` or `[TO CONFIRM]` inline
- Don't invent behavior — ask

### Be empathetic toward the future reader

- The spec will be read by someone without the context of this conversation
- Every decision needs a "why" (even if it's one sentence)
- Examples > abstractions
- Sequence diagrams > descriptive paragraphs

---

## Recommended Flow

```
1. Understand purpose (Layer 1) — "What does this solve?"
2. Collect concrete examples — "Show me 3 real scenarios"
3. Map edge cases — "What if...? And when...?"
4. Identify invariants — "What can NEVER break?"
5. Define observability — "How do I know it works?"
6. Write the spec (requirements → design → tasks)
7. Revisit with examples — "Does this example validate the requirements?"
8. Final challenge — "If I implemented this blind, what stayed ambiguous?"
```

---

## Spec Writing Anti-patterns

| Anti-pattern | Consequence | Correction |
|-------------|--------------|----------|
| Spec without concrete examples | Implementation diverges from intent | Example-first writing |
| "The system must support X" without quantifying | Every reader assumes a different number | Ask: "how much? with what SLA?" |
| Copying class/function names into the spec | Spec documents the code, not the intent | Describe behavior, not implementation |
| Spec covering only the happy path | Edge cases discovered during implementation (delays) | Ask about failures at every step |
| Spec written in 10 minutes for a complex feature | False sense of planning | Invest time proportional to complexity |
| Spec that is never re-read or updated | Lies about the real system | Update after any justified deviation |
| Design without Rationale | Nobody understands "why this way" in 6 months | Use the Rationale format from steering |
| Accepting "it's simple, no spec needed" | A "simple" feature that becomes a week of work | Everything gets a spec; depth varies |

---

## Calibrating Depth

Not every spec needs 20 pages. Depth scales with risk:

| Risk | Indicators | Spec depth |
|-------|-------------|---------------------|
| Low | Config change, isolated refactor, 1 file | Light requirements (3-5 criteria) + tasks |
| Medium | New feature within a known domain | Full requirements + design + tasks |
| High | New service, breaking change, cross-domain | Complete spec + round-table + extensive examples |
| Critical | Data migration, security, production infra | Spec + review + dry-run plan + rollback doc |

**Heuristic**: if reverting costs more than a day, the spec needs a Rationale and a rollback plan.

---

## Domain Modeling — Before Coding

Before writing code, discover the domain's **entities**, **relationships**, and **invariants**. Specs that skip this step produce implementations that model reality incorrectly.

### Discovery process

```
1. Identify domain NOUNS → entity candidates
2. Identify VERBS → operation/transition candidates
3. Identify rules that "can never be violated" → invariants
4. Map who knows whom → relationships and dependency direction
5. Ask: "does this concept exist without the other?" → aggregates
```

### Questions that reveal the model

| Question | Reveals |
|----------|--------|
| "What are the THINGS that exist in this system?" | Entities |
| "What states can each thing have?" | Lifecycle / state machine |
| "What CAUSES a thing to change state?" | Events / triggers |
| "Can two things exist without each other?" | Composition vs association |
| "What can NEVER happen?" | Invariants |
| "Who OWNS this decision?" | Aggregate root / bounded context |
| "If I delete X, what dies with it?" | Cascade / ownership |

### Documentation format in design.md

```markdown
## Domain Model

### Entities

| Entity | Responsibility | Lifecycle |
|----------|-----------------|-----------|
| Integration | Connection to an external system | draft→active→paused→disabled→deleted |
| Delivery | Attempt to send a payload | pending→delivered / failed |
| Event | Occurrence that triggers a delivery | immutable after creation |

### Relationships

```
Integration 1──* Delivery (owns, cascade delete)
Event 1──* Delivery (triggers, non-cascading reference)
```

### Invariants

- An Integration can only be `active` if the last connection test succeeded
- Deliveries cannot be created for Integrations in the `disabled` state
- An Event is never mutated after creation (append-only)
- Maximum 1000 pending Deliveries per Integration (backpressure)
```

### Signs the model is wrong

- Entity with 15+ fields → probably 2-3 entities mixed together
- A "flag" that changes the behavior of the whole entity → probably distinct types
- A business rule requiring 4 entities to evaluate → wrong boundary
- An entity that is created but never changes → may be a Value Object
- The same entity edited by 3 different flows → missing aggregate boundary

---

## Cross-reference

- **Spec format** → `steering/spec-driven-workflow.md` (requirements.md, design.md, tasks.md)
- **Rationale format** → `steering/spec-driven-workflow.md` § "Rationale (decisions and trade-offs)"
- **When to create specs** → `steering/spec-driven-workflow.md` § "When to create specs"
- **Documentation** → `steering/documentation-sync.md` (update after implementation)
