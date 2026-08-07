---
name: agent-instruction-authoring
description: Use when writing or editing an agents_md or a SKILL.md for the AWS DevOps Agent. Carries the rule that an instruction must prescribe substance rather than labels, because the platform overrides the output format on deep investigations; the official SKILL.md procedure structure; what is observable about an instruction and what is not; and the two ways a well-written instruction still fails to land.
---

# Authoring an instruction that actually lands

Writing the instruction is the easy half. The hard half is that an instruction can be well-written, correctly imported, demonstrably loaded, and **still have no effect** — and the failure is silent. This skill carries the ways that happens.

## Prescribe substance, not labels

The platform imposes its own structure on some results. A deep `INVESTIGATION` returns structured `symptom` and `finding` records with time windows and `Cause:` prefixes; a chat returns prose. **Where the platform has a schema, the schema wins.**

So an instruction that says *"end with these seven numbered sections"* is asking for something unachievable on the path where it matters most. Worse, it invites asserting on section names — which produces test failures that are not defects. That misdiagnosis consumed three attempts on this project.

Write the requirement as a **fact that must be present**, and say explicitly that a platform-imposed shape is acceptable:

| Instead of a label | Prescribe the fact |
|---|---|
| `## Output` → `Status — healthy / degraded / critical` | *whether the system is healthy, degraded, or critical* |
| `Timeline — timestamped, cause before effect` | *when it happened, timestamped, with cause preceding effect — **a single timestamp is not a timeline*** |
| `Contradicting evidence` | *anything that does not fit, and how it is explained. "Nothing contradicts this" is valid; **saying nothing at all is not*** |

The parenthetical clauses matter more than the nouns. `a single timestamp is not a timeline` closes a specific way of technically complying while producing nothing useful. Prefer prescribing the **failure you are ruling out** over naming the artifact you want.

State the governing rule once, in `GENERIC`, since it applies on every path: *a required fact is required in any shape; a fact dropped because no section was named for it is a dropped fact, not a formatting detail.*

## SKILL.md holds procedure, not reference

Per AWS's own guidance, `SKILL.md` carries **step-by-step procedure, decision trees and expected outputs**. Lookup tables belong in `references/`. A catalog built the other way round — tables in `SKILL.md` — reads well and instructs poorly, because the agent gets facts where it needed a next action. Restructuring 47 skills to fix that was the single largest change in this project's history.

The working shape: *When to use / When NOT to use / numbered Steps / a step that says `Summarize findings` / Decision tree / Related skills*.

## What is observable, and what is not

| Question | How to answer it |
|---|---|
| Did any `agents_md` load? | The `utilization` record: `{"agents_md": {"utilization": 2.4}}` |
| Which skills loaded? | The same record names the bundles. Do not grep the transcript |
| **Which `agents_md` loaded?** | **Not observable.** Their content is never echoed into the journal, and `utilization` is aggregate |
| Did the instruction change behaviour? | Only by observing behaviour — tools invoked, skills loaded, facts present |

Because the third row is not observable, a question like *do these three files complement or compete?* cannot be answered by reading a transcript. The only route is a distinctive sentinel per file, checked for in the output.

## Two ways a good instruction still fails

**Measured on the wrong entry point.** A rule that governs typed executions will look inert if you test it in `create_chat`, which only opens CHAT/GENERIC. Confirm which entry point the rule applies to *before* concluding it does not work, and before moving it somewhere else to compensate.

**Tested against a scenario that cannot discriminate.** An investigation that finds everything healthy cannot exercise a contract asking for a timeline, a hypothesis, a remediation and a prevention — with nothing wrong, those items legitimately do not apply, and their absence proves nothing. A narrow scope is cheap and safe, but choose one where the requirement would have to appear.

## Before declaring an instruction done

- Substance, not labels, and each requirement names the failure it rules out
- The read-only invariant restated in the file, not delegated by reference alone
- No approval language anywhere — including the `description` field, where three instances survived a sweep that only checked the body
- Re-synced, and the **7 read-only probes re-run**: any `agents_md` change re-runs them
