# Kafka Pipeline — Reference

## Cluster Topology

| Item | Value |
|------|-------|
| Operator | Strimzi 1.1.0 |
| Kafka version | 4.3.0 (KRaft — no ZooKeeper) |
| Topology | 5 brokers (ids 0–4) + 3 controllers (ids 5–7) |
| Topics | `otlp_spans`, `otlp_logs`, `otlp_metrics` |
| Partitions | 10 per topic |
| Replication | RF=3, min.insync.replicas=2 |
| Retention | 4 hours / 30GB per partition |
| Message max | 10MB |
| Consumer group | `otel-process-consumer` |
| Management | helmfile (`bedag/raw`, release `kafka-cluster`) |

## Key Metrics

| Metric | Type | Normal Range | Investigation Threshold | Notes |
|--------|------|-------------|------------------------|-------|
| `kafka_consumergroup_lag{consumergroup="otel-process-consumer"}` | Gauge | < 10k | > 50k and growing | Primary health signal |
| `kafka_server_replicamanager_underreplicatedpartitions` | Gauge | 0 | > 0 | Broker disk/network issue |
| `kafka_controller_kafkacontroller_activecontrollercount` | Gauge | 1 | ≠ 1 | Split brain or no controller |
| `kafka_server_replicamanager_isrshrinks_total` | Counter | 0 | > 0 sustained | Replication falling behind |
| `kafka_server_brokertopicmetrics_messagesin_total` | Counter | baseline-relative | = 0 for a topic | Gateway not producing |
| `kafka_server_brokertopicmetrics_bytesin_total` | Counter | baseline-relative | Compare to 7d p95 | Bandwidth spike |
| `otelcol_exporter_sent_spans_total{exporter="kafka"}` | Counter | > 0 | = 0 | Gateway not sending |
| `otelcol_exporter_send_failed_spans_total{exporter="kafka"}` | Counter | 0 | > 0 | Kafka unreachable from gateway |

## KEDA Auto-Scaling Config

| Parameter | Value |
|-----------|-------|
| Min replicas | 5 |
| Max replicas | 10 |
| Trigger | Kafka consumer lag |
| Threshold | 20,000 messages |
| Consumer group | `otel-process-consumer` |

## Known Gotcha: required_acks=1

The OTel Kafka exporter uses `required_acks: 1` (leader only, not `all`). A message is acknowledged after ONE broker writes it, before replication. If the leader dies immediately after ack, that message is **lost**.

**Signal of loss**: `otelcol_exporter_send_failed_*{exporter="kafka"}` spikes during leader migrations, combined with gaps in downstream data.

Trade-off: lower latency at cost of theoretical durability. Loss is rare, only during broker failures.
