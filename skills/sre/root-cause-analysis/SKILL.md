---
name: root-cause-analysis
description: "Correlate signals to prove root cause."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [root, cause, analysis, sre]
    category: sre
    related_skills: []
---
# Root Cause Analysis

Techniques and patterns for investigating incidents in cloud-native distributed systems.

---

## When to Use

Use when investigating production incidents, diagnosing failures, or performing RCA. Covers 5 Whys, fault tree, cross-signal correlation, timeline construction, empirical validation, and common failure patterns in K8s/cloud-native systems.

## RCA Techniques

### 5 Whys (adapted for distributed systems)

```
Symptom: Service X returns 500
  Why 1: Pod X is crashlooping
  Why 2: OOMKilled (excedeu memory limit)
  Why 3: Heap grows without bound after deploy Y
  Why 4: Deploy Y introduziu cache sem eviction
  Why 5: PR review missed the missing cache TTL → PROCESS GAP
  
Root Cause: Cache without an eviction policy (technical)
Systemic Cause: Review checklist omits "cache memory behavior" (process)
```

Always look for the **systemic cause** beyond the technical one — what would prevent recurrence.

### Fault Tree Analysis

```
                    [Service Down]
                   /              \
          [Pod crash]          [Network issue]
          /        \                  |
    [OOMKill]  [Liveness fail]  [DNS timeout]
        |           |                 |
  [Memory leak] [Deadlock]     [CoreDNS overload]
        |           |                 |
  [Cache no TTL] [Lock ordering]  [ndots:5 + large cluster]
```

Useful when a symptom can have multiple causes. Work each branch until it is confirmed or eliminated.

### Elimination Method

```
Possible causes: [A, B, C, D, E]

Test 1: If A were the cause we would see X. Is X present? → NO → eliminate A
Test 2: If B were the cause we would see Y. Is Y present? → YES → B is a candidate
Test 3: If C were the cause we would see Z. Is Z present? → NO → eliminate C
Test 4: If D were the cause we would see W. Is W present? → YES → D is a candidate
Test 5: Can B and D coexist? → NO → one refutes the other → decisive test

Result: B confirmed, D refuted by test 5
```

---

## Cross-Signal Correlation

### Signal matrix for common problems

| Problem | Metric | Log | Trace | Event | Deploy |
|----------|---------|-----|-------|-------|--------|
| Memory leak | `container_memory_working_set_bytes` rising | OOMKill | Rising latency (GC) | Pod restart | Yes (introduced the leak) |
| Connection leak | Connections open crescente, pool exhausted | "connection pool exhausted" | Timeout no DB call | — | Sim (mudou pool config) |
| DNS issue | Request duration spike | "lookup: i/o timeout" | Gaps between spans | — | No (infra) |
| Certificate expiry | — | "x509: certificate has expired" | TLS handshake fail | — | No (cert rotation) |
| Resource starvation | CPU throttle, pending pods | — | — | FailedScheduling | Scaling event |
| Cascading failure | Multiple services error_rate up | Circuit breaker open | Cross-service error propagation | — | Single service deploy |

### Validation pattern: 3 signals agree

```
VALID (3 signals agree):
  Metric: error_rate up at 14:03 ✅
  Log: first error at 14:03:12 ✅  
  Deploy: rollout finished at 14:02:58 ✅
  → Strong causal correlation

INVALID (signals disagree):
  Metric: error_rate up at 14:03
  Log: first error at 13:45 (18 min EARLIER!)
  Deploy: none in the window
  → Deploy correlation REFUTED — look for another cause
```

---

## Timeline Construction

### Sources for building the timeline

| Fonte | Comando/Query | Granularidade |
|-------|---------------|---------------|
| K8s events | `kubectl get events --sort-by=.lastTimestamp` | segundo |
| Pod restarts | `kubectl get pods -o json \| jq '.items[].status.containerStatuses[].restartCount'` | — |
| ArgoCD syncs | ArgoCD UI / `argocd app history <app>` | minuto |
| Alertmanager | `/api/v2/alerts?active=true` | segundo |
| VictoriaMetrics | `changes(metric[5m])` to detect step changes | 15s-1min |
| Loki | `{namespace="X"} \| level="error" \| first_over_time` | segundo |
| Git | `git log --since="2h ago" --oneline` | commit |

