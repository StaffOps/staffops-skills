---
name: otel-pipeline-review
description: >
  Proactive operational review of the OTel telemetry pipeline (Evaluation agent type).
  Produces a findings report covering end-to-end data loss, queue headroom, tail-sampling
  correctness, cardinality trend, Kafka buffer health, and resource headroom. Pipeline:
  Agent DaemonSet (tail_sampling) → Gateway StatefulSet (5x, exports to Kafka) → Kafka →
  Process collector (KEDA 5–10, consumes Kafka) → VictoriaMetrics/Tempo/Loki/Pyroscope.
  Each dimension reports PASS/FINDING with measured value vs threshold.
---

# OTel Pipeline Operational Review

## When to use this skill

- Scheduled proactive review (weekly/biweekly cadence).
- After a pipeline change (new processor, scaling event, Kafka topic change).
- Before a high-traffic event (known batch window, product launch).
- When asked "is the telemetry pipeline healthy?" without a specific incident.

## When this skill does NOT apply

- Active data loss incident → use `otel-pipeline-troubleshooting` (reactive, not review).
- Kafka broker health crisis → use `kafka-pipeline-health` (reactive).
- Backend-specific issues (VM slow queries, Tempo OOM) → use backend-specific skills.
- Cost review of the pipeline → use `cost-explorer`.

## Review Dimensions Overview

| # | Dimension | Primary metric | Pass threshold |
|---|-----------|---------------|----------------|
| 1 | End-to-end data loss | Sum of all `*_failed_*` + `*_refused_*` counters | = 0 sustained |
| 2 | Queue headroom | `otelcol_exporter_queue_size / queue_capacity` | < 60% |
| 3 | Tail-sampling correctness | Error/slow trace retention rate | = 100% |
| 4 | Cardinality trend | `vm_new_timeseries_created_total` rate + total series | < 1000/s creation, < 80% of limit |
| 5 | Kafka buffer health | `kafka_consumergroup_lag` trend | Stable or decreasing |
| 6 | Resource headroom | CPU/memory utilization vs limits | < 75% |

## Quick pre-flight checklist (copy-paste for rapid review)

Run these 6 queries. If ALL return 0 / healthy → pipeline PASS without deep-dive:

```promql
# ☐ 1. Data loss (any hop) — MUST be 0
sum(rate(otelcol_exporter_enqueue_failed_spans_total[30m]))
  + sum(rate(otelcol_exporter_send_failed_spans_total[30m]))
  + sum(rate(otelcol_exporter_send_failed_log_records[30m]))
  + sum(rate(otelcol_exporter_send_failed_metric_points_total[30m]))

# ☐ 2. Queue saturation — MUST be < 0.6
max(otelcol_exporter_queue_size / otelcol_exporter_queue_capacity)

# ☐ 3. Kafka lag — MUST be < 10k
sum(kafka_consumergroup_lag{consumergroup="otel-process-consumer"})

# ☐ 4. Cardinality creation rate — MUST be < 1000
rate(vm_new_timeseries_created_total[5m])

# ☐ 5. Backend rejections — MUST be 0
sum(rate(vm_rows_ignored_total[30m])) + sum(rate(tempo_discarded_spans_total[30m])) + sum(rate(loki_discarded_samples_total[30m]))

# ☐ 6. Memory limiter drops — MUST be 0
sum(rate(otelcol_processor_refused_spans_total{processor="memory_limiter"}[30m]))
```

**All 6 pass?** → Report "HEALTHY — no findings". No need for deep-dive Steps 1–7.
**Any fail?** → Run the corresponding Step (1–6) for that dimension to get severity and recommendation.

## Step 1: Measure end-to-end data loss across every hop

Check each pipeline layer for permanent data loss. ANY sustained non-zero is a finding.

