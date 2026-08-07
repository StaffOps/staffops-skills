# OTel Pipeline Review Checklist

## Pre-flight

- [ ] Confirm pipeline topology is unchanged: Agent → Gateway (5x) → Kafka → Process (KEDA 5–10) → backends
- [ ] Confirm review time window: use last 30 min for point-in-time, last 24h for trend
- [ ] Budget: Evaluation tier (8 min / $4.00 / 20–25 queries)

## Dimension 1: End-to-end data loss

- [ ] Agent → Gateway: `otelcol_exporter_send_failed_*{job=~".*agent.*"}` = 0
- [ ] Gateway permanent loss: `otelcol_exporter_enqueue_failed_*{job=~".*gateway.*"}` = 0
- [ ] Gateway → Kafka: `otelcol_exporter_send_failed_*{exporter="kafka"}` = 0
- [ ] Gateway backpressure: `otelcol_receiver_refused_*{job=~".*gateway.*"}` = 0
- [ ] Process → Backends: `otelcol_exporter_send_failed_*{job=~".*process.*"}` = 0
- [ ] VM loss: `vm_rpc_rows_dropped_on_overload_total` increase = 0
- [ ] VM rejection: `vm_rows_ignored_total` rate ≈ 0 (check `reason`)
- [ ] Tempo rejection: `tempo_discarded_spans_total` rate = 0
- [ ] Loki rejection: `loki_discarded_samples_total` rate = 0

## Dimension 2: Queue headroom

- [ ] Gateway queues: `queue_size / queue_capacity` < 60% (all exporters)
- [ ] Process queues: `queue_size / queue_capacity` < 60% (all exporters)

## Dimension 3: Tail-sampling correctness

- [ ] Sampling ratio reasonable: `outgoing / incoming` at Agent tail_sampling processor
- [ ] Error traces present in Tempo: `{status=error}` returns results
- [ ] Slow traces present: `{duration > 1s}` returns results (if traffic exists)

## Dimension 4: Cardinality trend

- [ ] `rate(vm_new_timeseries_created_total[30m])` < 1000/sec
- [ ] TSID cache miss rate < 5%
- [ ] Total active series within expected growth (no step-change jumps)

## Dimension 5: Kafka buffer health

- [ ] Consumer lag < 10k (total for `otel-process-consumer`)
- [ ] Lag trend: `deriv()` ≤ 0 (stable or draining)
- [ ] No topics approaching retention limit

## Dimension 6: Resource headroom (context only)

- [ ] Only check if a finding exists in dimensions 1–5
- [ ] Gateway CPU < 75%, Memory < 80%
- [ ] Process CPU < 75%, Memory < 80%

## Report template

```
## OTel Pipeline Review — YYYY-MM-DD

| Dimension | Status | Value | Threshold |
|-----------|--------|-------|-----------|
| Data loss | PASS/FINDING | [values] | = 0 |
| Queue headroom | PASS/FINDING | max X% | < 60% |
| Sampling | PASS/FINDING | [ratio] | 100% error retention |
| Cardinality | PASS/FINDING | X/sec new | < 1000/sec |
| Kafka buffer | PASS/FINDING | lag Xk, trend Y | < 10k, stable |
| Resources | CONTEXT/N-A | CPU X%, Mem Y% | < 75% |

**Overall**: HEALTHY / DEGRADED / CRITICAL
**Findings**: [count], highest severity: [SEV]
**Recommendations** (ranked):
1. ...
2. ...
```
