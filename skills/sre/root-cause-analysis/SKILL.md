---
name: root-cause-analysis
description: "Use when investigating production incidents where the root cause is unknown. Provides structured techniques (5 Whys, fault tree, elimination), cross-signal correlation patterns, timeline construction from K8s/ArgoCD/VictoriaMetrics/Loki, and empirical validation checklist. Grounded on VictoriaMetrics + OTel + Loki + Tempo stack."
---
# Root Cause Analysis

## When to use

- Alert fired and cause is NOT obvious within 30 seconds
- Multiple services failing simultaneously (cascading)
- Symptom is intermittent / hard to reproduce
- Post-incident: need formal RCA for post-mortem
- "Nothing changed" failures (no deploy but system broke)

## When NOT to use

- Cause is obvious (typo in config, known deploy broke it) → fix directly
- Simple config question → use relevant skill
- Planning/design work → use `sla-slo-design` or `alerting-strategy`
- Need to triage severity first → use `incident-triage`

## Steps

### 1. Establish the symptom precisely

Define WHAT is failing, for WHOM, and SINCE WHEN:

```bash
# What is the error rate right now?
curl -s "https://victoria-metrics-read.<org-domain>/select/0/prometheus/api/v1/query?query=sum(rate(http_server_request_duration_seconds_count{service_name=\"SERVICE\",http_status_code=~\"5..\"}[5m]))" | jq '.data.result[].value[1]'

# When did it start? (find the step change)
curl -s "https://victoria-metrics-read.<org-domain>/select/0/prometheus/api/v1/query?query=changes(http_server_request_duration_seconds_count{service_name=\"SERVICE\",http_status_code=~\"5..\"}[1h])"
```

### 2. Build timeline (first 5 minutes of investigation)

Gather ALL events in the window — deploy, restart, alert, log:

```bash
# K8s events (last 30 min)
kubectl get events -n NAMESPACE --sort-by='.lastTimestamp' --context CLUSTER | tail -30

# Pod restarts
kubectl get pods -n NAMESPACE -l app.kubernetes.io/name=SERVICE --context CLUSTER -o custom-columns='NAME:.metadata.name,RESTARTS:.status.containerStatuses[0].restartCount,LAST_STATE:.status.containerStatuses[0].lastState.terminated.reason'

# ArgoCD deploys in window
kubectl get applications -n argocd --context core-devops -o json | jq -r '.items[] | select(.metadata.name | test("SERVICE")) | "\(.status.operationState.finishedAt) \(.status.sync.revision[0:8])"'

# Alert history
curl -s "https://alertmanager.<org-domain>/api/v2/alerts?filter=namespace%3D\"NAMESPACE\"" | jq '[.[] | {alertname: .labels.alertname, startsAt: .startsAt, state: .status.state}]'
```

### 3. Form hypotheses (max 3)

Based on the timeline, list the top 3 most likely causes:

| # | Hypothesis | Predicted signal if true |
|---|-----------|--------------------------|
| 1 | Deploy introduced bug | Errors start exactly after sync |
| 2 | Upstream dependency down | Trace shows timeout on external call |
| 3 | Resource exhaustion | OOMKill or CPU throttle visible |

### 4. Test each hypothesis (elimination method)

For each hypothesis, define what evidence would CONFIRM and what would REFUTE:

```bash
# Hypothesis 1: Deploy correlation
# CONFIRM if: error start time matches deploy time (±2min)
kubectl get applications -n argocd --context core-devops -o json | jq '.items[] | select(.metadata.name=="SERVICE") | .status.operationState.finishedAt'

# Hypothesis 2: Upstream dependency
# CONFIRM if: trace shows error span on external call
# Query Tempo for error traces
curl -s "https://tempo-gateway.monitoring/api/search?tags=service.name%3DSERVICE%26status%3Derror&limit=10"

# Hypothesis 3: Resource exhaustion
# CONFIRM if: OOMKill in events OR container_memory near limit
kubectl get events -n NAMESPACE --context CLUSTER --field-selector reason=OOMKilling
curl -s "https://victoria-metrics-read.<org-domain>/select/0/prometheus/api/v1/query?query=container_memory_working_set_bytes{namespace=\"NAMESPACE\",pod=~\"SERVICE.*\"}/container_spec_memory_limit_bytes{namespace=\"NAMESPACE\",pod=~\"SERVICE.*\"}"
```

### 5. Validate with 3+ independent signals

A root cause is PROVEN only when ≥3 signals agree:

```
✅ VALID RCA:
  Signal 1 (metric): error_rate spike at 14:03 ✓
  Signal 2 (log): first 500 error at 14:03:12 ✓
  Signal 3 (deploy): ArgoCD sync completed 14:02:58 ✓
  → CONFIRMED: deploy caused regression

❌ INVALID RCA:
  Signal 1 (metric): error_rate spike at 14:03
  Signal 2 (log): first error at 13:45 (18 min EARLIER!)
  → REFUTED: timing mismatch = different cause
```

### 6. Confirm with empirical test

| Method | When | Command |
|--------|------|---------|
| Rollback | Deploy-related | `kubectl rollout undo deployment/SERVICE -n NAMESPACE --context CLUSTER` |
| Canary fix | Logic bug | Apply fix to 1 pod, compare error rate |
| Isolation | Dependency | Disable the suspect upstream, observe |
| Counterfactual | Env-specific | Compare pod WITH vs WITHOUT condition |

### 7. Document and prevent

