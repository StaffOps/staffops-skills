---
name: log-analysis
description: "Extract signal from logs with grep, awk and journalctl."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [logs, grep, journalctl, log-correlation, timestamps, error-patterns]
    category: troubleshooting
    related_skills: [linux-troubleshooting-methodology, shell-text-processing]
---
# Log Analysis

Extracting useful signal from logs efficiently — narrowing to the right time
window before grepping, correlating across multiple log sources by
timestamp, and recognizing the patterns that separate a real problem from
normal noise. Builds on `shell-text-processing`'s tools with log-specific
technique.

## When to Use

Use when investigating an incident by reading logs, correlating events
across multiple services, hunting for the first occurrence of an error, or
distinguishing a genuine anomaly from routine log noise.

## Narrow the time window first

The most common inefficiency in log analysis is grepping an entire log file
(or worse, an entire day) when the incident window is known to be minutes
wide.

```bash
journalctl -u myapp --since "13:44:00" --until "13:50:00"
awk -v start="13:44:00" -v end="13:50:00" '$2 >= start && $2 <= end' app.log
sed -n '/13:44:00/,/13:50:00/p' app.log      # only works if the log is time-sorted, which most are
```

Narrowing first makes every subsequent `grep`/`awk` pass faster and, more
importantly, reduces noise — a broad search across a full day's logs returns
far more irrelevant matches, making the real signal harder to spot even when
it's technically present in the output.

## Find the FIRST occurrence, not just any occurrence

```bash
grep -m1 "OutOfMemoryError" app.log     # stop at the first match
grep "OutOfMemoryError" app.log | head -1
awk '/ERROR/{print; exit}' app.log       # first ERROR line, then stop
```

The first occurrence of a symptom is usually much closer to the actual
trigger than a later occurrence — cascading failures generate many log
lines, but only the earliest ones are close to root cause. Working backward
from the first occurrence (what happened just before it) is more productive
than working from the most recent or most frequent occurrence.

## Correlating across multiple log sources

```bash
# Merge multiple logs into one time-sorted stream.
sort -k1,2 app.log db.log lb.log | less

# Or, with journalctl, natively across multiple units at once.
journalctl -u myapp -u postgresql -u nginx --since "13:44:00" --until "13:50:00"
```

A single service's logs often don't show the full picture — an application
error at 14:03:12 might be *caused* by a database timeout at 14:03:08 and a
load balancer health-check failure at 14:03:15 that's a downstream effect,
not a separate cause. Interleaving by timestamp (rather than reading each
log in isolation) reveals the actual sequence.

**Clock skew between hosts is a real risk here** — if NTP isn't tightly
synced across the hosts producing these logs, "correlated" timestamps might
be off by seconds, enough to misorder cause and effect. `chronyc tracking`
or `timedatectl` can confirm sync status when the order of events genuinely
matters.

## Recognizing patterns, not just error messages

```bash
# Frequency of each distinct error message -- the shape of the problem,
# not just individual instances.
grep ERROR app.log | awk -F'ERROR' '{print $2}' | sort | uniq -c | sort -rn | head -20

# Errors per minute, to see whether it's a spike, a step change, or gradual.
grep ERROR app.log | awk '{print substr($1,1,16)}' | uniq -c
```

A **spike** (error rate jumps and returns to baseline) suggests a transient
event — a deploy, a brief dependency blip, a traffic burst. A **step change**
(error rate jumps and stays elevated) suggests a persistent state change —
a bad deploy that stayed deployed, a resource that's now genuinely
exhausted, a dependency that's still down. A **gradual increase** suggests a
slow leak or accumulating resource exhaustion. The shape of the graph is
diagnostic information in itself, before reading a single error message's
content.

## Structured vs unstructured logs

```bash
# Unstructured -- text pattern matching, fragile to format changes.
grep "user_id=12345" app.log

# Structured (JSON) -- exact field matching, robust to unrelated format changes.
jq 'select(.user_id == "12345")' app.log
grep '"user_id":"12345"' app.log      # works, but breaks if key order/spacing changes

# journald's own structured fields, queried directly.
journalctl _PID=1234
journalctl SYSLOG_IDENTIFIER=myapp -o json | jq '.MESSAGE'
```

