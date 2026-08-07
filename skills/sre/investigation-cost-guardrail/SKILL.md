---
name: investigation-cost-guardrail
description: "Applies to EVERY investigation before the first query is executed. Triggered always — enforces time/cost budgets per incident severity, prevents unbounded queries (PromQL over 30d, TraceQL without time window, repeated kubectl get --all-namespaces), mandates narrow-first query strategy, and defines stop conditions. Cost: $0.50/minute, quota: 10 concurrent chats. A runaway investigation starves other users."
---

# Investigation Cost Guardrail

## When to use this skill

- **Always.** This skill is a pre-flight check before any investigation begins.
- Before executing the first query in any incident triage, evaluation, or ad-hoc investigation.
- When an investigation has been running for more than 3 minutes without new findings.
- When you are about to broaden a time window or remove a label selector.

## When this skill does NOT apply

- Read-only questions with a single lookup (e.g., "what's the current pod count for service X") — these are inherently cheap.
- Documentation or configuration generation (no runtime queries involved).

## Step 1: Classify severity and assign budget

**Cost model**: $0.0083/second = $0.50/minute = $30/hour.

| Severity | Max duration | Max cost | Max queries | Reasoning |
|----------|-------------|----------|-------------|-----------|
| **P1** (user-facing outage) | 10 min | $5.00 | 25–30 | Outage cost >> investigation cost; fast RCA has highest ROI |
| **P2** (degraded, SLO burning) | 7 min | $3.50 | 18–22 | Degradation costs ~$X/min in SLO burn; investigation should cost less |
| **P3** (internal, non-urgent) | 4 min | $2.00 | 10–14 | Low urgency; if not answered in 4 min, report partial findings |
| **P4** (question, no incident) | 2 min | $1.00 | 5–8 | Informational; a P4 spending P1 budget is pure waste |
| **Evaluation** (proactive review) | 8 min | $4.00 | 20–25 | Comprehensive but bounded; split into dimensions, stop when covered |

**Arithmetic**: 10 min × $0.50/min = $5.00. Each MCP tool call ≈ 10–15 seconds including response parse.
Therefore 10 min ÷ ~25 sec/query ≈ 25 queries is the P1 ceiling.

## Step 2: Apply the narrow-first query strategy

**Rule: start with the smallest time window and the most specific selector that can answer the question. Broaden ONLY if the narrow query returns no signal.**

| Expensive query | Cost reason | Cheap alternative |
|-----------------|-------------|-------------------|
| `query_range` over 30d with step=1m | 43,200 data points × N series | Start with `[1h]`, then `[6h]` if needed |
| `traceql-search` with no `start`/`end` | Scans ALL stored traces | Always pass `start=now-30m` initially |
| `kubectl get pods --all-namespaces` every step | 10k+ pods, 5s parse time | Filter by namespace from the alert context |
| `label_values(__name__)` (all metric names) | Unbounded, 50k+ names | Use `label_values(__name__, {job="..."})` with a job filter |
| Same metric queried 3× with minor variations | Redundant; no new info | Query once, parse the result fully |
| `list_prometheus_metric_names` with `limit=1000` | Transfers massive response | Use `regex` filter and `limit=10` |

**Progression pattern**:
1. Query with the exact service/namespace/pod from the alert context, last 15 min.
2. If empty → expand to 1h.
3. If still empty → expand selector (remove one label).
4. If still empty after 3 expansions → report "no signal found" as a finding.

## Step 3: Monitor budget consumption during investigation

Track mentally after each query:
- Elapsed time since investigation started
- Number of queries executed
- Whether the last 3 queries returned NEW information

**At 60% budget consumed**: evaluate — do you have enough signal for a partial report? If yes, report.

**At 80% budget consumed**: STOP unless the next query is highly likely to confirm a hypothesis already supported by ≥2 signals.

## Step 4: Apply stop conditions

STOP the investigation and report partial findings when ANY of these is true:

| Condition | Action |
|-----------|--------|
| 3 consecutive queries returned no new signal | Stop. You've exhausted this search space. |
| Same hypothesis re-tested with a different query phrasing | Stop. If 2 queries didn't confirm it, the hypothesis is wrong. |
| Budget ceiling reached (time or query count) | Stop. Report what you have, flag confidence as LOW. |
| Root cause confirmed with ≥3 independent signals | Stop. You're done — further queries are waste. |
| Downstream investigation needed (different domain/tool) | Stop. Recommend escalation to the appropriate skill. |

## Step 5: Account for concurrency

**Quota: 10 concurrent chats.** A 10-minute P1 investigation consumes 1 slot for the entire duration.
If multiple incidents are active, the longest investigations must be the highest severity.

Rules:
- P4 investigations that exceed 2 min are actively harming other users.
- If you detect you're in a low-severity investigation that has already consumed half its budget with no progress → abort early.
- Never hold a chat slot idle (waiting for a human response while queries could run) — if blocked, report partial and close.

## Step 6: Summarize with budget accounting

Every investigation output MUST include a budget footer:

```
---
**Budget**: P2 tier ($3.50 / 7 min max)
**Consumed**: 4 min 12s / ~14 queries / ~$2.10
**Status**: WITHIN BUDGET
```

If over budget:
```
**Status**: OVER BUDGET (exceeded P3 ceiling by 45s — escalated complexity justified? [reason])
```

## Decision tree

```
Investigation request arrives
├── Classify severity (P1/P2/P3/P4/Evaluation)
├── Set budget ceiling from table
├── First query: narrow time + specific selector
│   ├── Signal found → follow specific skill, budget-aware
│   └── No signal → broaden ONE dimension (time OR selector)
│       ├── Signal found → continue
│       └── 3 empty expansions → STOP, report "no signal for X"
├── After each query: track elapsed + query count
│   ├── 60% budget → can I report now? → YES: report partial
│   ├── 80% budget → MUST stop unless next query is definitive
│   └── 100% budget → HARD STOP, report whatever you have
└── Root cause confirmed (≥3 signals) → report immediately, save remaining budget
```

## Related skills

- `incident-triage` — classifies severity that feeds into budget tier selection
- `root-cause-analysis` — requires ≥3 signals; this skill ensures you get them efficiently
- `incident-skip-criteria` — skipping costs $0; always check skip criteria BEFORE spending budget
