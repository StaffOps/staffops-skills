# Cross-Signal Correlation Matrix — Full

For each symptom class, which signals to check SIMULTANEOUSLY and what each contributes.

The **"What disagreement means"** column is the most valuable — it teaches hypothesis refinement.

---

## Telemetry Data Loss

| Signal | What to check | Expected if pipeline is dropping |
|--------|--------------|----------------------------------|
| Metric | `rate(otelcol_exporter_send_failed_log_records[5m])` > 0 | Queue full or backend rejecting → data silently discarded (historically: `enqueue_failed_log_records` before queue disable) |
| Metric | `rate(otelcol_exporter_send_failed_spans[5m])` > 0 | Export target unreachable or rejecting |
| Metric | `otelcol_exporter_queue_size` / `otelcol_exporter_queue_capacity` → 1.0 | Saturated queue confirms bottleneck |
| Log | Collector logs: "sending queue is full" | Confirms enqueue_failed mechanism |
| K8s event | Collector pod restarts | Memory limiter → restart → data in buffer lost |
| **Agreement** | All point to collector pipeline → **confirmed pipeline loss** |
| **Disagreement** | Metrics show zero drops BUT data absent in backend → backend is rejecting: load `loki-tempo-self-metrics` (check `loki_discarded_samples_total` or `tempo_discarded_spans_total`) |

---

## High Latency

