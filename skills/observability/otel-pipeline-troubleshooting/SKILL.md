---
name: otel-pipeline-troubleshooting
description: "Diagnose data loss, backpressure, and failures in the OTel Collector pipeline. Symptoms: missing telemetry in Tempo/Loki/VictoriaMetrics, growing Kafka lag, otelcol_exporter_enqueue_failed > 0, otelcol_exporter_send_failed > 0, collector pods OOMKilled or CrashLoopBackOff. Pipeline flow: Agent (DaemonSet, tail_sampling) → Gateway (StatefulSet 5x, exports to Kafka) → Process (KEDA 5–10, consumes Kafka → backends)."
---

# OTel Pipeline Troubleshooting

## When to use this skill

- Telemetry missing, delayed, or incomplete in backends (Tempo, Loki, VictoriaMetrics)
- `otelcol_exporter_enqueue_failed_*` > 0 (active data loss)
- `otelcol_exporter_send_failed_*` > 0 (export failures)
- Kafka consumer lag growing for `otel-process-consumer`
- Collector pods restarting, OOMKilled, or CrashLoopBackOff
- Spans appear in Tempo with missing metadata (k8sattr failure)

## When this skill does NOT apply

- Kafka broker health issues (partition, ISR) → use `kafka-pipeline-health`
- VictoriaMetrics ingestion slow/rejecting → use `victoriametrics-investigation`
- Cardinality explosion causing metric loss → use `vm-cardinality-management`
- Cross-signal correlation config broken → use `grafana-cross-signal-correlation`

## Step 1: Check receiver layer — is data entering?

Query the Agent (upstream-most). If receivers show 0 accepted, the problem is before the pipeline.

```promql
sum(rate(otelcol_receiver_accepted_spans_total{job=~".*agent.*"}[5m]))
sum(rate(otelcol_receiver_refused_spans_total{job=~".*agent.*"}[5m]))
```

- **Normal**: accepted > 0, refused = 0
- **Investigate if**: refused > 0 (gateway backpressuring) or accepted = 0 (apps not sending)

## Step 2: Check Agent export — is data leaving agents?

```promql
sum(rate(otelcol_exporter_send_failed_spans_total{job=~".*agent.*"}[5m]))
```

- **Normal**: 0
- **Investigate if**: > 0 → gateway unreachable, DNS resolution, TLS cert expiry

## Step 3: Check Gateway — is sampling and routing working?

```promql
# Throughput
sum(rate(otelcol_receiver_accepted_spans_total{job=~".*gateway.*"}[5m]))

# Processor drop gap (incoming - outgoing = dropped)
sum(rate(otelcol_processor_incoming_items{job=~".*gateway.*",otel_signal="traces"}[5m]))
- sum(rate(otelcol_processor_outgoing_items{job=~".*gateway.*",otel_signal="traces"}[5m]))

# Export to Kafka
sum(rate(otelcol_exporter_send_failed_spans_total{job=~".*gateway.*",exporter="kafka"}[5m]))

# Queue saturation (>80% = imminent loss)
otelcol_exporter_queue_size{job=~".*gateway.*"} / otelcol_exporter_queue_capacity{job=~".*gateway.*"}
```

- **Normal**: drop gap ≈ expected tail_sampling ratio, send_failed = 0, queue < 50%
- **Critical**: queue > 80% = data loss imminent; send_failed > 0 = Kafka issue

## Step 4: Check Kafka lag — is the buffer draining?

```promql
sum(kafka_consumergroup_lag{consumergroup="otel-process-consumer"}) by (topic)
deriv(sum(kafka_consumergroup_lag{consumergroup="otel-process-consumer"})[10m:1m])
```

- **Normal**: lag < 10k, deriv ≤ 0 (draining or stable)
- **Degraded**: 10k–50k and stable
- **Critical**: > 50k and growing → see `kafka-pipeline-health`

## Step 5: Check Process collector — is data reaching backends?

```promql
# THE critical data-loss signal
sum(rate(otelcol_exporter_enqueue_failed_spans_total{job=~".*process.*"}[5m]))
# NOTE: otelcol_exporter_enqueue_failed_log_records does NOT exist — use send_failed:
sum(rate(otelcol_exporter_send_failed_log_records{job=~".*process.*"}[5m]))
sum(rate(otelcol_exporter_enqueue_failed_metric_points{job=~".*process.*"}[5m]))

# Memory limiter drops (processor-level loss)
sum(rate(otelcol_processor_memory_limiter_refused_spans{job=~".*process.*"}[5m]))
sum(rate(otelcol_processor_memory_limiter_refused_log_records{job=~".*process.*"}[5m]))

# Export success
sum(rate(otelcol_exporter_sent_spans_total{job=~".*process.*"}[5m])) by (exporter)
sum(rate(otelcol_exporter_send_failed_spans_total{job=~".*process.*"}[5m])) by (exporter)
```

- **Normal**: enqueue_failed = 0, send_failed = 0
- **Critical**: enqueue_failed > 0 = **permanent data loss** (queue full, items discarded). Resource metrics may look fine while this happens.

