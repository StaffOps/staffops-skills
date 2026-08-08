---
name: symptom-router
description: "ENTRY POINT — load FIRST when any symptom is reported: \"API is slow\", \"high latency\", \"logs missing\", \"traces missing\", \"metrics missing\", \"gaps in dashboard\", \"pods Pending\", \"OOMKilled\", \"cost spiked\", \"deploy stuck\", \"consumer lag\", \"503 errors\", \"secret not syncing\", \"alert not firing\", \"memory leak\", \"autoscaling not working\", \"dashboard no data\", \"certificate expired\", \"cardinality explosion\", \"SLO burn rate\", \"Redis errors\", \"database slow\", \"client says no data\", \"error rate\", \"dataset slow\", \"webhooks stopped\", \"batch job stuck\", \"load spike\", \"partner errors\", \"unfamiliar service name\", \"who owns this\". Routes to the exact skill(s) to load with first query. Cross-signal correlation and signal precedence (application counters > resources > pod phase)."
---

# Symptom Router — Correlation Layer

Load this skill when: a problem is reported, an alert fires, or something "looks wrong" — and you do not yet know which specialist skill to open.

This skill answers three questions:
1. **Which skill do I load first?** (routing table)
2. **Which signals should I check together?** (cross-signal correlation)
3. **When two signals disagree, which one wins?** (signal precedence)

Full matrices are in `references/` to keep this file navigable.

---

## 1. Symptom → Skill Routing Table (quick reference)

Load the **First skill** immediately. Load **Then** only if the first does not resolve.

| # | Symptom (human words) | First skill to load | Then | Why this order |
|---|----------------------|---------------------|------|----------------|
| 1 | API is slow / high latency | `apm-metrics-cross-runtime` | `tempo-trace-investigation` | Latency metrics narrow the layer; traces pinpoint the span |
| 2 | Logs missing in Grafana | `collector-internal-metrics` | `loki-tempo-self-metrics` | Pipeline loss is most common; backend rejection is second |
| 3 | Traces missing in Tempo | `otel-pipeline-troubleshooting` | `loki-tempo-self-metrics` | Pipeline drops before Tempo rejects |
| 4 | Metrics missing / gaps in dashboards | `victoriametrics-self-metrics` | `collector-internal-metrics` | Check backend health (ingestion gaps), then pipeline |
| 5 | Pods stuck Pending | `eks-node-troubleshooting` | `karpenter-metrics` | Scheduling constraints first; provisioner failures second |
| 6 | Certificate expired / TLS error | `cert-manager-metrics` | `external-secrets-aws-sm` | cert-manager lifecycle first; secret sync if cert delivered but not mounted |
| 7 | Cost spiked | `cost-explorer` | `karpenter-metrics` | Tag attribution identifies the blast; Karpenter shows if node churn caused it |
| 8 | Deploy did not roll out | `argocd-metrics` | `gitops-environments` | Sync/reconcile failure first; repo topology if app not registered |
| 9 | Consumer lag growing (Kafka) | `kafka-pipeline-health` | `strimzi-kafka-metrics` | Pipeline lag first; broker saturation if partitions themselves are slow |
| 10 | Service returning 503 | `istio-ambient-metrics` | `k8s-workload-metrics` | Mesh response flags reveal the layer; pod health confirms origin |
| 11 | OOMKilled | `k8s-workload-metrics` | `dotnet-apm-metrics` or `python-apm-metrics` or `go-apm-metrics` | Confirm OOM via kube_*, then runtime metrics reveal the leak source |
| 12 | Secret not syncing | `external-secrets-aws-sm` | `iam-patterns` | ESO status first; IRSA AccessDenied if SecretStore auth fails |
| 13 | Alert never fired (should have) | `vmalert-configuration` | `alerting-strategy` | Rule evaluation issues first; routing/silence if rule evaluates correctly |
| 14 | Alert fires constantly (false positive) | `alerting-strategy` | `vmalert-configuration` | Threshold/routing design first; evalDelay/queryStep if alert logic is correct |
| 15 | .NET service memory leak | `dotnet-apm-metrics` | `k8s-workload-metrics` | Runtime GC/heap metrics first; container limits if runtime looks healthy |
| 16 | Python service slow | `python-apm-metrics` | `tempo-trace-investigation` | CPython GC + DB pool metrics first; traces for dependency pinpointing |
| 17 | Go goroutine leak | `go-apm-metrics` | `k8s-workload-metrics` | go_goroutines + scheduler latency first; resource exhaustion second |
| 18 | Autoscaling not working (KEDA) | `keda-metrics` | `karpenter-metrics` | Scaler errors/HPA mismatch first; node capacity if pods scale but can't schedule |
| 19 | Grafana dashboard returns no data | `observability-tooling` | `victoriametrics-self-metrics` | Datasource/query routing first; backend health if datasource is reachable |
| 20 | Service mesh errors (400/gRPC) | `istio-ambient-debugging` | `istio-ambient-metrics` | Ambient gotchas (hostname, SNAT) first; traffic metrics for magnitude |
| 21 | Redis connection errors from app | `backing-services-metrics` | `apm-metrics-cross-runtime` | Backend saturation first; app-side pool config if Redis is healthy |
| 22 | Database slow queries | `backing-services-metrics` | `tempo-trace-investigation` | PG metrics + connections first; traces show which app path triggers |
| 23 | Cardinality explosion (VM OOM) | `vm-cardinality-management` | `streaming-aggregation` | Identify offender first; then route to remediation pattern |
| 24 | Node not consolidating (cost waste) | `karpenter-consolidation` | `karpenter-metrics` | Disruption blockers first; provisioner state if policy is correct |
| 25 | SLO burn rate alert | `error-budget-framework` | `incident-triage` | Budget math first; incident response if budget exhausted |

