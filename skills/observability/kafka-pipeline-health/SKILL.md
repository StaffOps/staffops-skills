---
name: kafka-pipeline-health
description: >
  Monitor and troubleshoot the Kafka buffer in the OTel telemetry pipeline
  (Strimzi-managed, KRaft mode). Symptoms: growing consumer lag for
  otel-process-consumer, under-replicated partitions, broker pod failures,
  gateway send_failed to Kafka exporter, delayed telemetry in backends.
  Topics: otlp_spans, otlp_logs, otlp_metrics.
---

# Kafka Pipeline Health

## When to use this skill

- Kafka consumer lag for `otel-process-consumer` growing (> 50k)
- Telemetry arrives in backends with increasing delay
- `otelcol_exporter_send_failed_*{exporter="kafka"}` > 0 on gateway
- Kafka broker pods restarting or unhealthy
- Under-replicated partitions detected
- KEDA not scaling Process collector despite high lag

## When this skill does NOT apply

- OTel pipeline issues upstream of Kafka (agent/gateway) → use `otel-pipeline-troubleshooting`
- Backend rejecting data after Kafka (VM/Tempo/Loki) → use `victoriametrics-investigation`
- Strimzi Kafka application metrics (not OTel pipeline) → use `strimzi-kafka-metrics`

## Step 1: Measure consumer lag (the primary health signal)

```promql
# Total lag — the single most important number
sum(kafka_consumergroup_lag{consumergroup="otel-process-consumer"})

# Lag by topic — which signal is falling behind?
sum(kafka_consumergroup_lag{consumergroup="otel-process-consumer"}) by (topic)

# Lag trend — growing = problem, stable = acceptable backlog
deriv(sum(kafka_consumergroup_lag{consumergroup="otel-process-consumer"})[10m:1m])

# Lag velocity (messages/sec being added to backlog) — more intuitive than deriv
(sum(kafka_consumergroup_lag{consumergroup="otel-process-consumer"}) - sum(kafka_consumergroup_lag{consumergroup="otel-process-consumer"} offset 5m)) / 300

# Consumer commit rate (is consumer making progress at all?)
sum(rate(kafka_consumergroup_current_offset{consumergroup="otel-process-consumer"}[5m])) by (topic)

# Production rate vs consumption rate (the supply/demand balance)
# Production:
sum(rate(kafka_server_brokertopicmetrics_messagesin_total{topic=~"otlp_.*"}[5m])) by (topic)
# Consumption (commits/sec):
sum(rate(kafka_consumergroup_current_offset{consumergroup="otel-process-consumer"}[5m])) by (topic)
# If production > consumption sustained → lag grows

# Time-to-drain estimate (how long until lag is zero at current rate)
# lag / (consumption_rate - production_rate) = seconds to drain
# Only valid when consumption > production (otherwise infinite)

# Lag approaching retention (DATA LOSS imminent) — rough heuristic:
# If lag_messages / consumption_rate > retention_ms/1000, oldest messages will expire
# Default retention is 7 days (604800s). If lag represents >6 days of data → CRITICAL.
```

| Lag Level | Status | Action |
|-----------|--------|--------|
| < 10k | Healthy | None |
| 10k–50k | Degraded | Monitor trend, check if KEDA is scaling |
| 50k–200k | Critical | KEDA should have scaled; investigate consumer health |
| > 200k | Emergency | Consumer cannot keep up; investigate downstream bottleneck |

## Step 1b: Per-partition lag analysis (find hot partitions)

```promql
# Lag by partition — identifies uneven distribution
kafka_consumergroup_lag{consumergroup="otel-process-consumer"} by (topic, partition)

# Find the MAX lag partition (hot partition)
topk(5, kafka_consumergroup_lag{consumergroup="otel-process-consumer"})

# Check if one partition is stuck (lag growing while others are stable)
deriv(kafka_consumergroup_lag{consumergroup="otel-process-consumer"}[10m:1m]) > 0
```