## Step 6: Summarize findings

1. **Status** — healthy / degraded / critical
2. **Root cause hypothesis** — cite the stage where flow breaks (e.g., "Gateway queue at 92%, Kafka lag growing at 5k/min, Process enqueue_failed_log_records = 2840/sec")
3. **Recommended remediation** — ranked:
   - Fix downstream bottleneck first (backend health)
   - ⚠️ RECOMMENDATION ONLY — read-only agent, a human executes: Scale gateway StatefulSet replicas
   - ⚠️ RECOMMENDATION ONLY — read-only agent, a human executes: Adjust memory_limiter / GOMEMLIMIT
   - ⚠️ RECOMMENDATION ONLY — read-only agent, a human executes: Increase KEDA maxReplicas for Process
4. **Confidence** — count independent signals (receiver refused, queue saturation, enqueue_failed, pod events, backend errors). Assert root cause only with ≥3.

## Decision tree — symptom-first routing

```
SYMPTOM: What are you seeing?
│
├─ "Traces missing from Tempo"
│  ├── sum(rate(otelcol_receiver_accepted_spans_total{job=~".*agent.*"}[5m])) = 0?
│  │   └── YES → Apps not sending. Check SDK config, OTLP endpoint, service up{}
│  ├── sum(rate(otelcol_exporter_send_failed_spans_total{job=~".*agent.*"}[5m])) > 0?
│  │   └── YES → Agent can't reach Gateway. DNS? TLS cert expired? Gateway down?
│  ├── otelcol_exporter_queue_size{job=~".*gateway.*"} / queue_capacity > 0.8?
│  │   └── YES → Gateway saturated → check Kafka send_failed
│  ├── kafka_consumergroup_lag{consumergroup="otel-process-consumer",topic="otlp_spans"} growing?
│  │   └── YES → Process can't keep up → KEDA at max? Backend bottleneck?
│  └── sum(rate(tempo_discarded_spans_total[5m])) > 0?
│      └── YES → Tempo rejecting. Check reason label (trace_too_large, rate_limited)
│
├─ "Logs missing from Loki"
│  ├── sum(rate(otelcol_exporter_send_failed_log_records{job=~".*gateway.*"}[5m])) > 0?
│  │   └── YES → Gateway can't export logs. Kafka reachable?
│  ├── kafka_consumergroup_lag{topic="otlp_logs"} growing?
│  │   └── YES → Process behind on logs specifically
│  └── sum(rate(loki_discarded_samples_total[5m])) by (reason) > 0?
│      └── YES → Loki rejecting. rate_limited? per_stream_limit?
│
├─ "Metrics gaps in dashboards"
│  ├── sum(rate(otelcol_exporter_send_failed_metric_points_total{job=~".*process.*"}[5m])) > 0?
│  │   └── YES → Process can't write to VM
│  ├── sum(rate(vm_rows_ignored_total[5m])) by (reason) > 0?
│  │   └── YES → VM rejecting samples. Check reason: duplicate? out_of_order?
│  └── vmagent_remotewrite_pending_data_bytes growing?
│      └── YES → vmagent backpressure → vminsert overloaded
│
├─ "Collector pods crashing"
│  ├── OOMKilled? → memory_limiter misconfigured or GOMEMLIMIT too low
│  ├── CrashLoopBackOff? → Check previous logs: config parse error? TLS? permissions?
│  └── Evicted? → Node pressure → check node_memory_MemAvailable
│
└─ "Metadata missing on spans" (no k8s.* attributes)
   ├── k8sattributesprocessor in config? → Check RBAC (needs get/list/watch pods)
   └── Pod IP matching? → k8sattr needs pod_association by IP; check gateway can resolve pod IPs
```

## Quick-reference: per-hop health check (copy-paste)

Run these in sequence. The FIRST non-zero failure counter identifies the broken hop:

```promql
# Hop 1: App → Agent
sum(rate(otelcol_receiver_refused_spans_total{job=~".*agent.*"}[5m]))

# Hop 2: Agent → Gateway
sum(rate(otelcol_exporter_send_failed_spans_total{job=~".*agent.*"}[5m]))

# Hop 3: Gateway → Kafka
sum(rate(otelcol_exporter_send_failed_spans_total{job=~".*gateway.*",exporter="kafka"}[5m]))

# Hop 4: Kafka → Process (lag as proxy)
sum(kafka_consumergroup_lag{consumergroup="otel-process-consumer"})

# Hop 5: Process → Backends
sum(rate(otelcol_exporter_enqueue_failed_spans_total{job=~".*process.*"}[5m]))
sum(rate(otelcol_exporter_send_failed_spans_total{job=~".*process.*"}[5m]))
```

**Interpretation**: First non-zero counter = the failing hop. Investigate that layer.

## Related skills

- `kafka-pipeline-health` — Kafka broker/partition/lag deep-dive
- `victoriametrics-investigation` — VM ingestion/query issues
- `otel-collector-multi-cluster` — topology, k8sattr, routing config
- `collector-internal-metrics` — full metric reference table