### Client and product symptoms

These arrive in product language rather than infrastructure language. **The generic RED method does not work on Plataforma** — it answers HTTP 200 with a negative status in the body, so a 5xx error query reports 0% no matter how broken it is. Route these to the business-metric path instead.

| # | Symptom (human words) | First skill to load | Then | Why this order |
|---|----------------------|---------------------|------|----------------|
| 40 | Who owns this? / who do I escalate to? | `product-escalation-map` | — | Routes on the failing component, not the alerting service |
| 41 | Is the API actually down for clients? / external validation | `kuma-synthetic-status` | `incident-triage` | Kuma tests from OUTSIDE — ground truth when internal metrics disagree with client reports |
| 42 | Endpoint latency from client perspective / SLA compliance | `kuma-synthetic-status` | `sla-slo-design` | monitor_response_time and monitor_uptime_ratio answer "how do clients experience it?" |

Full table with 40+ rows: see `references/routing-table-full.md`.

---

## 2. Cross-Signal Correlation Matrix (top 10 symptom classes)

| Symptom class | Metric to check | Log to check | Trace to check | K8s event to check | Agreement proves | Disagreement means |
|---------------|----------------|--------------|----------------|-------------------|-----------------|-------------------|
| Data loss (logs/traces/metrics) | `otelcol_exporter_enqueue_failed_*`, `otelcol_exporter_send_failed_*` | Collector logs: "dropping data" | N/A (data never arrived) | Pod restarts on collector | All point to pipeline → confirmed pipeline loss | Metrics show no drop but data absent → backend is rejecting (load `loki-tempo-self-metrics`) |
| High latency | `http_server_request_duration_seconds` P99 | App logs: timeout messages | Trace waterfall: which span is slow | None expected | Metric + trace agree on same span → root cause in that dependency | Metric shows latency but trace is fast → metric aggregation includes queuing outside request lifecycle |
| OOMKilled pods | `container_memory_working_set_bytes` near limit | dmesg: "Out of memory: Killed" | N/A | `Killing` event with reason OOMKilled | Memory + event agree → real OOM, investigate leak | Memory was NOT near limit but OOMKilled → container limit was LOWER than node available; check resource limits |
| Pods Pending | `karpenter_pods_startup_duration_seconds` | Karpenter logs: "Could not schedule" | N/A | `FailedScheduling` event | Event message names the constraint → follow it | Karpenter provisioned node but pod STILL Pending → topology/affinity blocking, not capacity |
| 503 errors | `istio_requests_total{response_code="503"}` | Upstream logs: connection reset | Trace: span with 503 status | `Unhealthy` or `BackOff` events | Istio flag UH + pod unhealthy → pod is the origin | Istio shows 503 but pods are Ready → mesh routing misconfigured or circuit breaker tripped (UO flag) |
| Deploy stuck | `argocd_app_sync_total{phase="Error"}` | ArgoCD logs: "ComparisonError" | N/A | Rollout events: ProgressDeadlineExceeded | Sync error + event → manifests invalid or cluster unreachable | ArgoCD shows Synced but pods not updated → image pull failure or webhook blocking admission |
| Alert not firing | `ALERTS{alertname="X"}` absent | VMAlert logs: no evaluation error | N/A | N/A | Rule exists, evaluates, no match → threshold too high or metric renamed | Rule exists but "result is NaN" in logs → metric absent (label change or scrape broken) |
| Cost spike | `node_total_hourly_cost` delta | N/A | N/A | Node scaling events | Cost tags match new nodes → Karpenter launched expensive instances | Cost tags don't match any k8s resource → non-EKS AWS resource (check CUR) |
| Consumer lag | `kafka_consumergroup_lag` | Process collector logs: rebalancing | Trace: processing duration per message | Consumer pod restarts | Lag + processing time → consumer too slow | Lag growing but consumer idle → partition reassignment loop (check `strimzi-kafka-metrics`) |
| Secret sync failure | `externalsecrets_status_condition{status="False"}` | ESO logs: "AccessDeniedException" | N/A | ExternalSecret events: SyncError | ESO error + AccessDenied → IRSA misconfigured (load `iam-patterns`) | ESO shows synced but pod still has old value → pod not restarted (Reloader not triggering) |

