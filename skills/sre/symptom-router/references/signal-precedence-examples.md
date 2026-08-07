# Signal Precedence — Extended Examples

Concrete examples of each precedence rule applied in practice.

---

## Rule 1: Application counters > Resource metrics

### Example: VictoriaMetrics vmagent healthy on resources but losing data

```
Resource check:
  container_cpu_usage_seconds_total{pod=~"vmagent.*"} → 0.3 cores of 1.0 → 30%
  container_memory_working_set_bytes{pod=~"vmagent.*"} → 800Mi of 2Gi → 40%
  Conclusion (WRONG): "vmagent is healthy, plenty of headroom."

Application counter check:
  vmagent_remotewrite_requests_total{status_code="503"} → 45/min
  vmagent_remotewrite_pending_data_bytes → 2.1GB and growing
  Conclusion (CORRECT): vminsert is rejecting writes (503), vmagent is buffering
  to disk (pending_data_bytes growing). Data will be lost when buffer fills.
```

**Lesson**: Resources show vmagent itself is fine (it IS fine — it's buffering efficiently). The data loss is DOWNSTREAM at vminsert. Only the application counter reveals the problem.

---

### Example: KEDA-scaled consumer "healthy" but not consuming

```
Resource check:
  container_cpu_usage_seconds_total{pod=~"process-collector.*"} → 0.05 cores → 5%
  Conclusion (WRONG): "Consumer is idle because there's nothing to process."

Application counter check:
  kafka_consumergroup_lag{group="otel-process-consumer"} → 500,000 messages
  otelcol_receiver_accepted_log_records{instance=~"process.*"} → 0/sec
  Conclusion (CORRECT): Consumer is NOT consuming despite massive lag.
  Low CPU is BECAUSE it's stuck, not because there's no work.
```

**Lesson**: Low resource usage can mean "idle because broken" not "idle because done."

---

## Rule 2: Pod phase proves nothing

### Example: Sidecar healthy, main container crashing

```
Pod status:
  kubectl get pod app-xyz-5f8d7 → STATUS: Running, READY: 2/2

Deeper check:
  kubectl get pod app-xyz-5f8d7 -o json | jq '.status.containerStatuses[] | {name, restartCount, ready}'
  → {name: "app", restartCount: 12, ready: true}
  → {name: "istio-proxy", restartCount: 0, ready: true}

  The pod shows Running/Ready because the container restarts fast enough
  that the readiness probe passes between crashes. restartCount=12 in 1 hour
  means it's crashing every 5 minutes.
```

**Lesson**: A multi-container pod is Ready when ALL containers pass readiness. If a container crashes and restarts within the probe period, it shows Ready briefly. Only restartCount reveals the pattern.

---

### Example: Init container succeeded, app hanging

```
Pod status:
  kubectl get pod migration-job → STATUS: Running, READY: 0/1
  (Running but NOT Ready — often dismissed as "still starting up")

Deeper check:
  kubectl get pod migration-job -o jsonpath='{.status.containerStatuses[0].state}'
  → {"running":{"startedAt":"2026-08-01T10:00:00Z"}}
  
  Started 4 hours ago and still not Ready. NOT "starting up" — it's HUNG.
  
  kubectl logs migration-job → last line: "Waiting for lock on table X..."
  → Database lock contention. Will never become Ready without intervention.
```

**Lesson**: `Running` + `Ready: 0/1` for extended duration is NOT "starting" — it's stuck. Check how long it's been Running and look for blocking conditions in logs.

---

## Rule 3: Alerts are symptoms, not causes

### Example: HighErrorRate alert leads to dependency, not service

```
Alert: HighErrorRate on service-A (error_ratio > 5%)

Naive investigation:
  "service-A has high errors → something wrong WITH service-A"

Correct investigation:
  rate(http_server_request_duration_seconds_count{service="service-A", status_code=~"5.."}[5m])
  → errors are all on endpoint /api/orders

  TraceQL: {resource.service.name = "service-A" && status = error && span.http.target = "/api/orders"}
  → all error traces show: service-A → service-B → timeout

  rate(http_server_request_duration_seconds_count{service="service-B", status_code=~"5.."}[5m])
  → service-B itself returning 503 (its Redis is down)

  Root cause: Redis backing service-B is OOMKilling. Cascading to service-A via dependency.
  The alert on service-A was CORRECT (symptom) but the CAUSE is in service-B's Redis.
```

**Lesson**: Follow the error UPSTREAM through traces. The alerting service is where the symptom is OBSERVED, not where the cause LIVES.

---

## Rule 4: Absence of errors ≠ health

### Example: No errors in logs but 12% data loss

```
Log check:
  LogQL: {service_workload="otel-gateway"} |= "error" | count_over_time([5m])
  → 0 error log lines

  Conclusion (WRONG): "No errors in logs → gateway is fine."

Application counter check:
  otelcol_exporter_send_failed_log_records → 2840/sec (historically: enqueue_failed_log_records)
  
  The collector does NOT log when it drops data from a full queue.
  It increments a metric counter silently. Logs cannot detect this failure mode.
```

**Lesson**: Some failure modes are silent-by-design. The system is DESIGNED to drop data without logging (to avoid log storm during overload). Only dedicated counters reveal these.

---

### Example: Sampling hides errors

```
Log check:
  LogQL: {service_workload="payment-api"} |= "exception"
  → 3 exceptions in last hour

  "Only 3 exceptions? That's normal background noise."

Metric check:
  rate(http_server_request_duration_seconds_count{service="payment-api", status_code="500"}[1h])
  → 340 errors/hour

  Discrepancy: 340 metric errors but only 3 log lines.
  Cause: structured logging is rate-limited (1 log per error type per minute).
  Logs UNDERCOUNT the real error volume by 100x.
```

**Lesson**: Metrics count EVERY occurrence. Logs may be sampled, rate-limited, or deduplicated. When investigating error magnitude, trust metric counters over log line counts.

---

## Rule 5: Temporal correlation ≠ causation

### Example: Deploy coincides with but did not cause the outage

```
Timeline:
  14:00 — Deploy of service-X (config change: logging format)
  14:02 — Error rate spikes on service-X

  Naive conclusion: "Deploy caused the error spike."

Deeper investigation:
  - The deploy changed logging format ONLY (no behavioral change)
  - Error traces show timeout calling service-Y
  - service-Y had an OOMKill at 14:01 (independent event)
  - service-Y OOMKill → service-X timeout → error spike

  The deploy was CORRELATED in time but NOT CAUSAL.
  service-Y's OOMKill was the actual cause. The deploy was a red herring.

Validation (counterfactual):
  Rolling back service-X deploy → errors persist (not caused by deploy)
  Restarting service-Y pod → errors resolve (caused by service-Y OOM)
```

**Lesson**: Before blaming a deploy, check if the errors are on paths CHANGED by the deploy. If errors are on an unrelated code path, the deploy is a coincidence. Always validate with rollback or counterfactual.