**Hot partition signals**: If one partition has 10x the lag of others → that partition's consumer is stuck or the partition has disproportionate traffic. This is common when the producer key distribution is skewed.

## Step 2: Check broker health

```promql
# Under-replicated partitions (MUST be 0)
kafka_server_replicamanager_underreplicatedpartitions

# Active controller count (must be exactly 1 in KRaft)
kafka_controller_kafkacontroller_activecontrollercount

# ISR shrinks (replication falling behind)
sum(rate(kafka_server_replicamanager_isrshrinks_total[5m]))
```

- **Normal**: under-replicated = 0, controller = 1, ISR shrinks = 0
- **Investigate if**: any non-zero → broker disk, memory, or network issue

## Step 3: Check producer side (gateway → Kafka)

```promql
# Gateway successfully producing
sum(rate(otelcol_exporter_sent_spans_total{job=~".*gateway.*",exporter="kafka"}[5m]))

# Gateway failing to produce (should be 0)
sum(rate(otelcol_exporter_send_failed_spans_total{job=~".*gateway.*",exporter="kafka"}[5m]))

# Message throughput at broker
sum(rate(kafka_server_brokertopicmetrics_messagesin_total[5m])) by (topic)
```

- **Normal**: sent > 0, send_failed = 0
- **Investigate if**: send_failed > 0 → Kafka unreachable from gateway

## Step 4: Check consumer side (Kafka → Process)

```promql
# Process collector receiving from Kafka
sum(rate(otelcol_receiver_accepted_spans_total{job=~".*process.*",receiver="kafka"}[5m]))

# Process export success to backends
sum(rate(otelcol_exporter_sent_spans_total{job=~".*process.*"}[5m])) by (exporter)
```

- If receiver_accepted > 0 but lag still growing → consumer is slower than producer
- If receiver_accepted = 0 → consumer is disconnected from Kafka

## Step 5: Verify KEDA auto-scaling

Process collector scales via KEDA (min 5, max 10, threshold 20k lag).

- Check current replica count vs max
- Check ScaledObject status for errors
- If at max replicas and lag growing → bottleneck is downstream (backends)

## Step 6: Summarize findings

1. **Status** — healthy / degraded / critical
2. **Root cause hypothesis** — cite lag values, trend, producer/consumer rates (e.g., "Lag at 180k and growing at 3k/min, Process at max 10 replicas, Tempo returning 503")
3. **Recommended remediation** — ranked:
   - Fix downstream backend if it's the bottleneck
   - ⚠️ RECOMMENDATION ONLY — read-only agent, a human executes: Increase KEDA maxReplicas
   - ⚠️ RECOMMENDATION ONLY — read-only agent, a human executes: Increase topic partition count (requires consumer rebalance)
   - ⚠️ RECOMMENDATION ONLY — read-only agent, a human executes: Increase Kafka retention if lag approaches retention window
4. **Confidence** — ≥3 signals: lag trend + producer rate + consumer rate + backend health

## Decision tree

```
Kafka lag growing?
├── Producer send_failed > 0 → Gateway can't reach Kafka
│   ├── Kafka pods healthy? → Check network/DNS/security group
│   └── Kafka pods unhealthy → Check broker disk/memory, PVC
├── Consumer receiving but lag growing → Consumer too slow
│   ├── KEDA scaling? → Wait for scale-up
│   ├── KEDA at max? → Backend is bottleneck (check VM/Tempo/Loki)
│   └── Process pods OOMKilled → Increase memory, check batch sizes
└── Messages in = 0 for topic → Gateway not producing
    └── Check gateway health (otel-pipeline-troubleshooting)
```

## Related skills

- `otel-pipeline-troubleshooting` — full pipeline diagnosis (upstream/downstream of Kafka)
- `strimzi-kafka-metrics` — detailed Kafka broker/JVM metric reference
- `victoriametrics-investigation` — when VM is the downstream bottleneck