---

## 3. Signal Precedence Rules

When signals conflict, follow these precedence rules (highest priority first):

### Rule 1: Application counters > Resource metrics

**Application-level counters** (enqueue_failed, send_failed, refused, discarded, dropped) **always beat** resource metrics (CPU, memory) for establishing data loss.

Resource metrics explain a loss already measured; they NEVER establish health.

> CPU=0.6/1.0, Memory=1.6/2.0, pod=Running → "healthy"? NO.
> `otelcol_exporter_send_failed_log_records` = 2840/sec → 12% data loss.
> Resources lied. Application counter told the truth.
> (Historical note: this incident originally manifested as `otelcol_exporter_enqueue_failed_log_records` before the queue was disabled on the log exporter. Today, `send_failed_log_records` is the detection signal.)

### Rule 2: Pod phase proves nothing

`phase=Running` is necessary but NOT sufficient for health. Decide based on:
- `kube_pod_container_status_restarts_total` (climbing = crashing)
- `kube_pod_container_status_last_terminated_reason` = OOMKilled
- Application-level drop/error counters

A pod can be `Running` while actively OOMKilling every 4 minutes.

### Rule 3: Alerts are symptoms, not causes

An alert firing is evidence that a threshold was breached — it may be a downstream effect.
- `HighErrorRate` fired → the ERROR is the symptom, not the cause
- Look for what CAUSED the errors (deploy? dependency? capacity?)
- Never treat the alert name as the diagnosis

### Rule 4: Absence of errors ≠ health

Logs showing no errors does NOT prove a system is healthy. The failure mode may be:
- Silent drops (data lost before logging)
- Pre-log rejection (receiver refused before handler)
- Sampled away (log sampling hid the evidence)

Always check application-level counters ALONGSIDE logs.

### Rule 5: Temporal correlation ≠ causation

Two events happening at the same time proves correlation only. To claim causation:
- Identify a **mechanism** (how A causes B)
- Show **directionality** (A always before B, never B before A)
- Validate with **counterfactual** (remove A → B disappears)

---

## 4. Worked Examples

### Example A — The Silent Log Loss

**Symptom**: "Some logs are missing in Grafana for service X."

**Investigation sequence**:

