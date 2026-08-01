---
name: session-handoff
description: "Hand off an incident or migration to the next on-call shift."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [handoff, incident, migration, oncall, workflows]
    category: workflows
    related_skills: [incident-response-runbook, post-mortem-templates]
---
# Session Handoff

Capture an in-progress incident investigation or infra migration into a
handoff artifact so the next on-call engineer's agent session can pick it up
without re-treading ground already covered. This is for operational handoff
across a shift change or a hard stop mid-investigation — not for routine
"continue this coding task tomorrow" handoff, which does not need this level
of structure.

Two modes are covered: writing a handoff document (works with any harness,
any engineer) and spawning a background agent seeded with the handoff summary
(Claude Code specific, faster, but ties the handoff to that tool).

## When to Use

- An on-call engineer needs to end their shift mid-incident and hand the
  investigation to whoever picks up next.
- A long-running migration (data migration, cluster migration, dependency
  upgrade) spans a shift change or a multi-day pause.
- You are about to go heads-down elsewhere and want your own future session
  to resume without re-deriving context.

Invoke this only when the user explicitly asks for a handoff. Never generate
one automatically mid-task, and never generate one as a substitute for
declaring an incident or closing it out — see `incident-response-runbook` for
that lifecycle.

## Two Handoff Modes

### Mode A: Background agent (Claude Code fast path)

If the operator is running Claude Code and wants the next session live
immediately, spawn a detached background agent seeded with the handoff
summary:

```bash
claude --bg --name "<descriptive name>" "<handoff summary>"
```

- Requires the `claude` CLI's background-agent feature (`claude --bg`, current
  as of this writing — confirm it still exists in your installed CLI version
  before relying on it, since flag names and background-agent behavior can
  change between releases).
- Always pass `--name` with something identifiable in a job list at 3am, e.g.
  `--name "INC-2381 payment-api 500s"` or `--name "migrate-rds-pg16 phase2"`
  — not `--name "handoff"`.
- The agent starts in the current working directory and returns immediately;
  the user manages it later with `claude agents`.
- The handoff summary passed as the prompt follows the same structure and
  redaction rules as Mode B below — it is the same document, just delivered
  as a prompt instead of a file.
- Caveat: this only works if the next engineer is also on Claude Code. If
  they might use a different harness, or if the background job could be
  lost (host restart, `claude agents` state cleared), do not rely on this
  alone — pair it with Mode B, or use Mode B only.

### Mode B: Handoff document (harness-agnostic fallback)

Write the handoff document to a path **outside the project's git workspace**
— the OS temp directory, or a personal scratch/notes location. Never inside
the repo, even in a gitignored directory: ephemeral handoff state must never
land in `git status`, and must never risk being swept into a commit. Any
engineer, on any tool, can open a plain file.

This is the default mode. Use it whenever there is any doubt about which
harness the next session will use, or whenever the handoff needs to survive
longer than a single background job's lifetime.

## Handoff Document Structure

Use `references/handoff-template.md` as the skeleton. The sections are
deliberately ordered so the most perishable, highest-value information comes
first:

1. **Status** — current hypothesis, current phase, severity (if an
   incident), who is IC, elapsed time since detection or migration start.
   Not "still investigating" — the actual working theory, even if wrong.
2. **Ruled out (do not repeat this investigation)** — every dead end already
   checked, with the check performed and the negative result. This is the
   single highest-value section in the document: the thing a stale or
   missing handoff doc costs the most is someone re-running a query, a
   `kubectl` check, or a hypothesis test that already came back negative.
   Write it as a checklist, not prose, so it can be scanned in ten seconds.
3. **Still running** — anything in flight right now: a background
   remediation, a migration step, a long-running job, a canary rollout.
   State how to check its status and what "done" looks like, so the next
   engineer does not duplicate or interrupt work already underway.
4. **Links** — the incident channel or thread, the ticket, the runbook in
   use, and any dashboard/query links. Reference these by URL or path;
   do not re-paste their content into the handoff doc. This mirrors
   `incident-response-runbook`'s Slack-based coordination pattern and
   `post-mortem-templates`' evidence-by-link convention — the handoff doc
   should point at the same artifacts a post-mortem will eventually cite,
   not invent a fourth place to look.
5. **Next steps** — the concrete next 1-3 actions, in priority order.
6. **Rollback plan** (migrations only) — how to revert if the next step
   fails. Omit for incidents already past mitigation.
7. **Suggested skills** — which skills the next session should invoke first
   (e.g. `incident-response-runbook` if still mitigating,
   `post-mortem-templates` if the incident is resolved and needs writeup,
   a domain skill like `eks-management` if the next step is cluster-specific).

Tag the Status section's hypothesis with a **suspected cause category** —
the same six categories `post-mortem-templates` uses for root cause (Code /
Config / Infra / Deploy / Capacity / Dependency), or "not yet narrowed" if
it's too early to guess. See `references/handoff-template.md` for the exact
field. A hypothesis tagged on handoff slots directly into the eventual
post-mortem's RCA section instead of needing to be reformatted later.

## Redaction Checklist

Redaction is not "remove sensitive information" as a vague instruction —
strip these concrete categories before writing or transmitting the handoff,
whichever mode is used:

| Category | What to strip | What to keep instead |
|----------|---------------|----------------------|
| Credentials and tokens | API keys, DB passwords, bearer/JWT tokens, kubeconfig client certs, AWS access keys | The secret's **name**, not its value (matches this catalog's `k8s-safety` rule: refer to secrets by key, never echo the value) |
| Customer / PII data | Customer names, emails, phone numbers, account IDs found in logs or payloads | An anonymized label ("Customer A"), matching `post-mortem-templates`' sharing convention |
| Internal hostnames and identifiers | Real internal hostnames, account IDs, ARNs, bucket names, internal URLs | This catalog's placeholder vocabulary: `<org>`, `<org-domain>`, `<ACCOUNT_ID>`, `<workspace>` |
| Raw payloads and stack traces | Full request/response bodies or dumps that might carry any of the above | A truncated excerpt (first/last lines) plus a pointer to where the full capture lives (log query, trace ID) |

If a background agent is used (Mode A), the redaction applies to the prompt
string itself — it is not a file you can edit after the fact, so redact
before calling `claude --bg`.

## Anti-patterns

- Writing the handoff document inside the project repo, even in a
  gitignored path — it risks landing in a commit and has no reason to
  outlive the shift it was written for.
- Generating a handoff automatically mid-task without the user asking for
  one — this skill is user-invoked only.
- Pasting full log dumps, diffs, or Slack threads into the document instead
  of linking the incident channel, ticket, or runbook.
- Omitting the "ruled out" section — this guarantees the next engineer
  re-runs a check that already came back negative.
- Writing a vague status ("still investigating") instead of the actual
  current hypothesis, even a tentative one.
- Pasting raw credentials, tokens, or PII "just for context" — reference by
  name or use a placeholder instead.
- Using only the background-agent mode (Mode A) for a handoff that needs to
  survive more than a few hours, or that might be picked up by someone on a
  different tool — pair it with a written document, or skip it in favor of
  Mode B.
- Treating this as generic dev-session handoff for routine, low-stakes work
  — a simple "pick up where I left off" note does not need severity,
  ruled-out lists, or redaction discipline; save this skill for incidents
  and migrations where re-treading ground or leaking a secret has real cost.
