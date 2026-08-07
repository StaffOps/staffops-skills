# OTel Pipeline — Reference

## Pipeline Topology

```
Apps → OTel Agent (DaemonSet, 1/node)
     → OTel Gateway (StatefulSet, 5 replicas, core-devops)
         traces → loadbalancing → OTel Spanmetrics
         logs + metrics → direct
     → Kafka (otlp_spans, otlp_logs, otlp_metrics)
     → OTel Process (StatefulSet, KEDA 5–10)
         → VictoriaMetrics (prometheusremotewrite)
         → Tempo (otlp_http)
         → Loki (otlp_http)
```

> ⚠️ Tail sampling is on the Agent (not Gateway). The `loadbalancing/traces` exporter on Agent uses `routing_key: traceID` with static gateway hostnames for trace affinity.

## Sizing (current deployed)

| Collector | Memory limit | GOMEMLIMIT | Replicas | Scaling |
|-----------|-------------|------------|----------|---------|
| Agent | per-node | — | DaemonSet | Node count |
| Gateway | 8Gi | 5600Mi | 5 (StatefulSet) | Manual |
| Process | 12Gi | 8400Mi | 5–10 | KEDA (Kafka lag threshold: 20k) |
| Spanmetrics | 8Gi | — | 1 | Manual |

## Key Metrics Reference

| Metric | Type | Normal Range | Investigation Threshold | Notes |
|--------|------|-------------|------------------------|-------|
| `otelcol_receiver_accepted_spans_total` | Counter | > 0 | = 0 for > 2m | No data entering |
| `otelcol_receiver_refused_spans_total` | Counter | 0 | > 0 | Backpressure from downstream |
| `otelcol_exporter_send_failed_spans_total` | Counter | 0 | > 0 sustained | Network/downstream failure |
| `otelcol_exporter_enqueue_failed_spans_total` | Counter | 0 | > 0 | **DATA LOSS** — queue full |
| `otelcol_exporter_enqueue_failed_log_records` | — | — | — | **DOES NOT EXIST** — queue disabled on log exporter. Use `otelcol_exporter_send_failed_log_records` |
| `otelcol_exporter_enqueue_failed_metric_points` | Counter | 0 | > 0 | **DATA LOSS** — queue full. **No `_total` suffix** |
| `otelcol_exporter_queue_size` / `queue_capacity` | Gauge | < 50% | > 80% | Imminent data loss |
| `otelcol_processor_incoming_items` - `outgoing_items` | Counter | ≈ sampling ratio | Unexpected gap growing | Processor dropping |
| `kafka_consumergroup_lag{consumergroup="otel-process-consumer"}` | Gauge | < 10k | > 50k and growing | Processing behind |

## Common Failure Modes

| Failure | Signal | Root Cause | Recovery |
|---------|--------|-----------|----------|
| Gateway OOM → data loss | enqueue_failed > 0, OOMKill events | memory_limiter too high or batch too large | Reduce memory_limiter to 75% of container limit |
| Kafka unreachable | send_failed{exporter="kafka"} spike | Broker restart, DNS, security group | Check Kafka health, network |
| Process can't keep up | Kafka lag growing, KEDA at max | Backend slow (Tempo/VM/Loki) | Fix backend first |
| k8sattr metadata missing | Traces without k8s.namespace.name | RBAC missing, pod churn | Check ClusterRoleBinding |
| Broken traces in Tempo | Parent spans without children | routing_key not set, wait_time too short | Ensure traceID routing on all exporters |

## Recovery Playbook

1. Identify the failing stage (queries in SKILL.md, upstream → downstream)
2. Check pod health: `kubectl get pods -n monitoring -l app.kubernetes.io/component=opentelemetry-collector`
3. Check resource usage: actual memory vs GOMEMLIMIT (leave 30% headroom)
4. Check downstream: if backend is the bottleneck, fix the backend first
5. ⚠️ Scale if needed: KEDA handles Process; Gateway needs manual StatefulSet scale
6. ⚠️ Never restart collectors blindly — PVC-backed file_storage queues survive restarts, but in-memory queues lose data