```markdown
## RCA Summary
- **Root cause**: [technical cause]
- **Systemic cause**: [process gap that allowed it]
- **Evidence**: [3 signals that proved it]
- **Prevention**: [alert / test / guardrail to add]
```

## Decision tree

```
SYMPTOM DETECTED
│
├─ Is there a deploy in the last 30 min?
│  ├─ YES → Does error timing match deploy timing (±2min)?
│  │         ├─ YES → Rollback. Confirm recovery. RCA = deploy regression.
│  │         └─ NO  → Deploy is coincidental. Continue below.
│  └─ NO → Continue below.
│
├─ Is the error on ONE service or MANY?
│  ├─ MANY → Shared dependency failing?
│  │         ├─ Check DB/Redis/Queue health metrics
│  │         ├─ Check DNS (CoreDNS query failures)
│  │         └─ Check node-level issues (kubectl get nodes)
│  └─ ONE → Continue below.
│
├─ Is the pod crashing (CrashLoopBackOff)?
│  ├─ YES → What is the termination reason?
│  │         ├─ OOMKilled → Memory leak or limit too low
│  │         ├─ Error (exit 1) → App crash, check logs --previous
│  │         └─ Liveness probe failed → Probe too aggressive or deadlock
│  └─ NO → Pod running but returning errors. Continue below.
│
├─ Is latency elevated OR just errors?
│  ├─ LATENCY + ERRORS → Upstream dependency slow (check traces)
│  ├─ ERRORS ONLY → Logic bug or bad config (check logs for stack trace)
│  └─ LATENCY ONLY → Resource contention (CPU throttle, GC pressure, connection pool)
│
└─ None of the above? → "Nothing changed" pattern:
   ├─ Certificate expiry? (check cert-manager)
   ├─ Secret rotation failed? (check ExternalSecret status)
   ├─ AWS service degradation? (check status page)
   ├─ Spot interruption / Karpenter rotation? (check node events)
   └─ DNS TTL expired + endpoint moved? (check CoreDNS logs)
```

## Cross-signal correlation matrix

| Problem | Metric to check | Log to grep | Trace signal | K8s event |
|---------|----------------|-------------|--------------|-----------|
| Memory leak | `container_memory_working_set_bytes` rising linearly | OOMKill | Rising latency (GC) | `OOMKilling` |
| Connection leak | `http_client_open_connections` rising | "pool exhausted" | Timeout on DB span | — |
| DNS failure | `http_client_request_duration` spike | "lookup: i/o timeout" | Gap between spans | — |
| Cert expiry | — | "x509: certificate has expired" | TLS handshake error | — |
| CPU throttle | `container_cpu_cfs_throttled_periods_total` | — | All spans slow | — |
| Cascading | Multiple `error_rate` up | Circuit breaker open | Cross-service errors | — |
| Disk full | `kubelet_volume_stats_available_bytes` = 0 | "no space left" | Write failures | `EvictionThresholdMet` |

## Common failure patterns

### Deploy → Crash
```bash
kubectl logs -n NS -l app.kubernetes.io/name=SVC --previous --tail=50 --context CLUSTER
```

### Cascading failure
Find which service failed FIRST:
```promql
# Which service had the earliest error spike?
topk(5, rate(http_server_request_duration_seconds_count{http_status_code=~"5.."}[5m]) > 0)
```

### Slow degradation (hours/days)
```promql
# Memory growing linearly?
deriv(container_memory_working_set_bytes{namespace="NS", pod=~"SVC.*"}[1h]) > 0
```

### Intermittent failures
```bash
# Is it node-specific?
kubectl get pods -n NS -l app.kubernetes.io/name=SVC -o wide --context CLUSTER
# Compare error rate by pod (not just aggregate)
```

### "Nothing changed"
```bash
# Check cert expiry
kubectl get certificates -n NS --context CLUSTER -o custom-columns='NAME:.metadata.name,READY:.status.conditions[0].status,EXPIRY:.status.notAfter'

# Check ExternalSecret sync
kubectl get externalsecrets -n NS --context CLUSTER -o custom-columns='NAME:.metadata.name,READY:.status.conditions[0].status,LAST_SYNC:.status.refreshTime'

# Check Karpenter node churn
kubectl get events --field-selector reason=DisruptionBlocked -A --context CLUSTER
```

## Anti-patterns

- ❌ **Declaring RCA with 1 signal** — correlation ≠ causation. Need ≥3.
- ❌ **"Root cause = human error"** — always dig to the systemic process gap.
- ❌ **Skipping the timeline** — without timestamps you can't prove causality.
- ❌ **Investigating cause-by-cause sequentially** — form hypotheses in parallel, test fastest first.
- ❌ **Ignoring counter-evidence** — if one signal refutes your hypothesis, the hypothesis is wrong.
- ❌ **Conflating correlation with causation** — deploy at 14:02 + error at 14:15 is 13 min gap = probably NOT related.
- ❌ **"It fixed itself"** — always find WHY it recovered (TTL expired? pod restarted? Karpenter rotated?).
- ❌ **No prevention step** — finding root cause without proposing a guardrail means it WILL recur.

## Related skills

- `incident-triage` — severity classification before RCA
- `incident-response-runbook` — response process during active incident
- `post-mortem-templates` — documenting RCA after resolution
- `alerting-strategy` — designing alerts that detect symptoms early
- `metric-correlation-analysis` — automated multi-metric correlation
- `deploy-correlation-checker` — automated deploy ↔ anomaly matching
