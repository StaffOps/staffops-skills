---
name: linux-troubleshooting-methodology
description: "Apply a systematic approach to diagnosing Linux issues."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [troubleshooting, methodology, use-method, rca, systematic-diagnosis]
    category: troubleshooting
    related_skills: [linux-performance-analysis, log-analysis, incident-triage-linux]
---
# Linux Troubleshooting Methodology

A systematic approach to diagnosing "something is wrong" on a Linux system,
instead of guessing and changing things until it seems to work. The core
idea: form a specific, falsifiable hypothesis before touching anything, and
let evidence — not intuition — decide what to try next.

## When to Use

Use as the entry point for any Linux issue that doesn't have an obvious
cause: a service misbehaving, a system running slow, unexpected errors, or
"it worked yesterday." This is the framework; `linux-performance-analysis`,
`log-analysis`, and `disk-and-memory-issues` are the specific tool sets it
calls into.

## The core discipline: hypothesis before action

The single biggest failure mode in troubleshooting is changing something
without first having a specific, testable theory for *why* that change
should help. This produces two bad outcomes: the problem "goes away" for an
unrelated reason (you never learn the real cause, and it comes back), or
multiple simultaneous changes make it impossible to tell which one mattered.

```
1. Observe   -- what is ACTUALLY happening (not what you assume is happening)
2. Hypothesize -- state a specific, falsifiable cause
3. Test      -- find evidence that would prove or disprove it
4. Act       -- change ONE thing, based on confirmed evidence
5. Verify    -- confirm the change actually fixed the SYMPTOM, not just the SIGNAL
```

"The CPU is at 90%" is an observation. "The CPU is high *because* a
resource is bottlenecked" is not yet a hypothesis — "the CPU is high because
a background cron job is running an unbounded query" is a hypothesis: it's
specific and testable (check the job schedule, check for a running query).

## Layer the investigation, outside in

Work from what the user/system actually experiences down to root cause,
rather than jumping to a guess about internals:

```
Symptom (what's reported)
   │
   ▼
Application layer   -- error messages, logs, exit codes
   │
   ▼
Process layer        -- is it running? in what state? resource usage?
   │
   ▼
OS/kernel layer       -- resource limits, cgroups, signals, /proc
   │
   ▼
Infrastructure layer   -- disk, network, other hosts/services it depends on
```

Skipping layers is the most common way to waste time — restarting a service
(application layer) without checking whether it's OOM-killed (OS layer)
because its dependency's disk filled up (infrastructure layer) fixes nothing
permanently; it'll recur within minutes.

## The USE method, as a starting checklist

For any resource that might be implicated (CPU, memory, disk, network),
check:

- **Utilization** — how busy is it?
- **Saturation** — is work queued waiting for it?
- **Errors** — are operations on it failing?

This is covered in depth in `linux-performance-analysis`; the point here is
that it's a *systematic checklist to run through*, not something to reach
for only after guessing wrong a few times.

## Correlate, don't just collect

Once several signals are gathered (a metric spike, an error log, a deploy
event), the next question is always: **do these actually share a cause, or
did they just happen around the same time?**

```
Signal A: error rate spike at 14:03
Signal B: deploy completed at 14:02
Signal C: CPU normal, memory normal, no infra alerts

→ Strong correlation: timing is tight (within a minute), no other
  candidate cause, deploy is a known potential trigger.
```

```
Signal A: error rate spike at 14:03
Signal B: a DIFFERENT, unrelated deploy at 13:40
Signal C: a third-party dependency's status page shows a 14:00 incident

→ The 13:40 deploy is a weak correlation (23 minutes prior); the
  third-party incident is tighter and has an independent confirming source.
```

A timestamp match alone is not proof — look for a **second, independent**
piece of evidence pointing the same direction (a log line naming the actual
mechanism, a metric that moved for a reason consistent with the hypothesis)
before treating a correlation as the cause.

## The five whys, applied carefully

```
Symptom: Service returns 500 errors
  Why? Database connection pool is exhausted
    Why? Connections aren't being released after use
      Why? A code path throws before calling close()
        Why? An unhandled edge case in input validation
          Why? No test coverage for that edge case
```

Stop when you reach something **actionable and specific** — "no test
coverage for that edge case" can be fixed directly. Stopping too early
("the database is slow") leads to a fix that doesn't address the actual
mechanism and will recur.

Two failure modes with this technique: stopping at the first plausible
answer without verifying it (each "why" should have *evidence*, not just be
plausible-sounding), and conflating a **technical** root cause with a
**process** one — both are often present ("no eviction policy on the cache"
is technical; "code review didn't catch it" is process) and worth
distinguishing, since they need different fixes.

## Confirmation techniques

Preferring evidence that actually *proves* causation over evidence that
merely *correlates*:

| Technique | What it proves |
| --- | --- |
| **Reproduction** | Deliberately trigger the same condition; if the symptom reappears, the mechanism is confirmed |
| **Rollback** | Revert a suspected change; symptom clearing is strong evidence (though not proof — something else could have changed at the same time) |
| **Counterfactual** | Compare an affected instance/host against an unaffected one; what's different between them |
| **Elimination** | Systematically rule out candidate causes one at a time, in order of likelihood |

A **counterfactual** is often the fastest technique available in a live
incident: two nodes behind the same load balancer, one healthy and one not
— diff their configuration, running processes, and resource state directly
rather than theorizing about what might differ.

## Documenting as you go

Keep a running timeline **during** the investigation, not reconstructed
afterward:

```
14:03  error rate alert fired
14:05  confirmed via logs: 500s originating from /api/orders
14:07  checked recent deploys: v2.4.1 deployed 14:02
14:09  hypothesis: v2.4.1 introduced the regression
14:10  rolled back to v2.4.0 on one canary instance
14:12  error rate on canary dropped to baseline; other instances still elevated
14:12  CONFIRMED: v2.4.1 is the cause
14:14  rolled back fleet-wide
14:16  error rate back to baseline fleet-wide
```

This is valuable independent of any formal post-mortem process: it prevents
re-investigating the same already-ruled-out theory, and it's the raw
material for a clear incident writeup afterward rather than a reconstruction
from memory.

## Pitfalls

- **Changing multiple things at once** — even if the problem resolves, you
  don't know which change mattered, and can't be confident it's actually
  fixed versus coincidentally quiet.
- **Treating a correlated timestamp as proof** — always look for a second,
  independent confirming signal.
- **Restarting a service as the first response** — often masks the symptom
  temporarily without addressing the cause, and destroys diagnostic state
  (running processes, open connections, in-memory data) that might have
  explained it.
- **Jumping straight to "it's probably X"** based on a past incident,
  without checking whether the current evidence actually matches X this
  time.
- **Stopping the investigation once the symptom clears**, without
  confirming *why* it cleared — the underlying cause can still be present
  and recur.
- **Skipping layers** — fixing an application-level symptom whose actual
  cause is one layer down (or up).

## Reference

- `linux-performance-analysis` — the USE method and resource-specific tools
- `log-analysis` — extracting evidence from logs efficiently
- `disk-and-memory-issues` — two of the most common specific root causes
- `incident-triage-linux` — applying this methodology under time pressure