| Signal | What to check | Expected if app is slow |
|--------|--------------|-------------------------|
| Metric | `histogram_quantile(0.99, rate(http_server_request_duration_seconds_bucket[5m]))` | P99 elevated above SLO |
| Log | App structured logs: `duration_ms` field on slow requests | Duration matches metric percentile |
| Trace | TraceQL: `{duration > 1s && resource.service.name = "X"}` | Waterfall shows which span is slow |
| K8s event | None expected (latency doesn't cause K8s events) | |
| **Agreement** | Metric P99 matches trace duration, log confirms → same root span → investigate that dependency |
| **Disagreement** | Metric shows P99 = 5s but ALL traces < 500ms → metric includes queuing OUTSIDE request (Kestrel queue, KEDA warm-up). Check `kestrel_queued_requests` or `http_server_active_requests` |

---

## OOMKilled Pods

| Signal | What to check | Expected if memory leak |
|--------|--------------|-------------------------|
| Metric | `container_memory_working_set_bytes` / `container_spec_memory_limit_bytes` | Approaches 1.0 before kill |
| Metric | `kube_pod_container_status_restarts_total` | Monotonically increasing |
| Metric | Language-specific: `dotnet_gc_heap_size_bytes`, `process_runtime_cpython_memory_bytes`, `go_memstats_alloc_bytes` | Growing between GC cycles |
| Log | dmesg/kernel: "Out of memory: Killed process" | Confirms OOM at OS level |
| K8s event | `Killing` event with reason=OOMKilled | Confirms container OOM |
| **Agreement** | Memory approaching limit + restarts climbing + runtime heap growing → confirmed leak |
| **Disagreement** | Memory was at 60% but OOMKilled → container limit was SET LOWER than visible in `top pods` (check `container_spec_memory_limit_bytes` actual value — may differ from requests). OR: a sidecar in the same pod consumed the memory |

---

## Pods Stuck Pending

| Signal | What to check | Expected if capacity issue |
|--------|--------------|----------------------------|
| Metric | `karpenter_pods_startup_duration_seconds` | No new values (pods never start) |
| Metric | `karpenter_cloudprovider_errors_total` | EC2 API errors → can't launch instance |
| Log | Karpenter controller: "Could not schedule pod" | Names the unsatisfied constraint |
| K8s event | `FailedScheduling` on pod | Message contains the specific constraint |
| **Agreement** | FailedScheduling event + Karpenter error + zero startup → capacity unavailable in requested type/zone |
| **Disagreement** | Karpenter launched a new node (nodepool shows new nodeclaim) BUT pod STILL Pending → not a capacity issue; it's topology/affinity blocking (check `requiredDuringScheduling` antiAffinity — zone cap may be reached) |

---

## 503 Errors

| Signal | What to check | Expected if upstream is down |
|--------|--------------|-------------------------------|
| Metric | `istio_requests_total{response_code="503", reporter="destination"}` | Shows which service is returning 503 |
| Metric | `istio_requests_total{response_code="503", response_flags="UH"}` | UH = no healthy upstream |
| Log | Upstream service logs: unhandled exception, crash | Correlates with 503 time |
| Trace | Span with status_code=503, peer info | Shows exact dependency path |
| K8s event | `Unhealthy` (readiness probe failed), `BackOff` (crash loop) | Pod not ready → removed from Service endpoints |
| **Agreement** | UH flag + pod not Ready + crash logs → pod is genuinely unhealthy |
| **Disagreement** | All pods show Ready=True but 503 with flag UO → circuit breaker tripped (outlier detection). Check Istio DestinationRule `outlierDetection` config. OR: flag NR → no route matched (VirtualService misconfigured) |

---

## Deploy Not Rolling Out

| Signal | What to check | Expected if sync failure |
|--------|--------------|--------------------------|
| Metric | `argocd_app_sync_total{phase="Error"}` | Increment at deploy time |
| Metric | `argocd_git_fetch_fail_total` | Git unreachable |
| Log | ArgoCD application-controller: "ComparisonError" or "SyncError" | Specific failure reason |
| K8s event | Rollout: `ProgressDeadlineExceeded` | Rollout timed out waiting for pods |
| **Agreement** | Sync error + git fetch fail → Git/manifest problem |
| **Disagreement** | ArgoCD shows Synced=True, Health=Healthy BUT pods running OLD image → image tag is the same (re-pushed mutable tag). Check image SHA vs running containers. OR: Kyverno webhook rejected the new pod (check `kubectl get events -n <ns> | grep Deny`) |

---

## Alert Not Firing

| Signal | What to check | Expected if rule is broken |
|--------|--------------|----------------------------|
| Metric | `ALERTS{alertname="X"}` | Absent entirely (no evaluation) |
| Metric | `ALERTS_FOR_STATE{alertname="X"}` | Absent (rule never entered firing state) |
| Log | VMAlert: "error evaluating rule" or "result is NaN" | Rule evaluates but returns NaN |
| K8s event | N/A | |
| **Agreement** | NaN in VMAlert log + metric absent → underlying metric disappeared (renamed, scrape broken, label changed) |
| **Disagreement** | Rule evaluates successfully with value (check `/api/v1/query?query=<rule_expr>` returns data) but ALERTS{} absent → `for` duration not reached yet, OR threshold set too high for current values. Reduce threshold or wait for `for` period |

---

## Cost Spike

| Signal | What to check | Expected if node churn |
|--------|--------------|-------------------------|
| Metric | `karpenter_nodes_total` over time | Spike in node count at cost-spike time |
| Metric | `node_total_hourly_cost` (Kubecost) | Per-instance cost identifies expensive types |
| Log | N/A (cost data is not log-based) | |
| K8s event | Node scaling events | New nodes launched, old not terminated |
| **Agreement** | Node count spike + expensive instance type + cost tag attribution → Karpenter launched expensive on-demand (spot unavailable) |
| **Disagreement** | EKS node cost stable BUT total AWS cost spiked → non-K8s resource (NAT Gateway data transfer, S3 requests, RDS scaling). Check CUR in `cost-explorer` skill |

---

## Consumer Lag Growing

| Signal | What to check | Expected if consumer is slow |
|--------|--------------|-------------------------------|
| Metric | `kafka_consumergroup_lag{group="otel-process-consumer"}` | Growing monotonically |
| Metric | Processing time per message (varies by consumer) | Elevated |
| Log | Consumer/process-collector: "rebalancing", "commit failed" | Consumer instability |
| K8s event | Consumer pod restarts | Causes rebalance → lag spike |
| **Agreement** | Lag growing + high processing time + no restarts → consumer too slow for ingest rate (need more replicas or faster processing) |
| **Disagreement** | Lag growing BUT consumer is idle (low CPU, no processing) → partition reassignment loop. Consumer joins, gets partitions, gets evicted, repeats. Check `session.timeout.ms` vs `max.poll.interval.ms` in consumer config. Load `strimzi-kafka-metrics` |

---

## Secret Sync Failure

| Signal | What to check | Expected if IRSA broken |
|--------|--------------|--------------------------|
| Metric | ExternalSecret status condition (if instrumented) | status=False |
| Log | ESO controller: "AccessDeniedException" or "InvalidIdentityToken" | IRSA trust relationship broken |
| K8s event | ExternalSecret events: `SyncError` | Shows exact AWS error |
| **Agreement** | AccessDenied in ESO log + SyncError event → IRSA misconfigured. Load `iam-patterns` to fix trust policy |
| **Disagreement** | ESO shows `SecretSynced=True` (synced successfully) BUT pod still using old value → pod was not restarted after secret update. Check if Stakater Reloader is watching the secret (annotation `reloader.stakater.com/auto: "true"` on Deployment) |