```
Step 1: Check OTel gateway resource health (the naive path)
  Query: container_cpu_usage_seconds_total{pod=~"otel-gateway.*"}
  Result: 0.6 cores used of 1.0 limit → 60% utilization
  Query: container_memory_working_set_bytes{pod=~"otel-gateway.*"}
  Result: 1.6Gi of 2.0Gi limit → 80% utilization
  
  TRAP: Both look fine. Naive conclusion: "no issue found."

Step 2: Check application-level counters (the correct path)
  Query: rate(otelcol_exporter_send_failed_log_records[5m])
  # (Historically: otelcol_exporter_enqueue_failed_log_records — no longer emitted after queue disable)
  Result: 2840/sec

  Query: rate(otelcol_receiver_accepted_log_records[5m])
  Result: ~23,000/sec

  2840 / 23000 = 12.3% of all logs SILENTLY DROPPED.

Step 3: Confirm mechanism
  Query: otelcol_exporter_queue_size / otelcol_exporter_queue_capacity
  Result: 1.0 (queue full — exports can't keep up)
  
  Root cause: exporter queue saturated. Logs accepted by receiver but dropped
  when queue is full — memory_limiter never triggers because memory is at 80%.

Step 4: Fix direction
  - Increase queue_size OR
  - Add more gateway replicas (horizontal scale) OR
  - Reduce inbound rate (tail sampling earlier)
```

**Generalizable rule**: Resource metrics (CPU/memory) are LAGGING indicators of CAPACITY, not leading indicators of DATA HEALTH. Always start with application-level loss counters.

---

### Example B — The Replica Ceiling That Was Not a Ceiling

**Symptom**: "We raised maxReplicas to 8 but it never scales beyond 5."

**Investigation sequence**:

```
Step 1: Check HPA/KEDA state
  kubectl get hpa <name>
  TARGETS: 85%/70%  MINPODS: 2  MAXPODS: 8  REPLICAS: 5
  
  HPA WANTS to scale (target exceeded) but REPLICAS stuck at 5.

Step 2: Check for Pending pods
  kubectl get pods -l app=<name> | grep Pending
  Result: 3 pods in Pending state

Step 3: Read the scheduling failure
  kubectl describe pod <pending-pod>
  Events:
    Warning FailedScheduling: 0/15 nodes are available:
    5 node(s) didn't match pod anti-affinity rules,
    10 node(s) didn't match pod topology spread constraints.
    
  Message: "unsatisfiable topology constraint for pod anti-affinity"

Step 4: Check the anti-affinity rule
  kubectl get deployment <name> -o jsonpath='{.spec.template.spec.affinity}'
  Result: podAntiAffinity.requiredDuringSchedulingIgnoredDuringExecution
          topologyKey: topology.kubernetes.io/zone

Step 5: Count AZs
  kubectl get nodes -o jsonpath='{.items[*].metadata.labels.topology\.kubernetes\.io/zone}' | tr ' ' '\n' | sort -u | wc -l
  Result: 5

  Root cause: required anti-affinity by zone + 5 AZs = ceiling of 5 replicas.
  maxReplicas=8 is a no-op — scheduler will NEVER place the 6th pod.

Step 6: Fix direction
  Replace `requiredDuringScheduling` with `preferredDuringScheduling`
  + add topologySpreadConstraints with maxSkew=1 for balanced distribution.
```

**Generalizable rule**: Before raising maxReplicas, check if scheduling constraints (anti-affinity `required` + topology key cardinality) impose a LOWER ceiling. `maxReplicas` only works if the scheduler can PLACE the pods.

---

### Example C — The False-Healthy Backend

**Symptom**: "Pod shows Running but service is intermittently failing."

**Investigation sequence**:

```
Step 1: Check pod phase (the naive check)
  kubectl get pod <name>
  STATUS: Running    READY: 1/1
  
  TRAP: Looks healthy. Naive conclusion: "pod is fine."

Step 2: Check restart count
  kubectl get pod <name> -o jsonpath='{.status.containerStatuses[0].restartCount}'
  Result: 47

  47 restarts! Pod is Running RIGHT NOW but has been crash-looping.

Step 3: Check termination reason
  kubectl get pod <name> -o jsonpath='{.status.containerStatuses[0].lastState.terminated.reason}'
  Result: OOMKilled

  kubectl get pod <name> -o jsonpath='{.status.containerStatuses[0].lastState.terminated.finishedAt}'
  Result: 2 minutes ago

Step 4: Confirm with metrics
  Query: kube_pod_container_status_restarts_total{pod="<name>"}
  Result: 47 (monotonically increasing by ~1 every 4 minutes)

  Query: container_memory_working_set_bytes{pod="<name>"} / container_spec_memory_limit_bytes{pod="<name>"}
  Result: oscillates between 0.3 and 1.0 (hits limit → killed → restarts fresh)

  Root cause: Memory leak. Pod runs for ~4 minutes, hits limit, OOMKilled,
  restarts (counts as Running again immediately), repeat.

Step 5: Fix direction
  - Runtime investigation (load language-specific APM skill for heap analysis)
  - Short-term: raise memory limit to extend cycle (buys time, not a fix)
  - Long-term: find and fix the leak
```