For JSON logs, `jq` is almost always more precise than text-pattern
matching — a `grep` for `"status":500` breaks the moment key order or
whitespace changes, while `jq 'select(.status == 500)'` is robust to that
and additionally understands types (matching the *number* 500, not the
string `"500"` appearing anywhere).

## Distinguishing noise from signal

Not every `ERROR`-level line is actionable. Build a mental (or literal)
allowlist of known-benign recurring messages so they don't obscure a new,
genuine problem:

```bash
# Exclude known-noisy patterns, surfacing what's LEFT.
grep ERROR app.log | grep -v -E "ConnectionResetByPeer|ExpectedRetryableError"
```

A log line that has appeared at a steady, unchanging rate for weeks is
almost certainly not related to a problem that started ten minutes ago —
compare the *current* rate against the historical baseline rate for that
specific message, not just its presence or absence.

## Reading a stack trace efficiently

```
Traceback (most recent call last):
  File "app.py", line 45, in handle_request
    result = process(data)
  File "processor.py", line 102, in process
    return transform(item)
  File "processor.py", line 88, in transform
    return item.value / item.count
ZeroDivisionError: division by zero
```

Read **bottom to top**: the last line is the actual error, and the frame
immediately above it is usually where the *mistake* was made (here: dividing
without checking `item.count`), even though the exception might be caught
and re-logged several frames higher up the call stack. The topmost frames
are often just the request-handling machinery — rarely where the actual bug
lives.

## Extracting structured data from unstructured logs

```bash
# Request time, when a custom nginx/Apache log_format appends it as the
# last whitespace-separated field (a common convention, not universal).
awk '{print $NF}' access.log | sort -n | tail -20

# Status code distribution -- field 9 in the standard combined log format.
awk '{print $9}' access.log | sort | uniq -c | sort -rn

# A specific field from a semi-structured line via a targeted regex.
grep -oP 'latency=\K[0-9.]+' app.log | sort -n | tail -20
```

Splitting on the literal `"` character (`awk -F'"'`) isolates the quoted
request line itself — `awk -F'"' '{print $2}' access.log` gives
`GET /path HTTP/1.1` — not the trailing numeric fields around it; don't
assume a fixed field number without checking one real line of the log
format first, since these positions shift with the log format in use.

`grep -oP` with a `\K` (keep — resets the match start) is an efficient way
to extract just the value of a specific labeled field from otherwise
free-form log lines, without needing a full parser for the format. `-P` is
GNU grep only (see `shell-text-processing`) — it fails on macOS's built-in
BSD grep; use `ggrep` (from Homebrew's `grep` package) or fall back to
`sed -E` there.

## Aggregating for a summary, not a wall of text

```bash
# Top error types by count, in the incident window.
journalctl -u myapp --since "13:44" --until "13:50" -p err \
    | awk -F': ' '{print $2}' | sort | uniq -c | sort -rn

# Unique client IPs seen during an incident.
awk '{print $1}' access.log | sort -u | wc -l
```

For an incident writeup or a handoff to someone else, a ranked summary of
error types and counts communicates far more, far faster, than pasting raw
log excerpts — save the raw excerpts for the one or two lines that are
genuinely the smoking gun.

## Pitfalls

- **Grepping an entire log without narrowing the time window first** —
  slower and noisier than necessary.
- **Anchoring on the most recent or most frequent error** instead of the
  first occurrence, which is usually closer to the actual trigger.
- **Reading a stack trace top-to-bottom** — the useful information is
  usually at the bottom and in the frame just above it.
- **Assuming timestamps across different hosts are perfectly synchronized**
  — verify NTP sync before treating sub-second ordering as reliable.
- **Text-matching JSON logs instead of using `jq`** — fragile to formatting
  changes that don't represent an actual data change.
- **Not distinguishing a spike from a step change** — they point at very
  different classes of cause and warrant different next steps.
- **Pasting raw log dumps into an incident channel/writeup** instead of an
  aggregated summary — buries the signal for readers who weren't already
  deep in the investigation.

## Reference

- `shell-text-processing` — the underlying `grep`/`awk`/`jq` tools in depth
- `linux-troubleshooting-methodology` — where log analysis fits in a broader investigation