### Formato de timeline

```
[2026-06-01 14:00:00] BASELINE: all metrics normal
[2026-06-01 14:02:58] CHANGE: ArgoCD sync completed (app=service-x, image=v1.2.3→v1.2.4)
[2026-06-01 14:03:05] SIGNAL: first error log "connection refused" (pod service-x-abc)
[2026-06-01 14:03:12] SIGNAL: error_rate metric crosses threshold (0.1% → 12%)
[2026-06-01 14:03:30] SIGNAL: trace shows timeout on redis call (span_id=xyz)
[2026-06-01 14:04:00] ALERT: ErrorBudgetBurn fired (service=service-x)
[2026-06-01 14:05:00] ALERT: PodCrashLooping fired
[2026-06-01 14:10:00] ACTION: rollback initiated
[2026-06-01 14:11:30] RESOLVED: error_rate back to baseline after rollback
```

---

## Failure Patterns em K8s/Cloud-Native

### Pattern 1: Deploy → Crash

```
Signal: CrashLoopBackOff after deploy
Investigate: OOMKill? Liveness fail? Startup crash?
  - OOM → verificar memory requests/limits vs uso real
  - Liveness → verificar timeout, path, startup delay
  - Crash → verificar logs do container (Previous: kubectl logs --previous)
```

### Pattern 2: Cascading failure

```
Signal: Multiple services failing simultaneously
Investigate: Which failed FIRST? (timeline)
  - Upstream dependency (DB, cache, queue) degradou
  - Circuit breakers not configured → thundering herd
  - Shared resource (node, network) saturou
```

### Pattern 3: Slow degradation

```
Signal: Latency grows linearly over hours/days
Investigate: Memory? Connections? Queue depth?
  - Memory leak (no GC or cache without eviction)
  - Connection pool leak (opened connections never returned)
  - Queue backlog crescendo (consumer < producer rate)
```

### Pattern 4: Intermittent failures

```
Signal: Sporadic, non-consistent errors
Investigate: Scheduling? DNS? Certs? Specific nodes?
  - Problems on specific nodes (hardware, network)
  - DNS resolution flapping (CoreDNS saturation)
  - Certificate renewal window (valid on some pods, expired on others)
  - Race conditions (timing-dependent, hard to reproduce)
```

### Pattern 5: "Nothing changed" failures

```
Signal: Failure with no deploy or visible change
Investigate: What changed that is NOT a deploy?
  - Certificate expiry (automated rotation failed)
  - Secret rotation (External Secrets sync delay)
  - AWS service degradation (verify status page + CloudWatch)
  - Karpenter node rotation (new node, different config)
  - Spot interruption
  - DNS TTL expired + endpoint moved
  - Dependency SLA change (upstream rate limit hit)
```

---

## Empirical Validation

### Confirmation tests

| Type | How | When to use |
|------|------|-------------|
| **Rollback** | Revert the deploy, observe recovery | Deploy-related issues |
| **Reproduction** | Deliberately trigger the same condition | Logic bugs, race conditions |
| **Isolamento** | Desconectar componente suspeito, observar | Cascading failures |
| **Canary** | Apply the fix to 1 pod, compare with the rest | Validate the fix without blast radius |
| **Counterfactual** | Compare pod/node WITH and WITHOUT the condition | Environment-specific issues |

### Checklist before declaring it "resolved"

- [ ] Did the symptom stop? (not merely decrease)
- [ ] Did metrics return to baseline?
- [ ] Nenhum alerta ativo relacionado?
- [ ] Does the fix make causal sense? (not coincidence)
- [ ] Monitored for an adequate period (>=15min for intermittent issues)?
- [ ] Prevention proposed? (alert, test, guardrail)
- [ ] Investigation documented? (timeline + evidence + conclusion)