**Generalizable rule**: `phase=Running` with `restartCount > 0` and `lastState.terminated.reason=OOMKilled` means the pod is CRASH-LOOPING, not healthy. Never trust phase alone — always check restartCount and lastState.

---

## 5. Investigation Entry Procedure (first 60 seconds)

```
1. CLASSIFY the symptom
   → Match to routing table (Section 1)
   → If no match: use incident-triage for severity classification

2. LOOK UP the route
   → Load the FIRST skill from the routing table
   → Note the THEN skill (load only if first doesn't resolve)

3. BOUND the time window
   → When did it start? (exact timestamp from alert/report)
   → Default window: [start - 15min, now] (captures cause before symptom)
   → Cheapest queries first (instant > range; metadata > full scan)

4. RUN the first query
   → Use observability-tooling to select the correct MCP tool
   → Run the diagnostic query from the loaded skill
   → Reference investigation-cost-guardrail for query budget discipline

5. BRANCH based on result
   → Signal confirms hypothesis → deepen in same skill
   → Signal refutes hypothesis → load the THEN skill
   → Signal is ambiguous → cross-correlate (Section 2 matrix)
   → No signal at all → check if pipeline itself is broken (collector-internal-metrics)
```

---

## 6. Expected Output Format

After routing completes, the agent should produce:

```
ROUTE CHOSEN: <symptom matched> → <first skill loaded>
SKILLS LOADED (in order): [skill-1, skill-2, ...]
FIRST QUERY RUN: <exact PromQL/LogQL/TraceQL expression>
TIME WINDOW: [T-start, T-end]
RESULT: <value observed>
NEXT ACTION: <deepen | pivot to THEN skill | cross-correlate | escalate>
```

---

## References

- `references/routing-table-full.md` — expanded routing table with 40+ symptoms
- `references/correlation-matrix-full.md` — full cross-signal matrix for all symptom classes
- `references/signal-precedence-examples.md` — additional precedence rule examples

## When NOT to use

- **Known root cause** — if you already know what's wrong, go directly to the fix skill.
- **Non-technical symptoms** (user complaints, business metrics) — this routes technical signals.
- **Deep RCA** once routed — see [root-cause-analysis](../sre/root-cause-analysis/SKILL.md) after initial routing.

## Decision tree

```
What symptom category?
├── Latency (slow responses, high p99)?
│   └── Load apm-metrics-cross-runtime → then tempo-trace-investigation
├── Errors (5xx, exceptions, failed requests)?
│   └── Load apm-metrics-cross-runtime → filter by status_code >= 500
├── Saturation (CPU/mem/queue full, OOM)?
│   └── Load k8s-workload-metrics → then karpenter-metrics if node-level
├── Traffic (unexpected volume, zero requests)?
│   └── Load istio-ambient-metrics → check ingress + service mesh
└── Data loss (logs/traces/metrics missing)?
    ├── Logs missing → collector-internal-metrics → loki-tempo-self-metrics
    ├── Traces missing → otel-pipeline-troubleshooting
    └── Metrics missing → victoriametrics-self-metrics → collector-internal-metrics
```

## Related skills

- [incident-triage-linux](../troubleshooting/incident-triage-linux/SKILL.md) — triage procedure once routed to a Linux issue.
- [root-cause-analysis](../sre/root-cause-analysis/SKILL.md) — deep analysis after symptom routing.
- [incident-response-runbook](../sre/incident-response-runbook/SKILL.md) — executing response after routing.
- [alerting-strategy](../sre/alerting-strategy/SKILL.md) — alerts that feed into the symptom router.
- [linux-troubleshooting-methodology](../troubleshooting/linux-troubleshooting-methodology/SKILL.md) — systematic approach after routing.
