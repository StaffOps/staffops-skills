# Hypothesis Log -- <issue or ticket id>

Append one entry per hypothesis. Never edit or delete a past entry -- a
corrected understanding gets a NEW entry, not a rewrite of an old one. This
file is the audit trail behind the "3 failed fixes means architecture, not
another hypothesis" rule in `SKILL.md` Phase 3/4 -- the count is grepped, not
recalled from memory.

Copy this file into your scratch space (or attach it to the ticket) before
writing the first hypothesis. Keep it next to whatever evidence you pulled
from `tempo-traceql-patterns` / `loki-logql-patterns` (trace IDs, LogQL
queries, screenshots of a metric) so the log and the evidence stay together.

---

## Hypothesis 1 -- <YYYY-MM-DD HH:MM>

**Statement**: I think <X> is the root cause because <evidence Y>.
**Test**: <smallest possible change or query that would confirm/refute it>
**Outcome**: CONFIRMED | REFUTED | INCONCLUSIVE
**Evidence**: <trace ID, LogQL query + result, metric query + value, test output>

---

## Hypothesis 2 -- <YYYY-MM-DD HH:MM>

**Statement**:
**Test**:
**Outcome**:
**Evidence**:

---

## Hypothesis 3 -- <YYYY-MM-DD HH:MM>

**Statement**:
**Test**:
**Outcome**:
**Evidence**:

---

## Before writing Hypothesis 4

Count refuted hypotheses mechanically -- do not estimate it:

```bash
grep -c '^\*\*Outcome\*\*: REFUTED' hypothesis-log.md
```

If this returns `3`, there is no "Hypothesis 4" entry in this format. Instead
write an **Architecture Question** entry:

```markdown
## Architecture Question -- <YYYY-MM-DD HH:MM>

**Pattern observed**: each of the 3 refuted hypotheses above pointed at a
different component (<A>, <B>, <C>) and each fix attempt required touching
code the previous fix did not.
**Raised with**: <tech lead / ticket reporter / reviewing engineer>
**Question**: is <the underlying pattern> fundamentally sound, or does this
need a design change rather than a 4th patch?
```

This is not a failure to find the bug. It is the process correctly
identifying that the bug is one layer up from where the last three fixes
were aimed.