```promql
# Agent → Gateway: agent export failures
sum(rate(otelcol_exporter_send_failed_spans_total{job=~".*agent.*"}[30m]))
sum(rate(otelcol_exporter_send_failed_log_records{job=~".*agent.*"}[30m]))
sum(rate(otelcol_exporter_send_failed_metric_points_total{job=~".*agent.*"}[30m]))

# Gateway: permanent queue overflow (data gone forever)
sum(rate(otelcol_exporter_enqueue_failed_spans_total{job=~".*gateway.*"}[30m]))
# NOTE: otelcol_exporter_enqueue_failed_log_records does NOT currently exist in this environment
# (queue likely disabled on log exporter). Use send_failed as the log loss signal:
sum(rate(otelcol_exporter_send_failed_log_records{job=~".*gateway.*"}[30m]))
sum(rate(otelcol_exporter_enqueue_failed_metric_points{job=~".*gateway.*"}[30m]))

# Gateway → Kafka: export failures
sum(rate(otelcol_exporter_send_failed_spans_total{job=~".*gateway.*",exporter="kafka"}[30m]))

# Gateway: receiver refusing upstream (backpressure to agents)
sum(rate(otelcol_receiver_refused_spans_total{job=~".*gateway.*"}[30m]))

# Process → Backends: export failures
sum(rate(otelcol_exporter_send_failed_spans_total{job=~".*process.*"}[30m]))
sum(rate(otelcol_exporter_send_failed_log_records{job=~".*process.*"}[30m]))
sum(rate(otelcol_exporter_send_failed_metric_points_total{job=~".*process.*"}[30m]))

# Backend rejection (VictoriaMetrics)
sum(rate(vm_rows_ignored_total[30m])) by (reason)
increase(vm_rpc_rows_dropped_on_overload_total[30m])

# Backend rejection (Tempo)
sum(rate(tempo_discarded_spans_total[30m])) by (reason)

# Backend rejection (Loki)
sum(rate(loki_discarded_samples_total[30m])) by (reason)
```

**Pass**: ALL counters = 0 over 30-minute window.
**Finding**: ANY counter > 0 sustained (not a single blip). Severity = CRITICAL if `enqueue_failed` or `vm_rpc_rows_dropped_on_overload_total`; HIGH if `send_failed` (retryable but risky); MEDIUM if backend `discarded` (indicates config issue).

## Step 2: Assess queue headroom at each layer

```promql
# Gateway queue saturation (per exporter)
otelcol_exporter_queue_size{job=~".*gateway.*"} / otelcol_exporter_queue_capacity{job=~".*gateway.*"}

# Process queue saturation (per exporter)
otelcol_exporter_queue_size{job=~".*process.*"} / otelcol_exporter_queue_capacity{job=~".*process.*"}
```

**Pass**: All ratios < 60%. Reasoning: below 60% leaves headroom for traffic spikes (2x burst absorb capacity).
**Finding (MEDIUM)**: 60–80% — headroom shrinking, scale or increase queue_size soon.
**Finding (HIGH)**: >80% — imminent data loss if traffic spikes.

## Step 3: Validate tail-sampling correctness

Tail sampling in the Agent DaemonSet must keep 100% of error traces and 100% of high-latency traces (>1s). Verify by comparing error trace presence upstream vs downstream.

```promql
# Traces with error status entering Agent
sum(rate(otelcol_processor_incoming_items{job=~".*agent.*",processor="tail_sampling",otel_signal="traces"}[30m]))

# Traces exiting Agent (after sampling decision)
sum(rate(otelcol_processor_outgoing_items{job=~".*agent.*",processor="tail_sampling",otel_signal="traces"}[30m]))
```

Validation approach:
1. Calculate sampling ratio: `outgoing / incoming` — should be > the configured probabilistic rate.
2. Spot-check via TraceQL: query Tempo for `{status=error}` traces in the last 30 min — if error traces exist in the window, sampling is keeping them.
3. Query `{duration > 1s}` — should return results if any slow requests occurred.

**Pass**: Error traces present in Tempo, slow traces present, sampling ratio consistent with policy.
**Finding (CRITICAL)**: Error traces missing from Tempo that exist in application logs → tail sampling misconfigured.

## Step 4: Check cardinality trend

```promql
# New series creation rate
rate(vm_new_timeseries_created_total[30m])

# Total active series (approximate from cache)
vm_cache_entries{type="storage/metricName"}

# TSID cache miss rate (proxy for cardinality pressure)
rate(vm_cache_misses_total{type="storage/tsid"}[30m])
/ rate(vm_cache_requests_total{type="storage/tsid"}[30m])
```

**Pass**: New series rate < 1000/sec (reasoning: above this, TSID cache saturates causing slow inserts and ingestion degradation). Total series within expected growth corridor. Cache miss rate < 5%.
**Finding (MEDIUM)**: 1000–5000/sec creation → investigate source with `tsdb_status`.
**Finding (HIGH)**: > 5000/sec creation → active cardinality explosion, delegate to `vm-cardinality-management`.

## Step 5: Kafka buffer health

```promql
# Consumer lag (total and by topic)
sum(kafka_consumergroup_lag{consumergroup="otel-process-consumer"})
sum(kafka_consumergroup_lag{consumergroup="otel-process-consumer"}) by (topic)

# Lag trend (positive = growing = bad)
deriv(sum(kafka_consumergroup_lag{consumergroup="otel-process-consumer"})[30m:5m])

# Broker message in rate (pipeline throughput)
sum(rate(kafka_server_brokertopicmetrics_messagesin_total[30m])) by (topic)
```

