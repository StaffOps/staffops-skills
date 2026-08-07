---
name: agent-skills-adversarial-review
description: "Refute a document with independent reviewers before commit."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [review, specs, validation, harness, quality]
    category: aws
    related_skills: [agent-skills-metric-verification, agent-instruction-authoring, agent-skills-specs-authoring]
---
# Adversarial Review of Documents

Code has tests. A document has nothing — which is why a wrong fact in a skill or an unfalsifiable milestone in a product requirements document ships unnoticed. This skill is the substitute: independent reviewers instructed to break the document rather than bless it.

It covers reviewing prose artefacts. Reviewing code belongs to a code-review workflow with a test suite behind it.

## When to Use

- A spec, requirements document, architecture decision record or design document is about to be committed
- A new agent instruction file or a batch of skills has been written
- Any artefact that will be read at runtime and turned into a production conclusion
- After a delegated subagent produced content nobody has verified

Skip it for typos, formatting, and documents nobody will act on.

## "Looks good" is a failed review

A reviewer who returns approval has not reviewed. The instruction must make refutation the job, explicitly:

> Your job is to REFUTE, not to approve. Find what is wrong, contradictory, unsupported or unfalsifiable. A "looks good" response is a failed review. If you find fewer than 5 real defects across ~3000 lines you have not looked hard enough.

The last sentence matters. Without a floor, a reviewer optimises for agreement. With one, it keeps digging.

## Choose validators by attack surface, not by topic

One reviewer per angle, in parallel. Same document, different question.

| Validator | Assigned question |
|-----------|------------------|
| Rigour reviewer | Is it internally consistent, falsifiable, non-circular? Are exit criteria activities dressed as metrics? |
| Fact checker | Are the technical facts true? **Verify each against the live system, not against the document** |
| Security reviewer | What does it get wrong about security, and what risk does it create or fail to name? |
| Cost reviewer | Does the arithmetic survive? What cost is unmodelled? |
| Consistency reviewer | Dead links, count drift, contradictions between files, orphaned documents |

Cross-domain artefacts get all five. A single-domain document gets two: the domain specialist and the rigour reviewer.

## Write the brief so refutation is possible

A vague brief produces a vague review. Each validator needs:

1. **The file list** — absolute paths, and an instruction to read all of them before answering
2. **Specific attack targets**, numbered. Not "review the cost section" but "the suite is stated at $0.25 per query; at $0.0083 per agent-second that implies 30 seconds; observed durations were 108 to 300 seconds; recompute"
3. **Permission to use tools** — the fact checker must query the live system, the security reviewer must run read-only calls
4. **A required output shape**

### The output shape that works

```
For each defect: file / quote the offending text / why it is wrong /
propose the exact replacement text / severity (BLOCKING|HIGH|MEDIUM|LOW)
```

Demanding the replacement text is what turns a complaint into a fix. A reviewer who must write the correction thinks harder about whether the original is really wrong.

## Triage before applying

Not every finding is right. Two harness assertions in a real run were themselves defective — one counted latent tool wrappers against a tool budget, one matched an English keyword against a correct non-English answer.

Order of questioning:

1. **Is the finding itself correct?** Verify independently. A reviewer can be wrong with confidence.
2. **Is it blocking?** Security and factual errors outrank stylistic ones.
3. **Does the fix introduce a new claim?** If so, that claim needs verification too — this is how audits introduce regressions while appearing to fix them.

## Record the correction as a correction

When a document is fixed, say what was wrong and why, in the document. Silent correction destroys the reader's ability to calibrate trust:

```markdown
> **Corrected 2026-08-07 by independent re-verification.** Two families listed in
> the original version of this finding do not exist. This correction is itself an
> instance of the defect class this document exists to catch.
```

That last sentence is worth writing when it is true. It tells the next reader the discipline is real rather than aspirational.

## What this process caught

Run once over 22 spec files, roughly 3000 lines. Selected findings, to calibrate what to expect:

| Severity | Finding | How the reviewer knew |
|----------|---------|----------------------|
| Security | An inline policy documented as "inert (blocked by session policy), removable for hygiene" was a live grant of secret-read permission on production tokens. The session policy bounded only the sandbox; the role is assumed by the service for **all** operations | Read the role's trust policy and last-used timestamp — 13 minutes prior. Reasoned that one blocked path is not all paths |
| Facts | Two metric families asserted as live returned empty | Queried the live backend instead of trusting the document |
| Cost | A stated per-query cost implied 30 agent-seconds; nothing had ever completed in under 108 | Divided the stated cost by the stated rate and compared to the only real measurement |
| Rigour | A milestone exit criterion read "publish a baseline" — satisfiable by publishing 40% correctness and declaring victory | Asked what value of the metric would fail the criterion. None would |
| Rigour | Verification required two agreeing signals, but for several problem classes the only second signal was human feedback — which *is* the verdict, so it cannot triangulate with itself | Enumerated the available signals per class instead of accepting the general claim |
| Consistency | A document said a directory was "not versioned" and 160 lines later "versioned here, on purpose" | Read the whole file rather than the section under review |

**The pattern**: every finding came from checking a primary source or asking "what observation would falsify this?" None came from reading more carefully.

## Anti-patterns

- Asking a reviewer to "validate" or "check" — those words invite approval
- One reviewer for a cross-domain document; each angle needs its own context window and its own question
- Accepting a finding without verifying it independently
- Applying a fix that asserts a new unverified fact
- Correcting a document silently
- Reviewing your own work as the only gate — the author cannot see their own blind spot, which is the entire premise
