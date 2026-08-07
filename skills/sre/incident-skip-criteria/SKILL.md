---
name: incident-skip-criteria
description: >
  Incident Triage agent ONLY. Evaluate whether an alert should be SKIPPED (no paid
  investigation) or INVESTIGATED. Triggers: every incoming alert before the investigation
  budget is spent. Criteria: known-noisy signals, in-progress rollouts correlating with
  the alert, BTC/DEV environment expected saturation, duplicate/child alerts of an
  active parent investigation. HARD RULE: NEVER skip P1/CRITICAL, data-loss signals,
  security/auth incidents, or PRD alerts with confirmed user impact.
---

# Incident Skip Criteria

## When to use this skill

- **Every time** an alert arrives at the Incident Triage agent, BEFORE spending investigation budget.
- This is a gate: run the decision matrix FIRST, then either emit `SKIP` or proceed to `incident-triage`.
- A skip costs $0.00; a wasted investigation on a known-noise alert costs $1–5.

## When this skill does NOT apply

- The incident has already been classified as P1/P2 (investigation is mandatory; skipping is forbidden).
- The agent type is not Incident Triage (Evaluation agents don't skip — they review).
- Post-incident analysis — this skill is for real-time triage only.

## CRITICAL: The asymmetric risk rule

**A wrong SKIP is catastrophically worse than a wasted investigation.**

- Wrong SKIP → silent outage, undetected data loss, customer impact with no response.
- Wrong INVESTIGATE → you spent $2–5 on a non-issue; easily recovered.

**When ANY ambiguity exists in the criteria below → INVESTIGATE.** Default is always INVESTIGATE.

## Step 1: Check the NEVER-SKIP list (hard rules)

If ANY of these is true, emit `INVESTIGATE` immediately — do NOT evaluate further criteria:

| Condition | Reason |
|-----------|--------|
| Severity = CRITICAL or P1 | By definition, always warrants investigation |
| Alert mentions data loss (`vm_rpc_rows_dropped_on_overload_total`, `otelcol_exporter_enqueue_failed_*`) | Permanent loss is irrecoverable |
| Alert involves security/auth (IAM, secrets, certificate expiry, unauthorized access) | Security incidents have unbounded blast radius |
| Environment = PRD AND user-facing error rate > 0 confirmed | Real user impact overrides all noise criteria |
| Alert involves `production` namespace AND service-level SLO burn rate > 1x | Active budget consumption = real problem |
| First occurrence of this alert type (never seen before) | Unknown signals cannot be pre-classified as noise |

## Step 2: Check in-progress rollout correlation

An alert firing during an active deployment of the SAME service is expected transient behavior.

**Verification steps (mandatory — do not skip without checking)**:

1. Query ArgoCD sync status for the affected service/namespace.
2. Check if a Rollout (canary/blue-green) is currently in-progress (not Healthy/Degraded).
3. Confirm temporal correlation: alert fired WITHIN the rollout window (not before, not 10+ min after).

**SKIP criteria met when ALL three are true**:
- Rollout is actively in-progress (`phase=Progressing` or canary step mid-flight).
- Alert is for the same service being rolled out.
- Alert type is pod-level (CrashLoopBackOff, Pending, OOMKilled) — NOT request-level (error rate/latency).

**SKIP output**: `SKIP — alert correlates with in-progress rollout of {service} (phase: {phase}, step: {step}). Rollout health monitoring will catch failures.`

**DO NOT SKIP**: if the alert is about error rate or latency — a broken canary with user traffic IS a real incident.

## Step 3: Check batch/environment semantics

**BTC (batch) environment:**
- Batch workloads (CronWorkflows, ETL, bulk processing) by design cause resource spikes during their schedule window.
- Pod Pending/OOMKilled/HighCPU in `BTC` namespace during the known batch window (typically 00:00–06:00 UTC) is expected.

**SKIP criteria**: resource saturation alerts in BTC namespace during batch schedule AND the alert is resource-level (not data-correctness or completion-failure).

**DO NOT SKIP**: batch job FAILED/errored (not just resource pressure), or batch has exceeded its expected completion window by >2x.

**DEV environment:**
- DEV alerts have inherently lower value than PRD.
- However, sustained DEV failures can block developer productivity.

**SKIP criteria**: transient DEV alerts (single pod restart, brief spike) that resolve within 5 min.

**DO NOT SKIP**: sustained DEV outages lasting >15 min (blocks development teams).

## Step 4: Check duplicate/child alert suppression

If a PARENT alert for the same root cause is already under active investigation:

**SKIP criteria ALL must be true**:
- A parent alert exists (broader scope — e.g., "Node NotReady" is parent of "Pod Pending on that node").
- The parent alert is actively being investigated (not just acknowledged/silenced).
- The child alert's affected resource is a subset of the parent's scope.

**SKIP output**: `SKIP — child alert of active investigation {parent_alert_id}. Root cause: {parent_summary}. Will resolve when parent is fixed.`

**DO NOT SKIP**: if the "child" affects a different service than the parent, or if the temporal pattern suggests an independent cause.

## Step 5: Check known-noisy signals

Conservative list of signals that are documented as expected noise:

| Signal | Condition for skip | Reasoning |
|--------|-------------------|-----------|
| `KubeDeploymentReplicasMismatch` | Duration < 5 min AND rollout in-progress | Transient during scale-up/rollout |
| `KubePodNotReady` in `kube-system` | Single pod, self-heals < 3 min | System pod restarts are auto-recovered |
| `CPUThrottlingHigh` | < 25% throttle rate AND no latency impact | Common in burstable workloads; cosmetic |
| `NodeNotReady` (spot) | Karpenter replacement node launching within 2 min | Expected spot interruption behavior |
| `TargetDown` | Scrape target disappeared AND corresponding pod was terminated (scale-down) | Expected during scale-down events |

**IMPORTANT**: this list is CONSERVATIVE. Do NOT add signals here without validated production evidence. A noisy alert that occasionally catches real issues must remain INVESTIGATE.

## Step 6: Emit decision

Output format — ALWAYS include:

```
**Decision**: SKIP | INVESTIGATE
**Criterion matched**: [which rule from Steps 1–5 triggered the decision]
**Evidence checked**: [what you verified — e.g., "ArgoCD sync status: Progressing, image: v2.3.1"]
**Confidence**: HIGH | MEDIUM (if MEDIUM, lean toward INVESTIGATE)
```

Examples:

```
**Decision**: SKIP
**Criterion matched**: In-progress rollout correlation (Step 2)
**Evidence checked**: ArgoCD app dpm-people-api sync=Progressing, Rollout phase=Canary step 2/5, alert=PodCrashLoopBackOff for same service
**Confidence**: HIGH

**Decision**: INVESTIGATE
**Criterion matched**: NEVER-SKIP (Step 1) — PRD environment with error rate > 0
**Evidence checked**: http_server_request_duration_seconds{status_code=~"5.."} = 3.2% error rate in last 5m
**Confidence**: HIGH
```

## Decision tree

```
Alert arrives
├── NEVER-SKIP list match? (Step 1)
│   ├── YES → INVESTIGATE (immediately, no further checks)
│   └── NO → continue
├── In-progress rollout of same service? (Step 2)
│   ├── YES, pod-level alert → SKIP (with rollout evidence)
│   ├── YES, but request-level alert → INVESTIGATE (broken canary = real)
│   └── NO → continue
├── BTC batch window + resource alert? (Step 3)
│   ├── YES → SKIP (with schedule evidence)
│   └── NO → continue
├── DEV transient alert? (Step 3)
│   ├── YES, <5 min, self-resolving → SKIP
│   └── NO → continue
├── Parent alert already investigated? (Step 4)
│   ├── YES, child is subset → SKIP (with parent reference)
│   └── NO → continue
├── Known-noisy signal? (Step 5)
│   ├── YES, conditions match exactly → SKIP
│   └── NO or conditions don't match → INVESTIGATE
└── None matched → INVESTIGATE (default)
```

## Related skills

- `incident-triage` — the investigation that runs if decision is INVESTIGATE
- `investigation-cost-guardrail` — the skip decision saves the cost; guardrail bounds the investigation
- `alerting-strategy` — if too many alerts are SKIP, the alerting rules need tuning (fix the alerts, not the skip list)
