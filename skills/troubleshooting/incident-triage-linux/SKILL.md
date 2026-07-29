---
name: incident-triage-linux
description: "Triage a live Linux incident quickly and safely."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [incident, triage, on-call, mitigation, sev1, first-response]
    category: troubleshooting
    related_skills: [linux-troubleshooting-methodology, disk-and-memory-issues, log-analysis]
---
# Incident Triage on Linux

The first few minutes of responding to a live incident, specifically: what
to check immediately, when to mitigate versus keep investigating, and how to
avoid the mistakes that turn a contained incident into a worse one. This is
the time-pressured, mitigate-first counterpart to
`linux-troubleshooting-methodology`'s slower, more thorough investigation.

## When to Use

Use as the first response to a paging alert or an active production
incident on Linux infrastructure, when deciding whether to mitigate
immediately or keep diagnosing, or when handing off context to someone else
joining the incident in progress.

## Mitigate vs diagnose: the first real decision

**Under active user impact, restoring service takes priority over
understanding root cause.** This is a deliberate reordering from normal
troubleshooting — an incident is not the time for the patient, evidence-first
process in `linux-troubleshooting-methodology`; it's the time for whichever
of these is safe and fast:

| Mitigation | When it applies |
| --- | --- |
| Rollback | A recent deploy is a plausible cause and rollback is fast/safe |
| Restart | The known failure mode is transient (a leak, a stuck connection pool) and a restart is known-safe for this service |
| Failover | A redundant instance/region/replica exists and can take over |
| Scale up | The signal points at genuine capacity exhaustion, not a bug |
| Circuit-break / feature flag | A specific code path can be disabled without a full rollback |

Each of these can be executed **and evaluated for effect** in a couple of
minutes — that's the point. If a plausible mitigation exists and is safe,
try it while continuing to gather evidence in parallel, rather than fully
diagnosing before acting.

**Restarting is not free** — it also destroys diagnostic state (running
process, open connections, in-memory data, core dump opportunity) that might
have explained the cause. For a first, unexplained, and severe incident,
capturing a small amount of diagnostic evidence *before* restarting
(seconds, not minutes) is usually worth it — see below.

## The first 5 minutes, roughly in order

```bash
# 1. What actually changed recently? (Often the fastest path to a cause.)
last -x | head -5                    # recent logins/reboots
journalctl --since "-30min" -p err   # recent errors, system-wide

# 2. Is the obvious stuff healthy?
systemctl --failed                   # any failed units right now
df -h; df -i                          # disk space and inodes
free -h                                # memory
uptime                                 # load average

# 3. Is the specific affected service actually running and listening?
systemctl status myapp --no-pager
ss -tlnp | grep <port>

# 4. What does ITS log say, right now?
journalctl -u myapp -n 50 --no-pager
```

This sequence is deliberately broad and shallow — the goal in the first few
minutes is finding the *category* of problem (deploy-related, resource
exhaustion, dependency failure, infrastructure), not yet the precise root
cause. `linux-troubleshooting-methodology` and the resource-specific skills
take over once the category is known.

## Capturing evidence before it's gone

If a restart or rollback is about to happen and the cause isn't understood
yet, grab a few seconds of evidence first — cheap now, potentially
irreplaceable in five minutes:

```bash
# A process about to be restarted/killed:
ps -p <pid> -o pid,ppid,stat,etime,cmd > /tmp/incident-ps.txt
cat /proc/<pid>/status > /tmp/incident-status.txt
jstack <pid> > /tmp/incident-jstack.txt 2>/dev/null    # JVM only, if applicable
gcore <pid> 2>/dev/null                                 # a core dump, if space/time allows

# The system state generally:
dmesg -T > /tmp/incident-dmesg.txt
journalctl --since "-15min" > /tmp/incident-journal.txt
```

This step should take well under a minute — the point is not a thorough
investigation right now, it's not losing the *option* to investigate
properly later. Skip it entirely if the mitigation is time-critical and
every second matters; evidence capture is a should, not a must, during an
active severe incident.

## Communicating status concisely

During an active incident, status updates should be short and structured —
long narrative updates cost the responder time and are harder for others to
parse quickly:

```
IMPACT: API returning 500s for ~15% of requests, started 14:03
STATUS: Investigating -- correlates with a deploy at 14:02
ACTION: Rolling back to previous version now
NEXT UPDATE: 10 minutes, or sooner if it resolves
```

Four lines: what's actually broken (impact), current state (status), what's
being done right now (action), and when to expect the next update. This
format works as well for a single-person response as for a full incident
channel with stakeholders watching.

## Avoiding the incident-widening mistakes

- **Running an untested command against production under pressure** — a
  command that's fine to run carefully is a different risk profile when
  typed quickly during a page at 3am. A `-n`/`--dry-run` pass first, when
  the command supports one, is cheap insurance.
- **Restarting *everything*** as a first response, rather than the
  specifically affected component — widens blast radius and destroys
  diagnostic state across more of the system than necessary.
- **Making a change without a rollback plan for the change itself** —
  every mitigation should have a known way to undo it if it doesn't help or
  makes things worse.
- **Working in isolation on a severe incident** — a second person catching
  a mistake, or confirming an interpretation, is worth the coordination
  overhead once impact is significant.
- **Declaring resolution the moment the symptom stops** without a brief
  observation window — some causes (a slow leak, a queue draining) produce
  a temporary-looking recovery that isn't actually resolved.

## After mitigation: confirm, don't assume

```bash
# Confirm the SYMPTOM is actually gone, not just that the action completed.
curl -sf https://health-endpoint/ && echo OK
journalctl -u myapp -f              # watch for a few minutes, not just a point-in-time check
```

The action succeeding (a rollback command exits 0, a restart completes) is
not the same as confirming the actual user-facing symptom is resolved —
verify against the original impact statement, not against the mitigation
step itself completing.

## Handoff

If handing off to someone else mid-incident, a brief structured handoff is
far more useful than "it's still broken, good luck":

```
WHAT'S BROKEN: API returning 500s, ~15% of requests
TIMELINE: started 14:03, correlates with 14:02 deploy
TRIED: rolled back at 14:14 -- did NOT resolve it
CURRENT HYPOTHESIS: dependency (payments service) may be the actual cause,
  investigating their status page and our timeout logs
EVIDENCE CAPTURED: /tmp/incident-*.txt on host web-03
```

This mirrors the running-timeline habit from
`linux-troubleshooting-methodology` — it exists specifically so a handoff
(or your own memory an hour later) doesn't require reconstructing the
investigation from scratch.

## Pitfalls

- **Fully diagnosing before attempting any mitigation** — under active
  impact, a fast, safe, reversible mitigation attempt in parallel with
  investigation is usually the right trade-off.
- **Restarting without capturing evidence first**, for a first-time or
  poorly-understood failure — the diagnostic opportunity doesn't come back.
- **Long narrative status updates** during an active incident — cost
  responder time; use a short structured format.
- **Treating "the mitigation command succeeded" as "the incident is
  resolved"** — verify against the actual user-facing symptom.
- **A vague handoff** ("it's broken, I tried some stuff") that forces the
  next responder to start over.
- **Skipping the brief observation window after mitigation** — some
  symptoms return after looking temporarily resolved.

## Reference

- `linux-troubleshooting-methodology` — the thorough investigation process this complements
- `disk-and-memory-issues` — a common specific root cause to check early
- `log-analysis` — extracting the evidence referenced throughout this skill
