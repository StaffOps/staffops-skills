---
name: incident-triage
description: >
  Use when an alert fires (SLOBurnRateP1/P2, PodCrashLooping, HighErrorRate),
  a user reports service degradation, or pods are in CrashLoopBackOff/OOMKilled.
  Provides severity classification, evidence-driven investigation (≥3 signals for RCA),
  escalation per organizational RACI matrix,
  and communication templates. This agent is STRICTLY read-only and never executes a change.
---

# Incident Triage

## When to use this skill

- Alert fired and cause is not obvious within 30 seconds
- User reports service degradation or outage
- Pods in CrashLoopBackOff, OOMKilled, or Pending
- Error rate spike visible in Grafana dashboards
- SLO burn rate alert triggered (P1/P2/P3)

## When this skill does NOT apply

- Pure cost investigation → use `cost-explorer`
- Alert tuning without active incident → use `alerting-strategy`
- Historical analysis of resolved incident → use `root-cause-analysis`
- Node-level issues (NotReady, spot interruption) → use `eks-node-troubleshooting`
- ESO sync failures → use `external-secrets-aws-sm`

## CRITICAL: Safety Guardrails

- ✅ **Always allowed**: `kubectl get`, `describe`, `logs`, `events`, metric/trace/log queries
- ❌ **NEVER**: any mutation (rollback, scale, restart, apply, patch, delete) — there is no approval path
- ❌ **FORBIDDEN**: `kubectl apply` in PRD — all PRD changes via ArgoCD (GitOps only)
- ❌ **FORBIDDEN**: asserting system state without fresh evidence (<5 min old)

## Step 1: Establish scope and timeline (first 60 seconds)

Query current state of affected service:

```
→ get_pods (namespace of affected service)
→ get_events (filter by namespace, last 15 min)
→ gitops_app_status (check recent ArgoCD syncs)
```

**What to look for**: pod phase, restart count, recent deploy events, age of running pods.

**Evidence freshness rule**: if you checked something >5 minutes ago, re-check before asserting.

## Step 2: Classify severity

| Severity | Criteria | Response time |
|----------|----------|---------------|
| **SEV-1** | User-facing outage, data loss, security breach | Immediate |
| **SEV-2** | Degraded service, SLO burning >14.4x | Within 15 min |
| **SEV-3** | Internal tooling down, non-urgent degradation | Within 1 hour |
| **SEV-4** | Cosmetic, no user impact | Next business day |

## Step 3: Check application metrics (RED method)

```promql
# Error rate
sum(rate(http_server_request_duration_seconds_count{service_namespace="<ns>",http_response_status_code=~"5.."}[5m]))
/ sum(rate(http_server_request_duration_seconds_count{service_namespace="<ns>"}[5m]))

# Latency p99
histogram_quantile(0.99, sum(rate(http_server_request_duration_seconds_bucket{service_namespace="<ns>"}[5m])) by (le))

# Traffic rate
sum(rate(http_server_request_duration_seconds_count{service_namespace="<ns>"}[5m]))
```

**Threshold**: error rate >5% = degraded; >20% = critical. Latency p99 >2s for Tier 1 = degraded.

> ⚠️ **Plataforma trap (DPM/DCP/APPS):** these APIs return HTTP 200 for everything and carry the outcome as a body status code. The 5xx error rate above is **0% by construction** for Plataforma services — it does not mean they are healthy. For Plataforma incident detection, use `BigBoost_SQStoLogStats_Requests_NumberOfQueries_total{AnyError="True"}` — see `plataforma-api-semantics` for the full approach.

**Why application metrics first**: a pod `phase=Running` may be OOMKilling, dropping traffic, or deadlocked. Resources (CPU/mem) lie; application metrics reveal actual user impact.

## Step 4: Check pod health and resources

```
→ check_pod_health (specific pods with errors)
→ get_pod_metrics (CPU/memory actual usage)
→ get_previous_logs (if pods restarting — check terminated reason)
```

**What to look for**: `lastState.terminated.reason=OOMKilled`, restart count >3, resource usage near limits.

## Step 5: Trace and log correlation

```traceql
{resource.service.name="<service>" && status = error}
```

```logql
{namespace="<ns>", app="<service>"} |= "error" | logfmt
```

**What to look for**: error spans with specific exception types, log patterns correlating with the timeline.

## Step 6: Check recent changes

```
→ gitops_apps_list (filter by namespace)
→ Look for: recent syncs, failed syncs, image tag changes
→ Check Argo Rollouts: is a canary in progress or recently aborted?
```

## Step 7: Summarize findings

1. **Status** — healthy / degraded / critical
2. **Root cause hypothesis** — cite observed values (e.g., "error rate 12.3% since 14:02 correlating with deploy of v2.3.0")
3. **Recommended remediation** — ranked:
   - ⚠️ RECOMMENDATION ONLY — read-only agent, a human executes: rollback via ArgoCD (blast radius: all pods of service X; rollback: re-sync previous image tag)
   - ⚠️ RECOMMENDATION ONLY — read-only agent, a human executes: scale up replicas (blast radius: additional cost; rollback: scale down)
4. **Confidence** — count of independent signals (≥3 required for asserting root cause)

## Decision tree

```
Alert fires / user reports issue
├── Can you identify cause in <30s?
│   ├── Yes → fix directly (with approval if mutating)
│   └── No → continue this procedure
├── Is it user-facing? (check error rate, traces)
│   ├── Yes, full outage → SEV-1, escalate immediately
│   ├── Yes, degraded → SEV-2, investigate + mitigate
│   └── No → SEV-3/4, investigate at normal pace
├── Was there a recent deploy? (gitops_app_status)
│   ├── Yes, correlates temporally → rollback candidate (⚠️ RECOMMENDATION ONLY — read-only agent, a human executes)
│   └── No → check resources, dependencies, platform
└── ≥3 independent signals pointing to same cause?
    ├── Yes → declare root cause, propose fix
    └── No → escalate per RACI, gather more evidence
```

## Escalation (per organizational RACI)

| Condition | Escalate to |
|-----------|------------|
| Infrastructure incident (nodes, networking, EKS, mesh) | DevOps team (R) |
| Application/product incident confirmed | Developers (R) + Team Leader (A) |
| Deploy/rollback needed | Developers (R) + Team Leader (A) |
| Security incident suspected | Security team immediately |
| AWS service degradation | DevOps (R) + AWS support case |

> **Note**: BDC does NOT have an "oncall SRE" role. The first senior responder becomes IC.

## Related skills

- `root-cause-analysis` — formal RCA after mitigation (5 Whys, fault tree)
- `eks-node-troubleshooting` — node-level issues (NotReady, spot, Karpenter)
- `alerting-strategy` — tuning alerts after incident resolution
- `error-budget-framework` — quantifying incident SLO impact