**Pass**: Lag < 10k AND trend stable or negative (draining). Reasoning: below 10k at normal throughput = seconds of buffer, well within retention window.
**Finding (MEDIUM)**: Lag 10k–50k with positive trend → consumer falling behind.
**Finding (HIGH)**: Lag > 50k or approaching retention window → data loss imminent when oldest messages expire.

Retention check: if lag (messages) / consumption rate (msg/sec) approaches retention.ms, messages expire before consumption.

## Step 6: Resource headroom (explanation layer only)

Only relevant as an EXPLANATION for a finding in Steps 1–5. Do not flag resource usage alone.

```promql
# CPU utilization per collector layer
sum(rate(container_cpu_usage_seconds_total{namespace="monitoring",container=~"otel.*"}[5m])) by (pod)
/ sum(kube_pod_container_resource_limits{namespace="monitoring",container=~"otel.*",resource="cpu"}) by (pod)

# Memory utilization per collector layer
sum(container_memory_working_set_bytes{namespace="monitoring",container=~"otel.*"}) by (pod)
/ sum(kube_pod_container_resource_limits{namespace="monitoring",container=~"otel.*",resource="memory"}) by (pod)
```

**Context for findings**: CPU > 75% sustained explains send_failed (can't process fast enough). Memory > 80% explains memory_limiter triggering (drops data proactively).
**Not a standalone finding**: "gateway at 65% CPU" is not a finding if Steps 1–5 all pass.

## Step 7: Produce the review report

Format — one section per dimension:

```
## OTel Pipeline Review Report — [date]

### Dimension 1: End-to-end data loss
**Status**: PASS | FINDING (severity)
**Measured**: [actual values for each hop]
**Threshold**: = 0 sustained
**Recommendation**: [if finding]

### Dimension 2: Queue headroom
**Status**: PASS | FINDING (severity)
**Measured**: Gateway max ratio = X%, Process max ratio = Y%
**Threshold**: < 60%
**Recommendation**: [if finding — ⚠️ RECOMMENDATION ONLY — read-only agent, a human executes: increase queue_size in collector config via GitOps]

### Dimension 3: Tail-sampling correctness
**Status**: PASS | FINDING (severity)
**Measured**: Sampling ratio = X%, error traces in Tempo: [present/absent]
**Threshold**: 100% error/slow retention
**Recommendation**: [if finding]

### Dimension 4: Cardinality trend
**Status**: PASS | FINDING (severity)
**Measured**: New series rate = X/sec, total series = Y, TSID miss rate = Z%
**Threshold**: < 1000/sec creation, < 5% miss rate
**Recommendation**: [if finding — see vm-cardinality-management]

### Dimension 5: Kafka buffer health
**Status**: PASS | FINDING (severity)
**Measured**: Lag = Xk, trend = Y msg/min [growing/stable/draining]
**Threshold**: < 10k, stable/negative trend
**Recommendation**: [if finding — ⚠️ RECOMMENDATION ONLY — read-only agent, a human executes: scale Process replicas or increase Kafka partitions]

### Dimension 6: Resource headroom
**Status**: Context for [dimension N finding] | NOT APPLICABLE (no findings above)
**Measured**: Gateway CPU = X%, Memory = Y%; Process CPU = X%, Memory = Y%
**Conclusion**: [explains/does not explain the finding above]

---
**Overall pipeline status**: HEALTHY | DEGRADED (N findings) | CRITICAL (data loss active)
**Budget consumed**: [per investigation-cost-guardrail]
```

## Decision tree

```
Start review
├── Step 1: Data loss? → If ANY non-zero → immediate CRITICAL/HIGH finding
├── Step 2: Queue > 60%? → MEDIUM/HIGH finding → check if explains Step 1
├── Step 3: Error traces missing from Tempo? → CRITICAL finding
├── Step 4: New series > 1000/sec? → MEDIUM/HIGH → delegate vm-cardinality-management
├── Step 5: Kafka lag growing? → MEDIUM/HIGH → check Process scaling
├── Step 6: Resources explain a finding? → Context only
└── Compile report: per-dimension PASS/FINDING + overall status
```

## Related skills

- `collector-internal-metrics` — detailed metric reference for OTel Collector self-telemetry
- `otel-pipeline-troubleshooting` — reactive investigation when data loss is active
- `kafka-pipeline-health` — Kafka broker/topic deep-dive
- `vm-cardinality-management` — when cardinality dimension has a finding
- `loki-tempo-self-metrics` — backend-side ingestion counters (Tempo discarded, Loki discarded)
- `investigation-cost-guardrail` — bounds this review to Evaluation budget tier (8 min / $4.00)
