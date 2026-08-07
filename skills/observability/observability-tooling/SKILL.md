---
name: observability-tooling
description: >
  Route observability symptoms to the correct MCP tool with correct parameters.
  Use as the FIRST skill loaded when any observability investigation begins.
  Maps symptoms (slow service, errors spiking, data loss, cost spike, alert
  firing) to the specific MCP tool invocation, parameters, and result
  interpretation. Covers VictoriaMetrics MCP, Tempo MCP, Grafana MCP (Loki,
  dashboards, alerting), and kubectl for pod health.
---

# Observability Tooling — Symptom Router

## When to use this skill

- Starting any observability investigation (first skill to consult)
- Need to decide: which MCP tool? which parameters? how to interpret result?
- User reports a symptom and you need the fastest path to evidence

## When this skill does NOT apply

- Already know which backend to query → use the specific skill directly
- Need config changes (not investigation) → use configuration skills
- Non-observability investigation (AWS, GitOps, security)

## Routing Table: Symptom → Tool → Parameters → Interpretation

### Signal type → Backend → MCP tool (quick reference)

| Signal | Backend | MCP Tool | Key parameters |
|--------|---------|----------|----------------|
| Metrics (counters, gauges, histograms) | VictoriaMetrics | `query` / `query_range` | MetricsQL expr, time range |
| Metrics metadata | VictoriaMetrics | `metrics`, `metrics_metadata`, `tsdb_status` | match pattern, metric name |
| Alerting rules & state | VictoriaMetrics (vmalert) | `alerts`, `rules` | state, group filter |
| Traces (distributed) | Tempo | `traceql-search`, `get-trace` | TraceQL expr, trace_id |
| Trace metrics (aggregates) | Tempo | `traceql-metrics-instant`, `traceql-metrics-range` | TraceQL metrics expr |
| Trace attributes discovery | Tempo | `get-attribute-names`, `get-attribute-values` | scope, attribute name |
| Logs | Loki (via Grafana) | `query_loki_logs` | LogQL, time range, limit |
| Log stats (cheap check) | Loki (via Grafana) | `query_loki_stats` | stream selector only |
| Log patterns | Loki (via Grafana) | `query_loki_patterns` | stream selector |
| Log labels | Loki (via Grafana) | `list_loki_label_names`, `list_loki_label_values` | datasource UID |
| Dashboards | Grafana | `search_dashboards`, `get_dashboard_by_uid` | query, UID |
| Annotations (deploys) | Grafana | `get_annotations` | time range, tags |
| Pod health | Kubernetes | `check_pod_health`, `diagnose_pod_crash` | pod name, namespace |
| Pod logs | Kubernetes | `get_logs`, `get_previous_logs` | pod name, tail lines |
| Events | Kubernetes | `events_list` | namespace, field selector |

### "Service is slow" / high latency

| Step | Tool | Parameters | Interpret |
|------|------|-----------|-----------|
| 1 | `query` (VM) | `rate(http_server_request_duration_seconds_count{service_name="X"}[5m])` | Confirm traffic exists |
| 2 | `query` (VM) | `histogram_quantile(0.99, sum(rate(http_server_request_duration_seconds_bucket{service_name="X"}[5m])) by (le))` | p99 latency value |
| 3 | `traceql-search` | `{resource.service.name="X" && duration > 1s}` | Find slow traces |
| 4 | `get-trace` | trace_id from step 3 | Identify slow span |

### "Errors spiking"

| Step | Tool | Parameters | Interpret |
|------|------|-----------|-----------|
| 1 | `query` (VM) | `sum(rate(http_server_request_duration_seconds_count{service_name="X",http_status_code=~"5.."}[5m]))` | Error rate |
| 2 | `traceql-search` | `{resource.service.name="X" && status = error}` | Error traces |
| 3 | `query_loki_logs` | `{service_workload="X"} \|= "error" \| json \| level="error"` | Error details |

### "Missing telemetry / data loss"

| Step | Tool | Parameters | Interpret |
|------|------|-----------|-----------|
| 1 | `query` (VM) | `sum(rate(otelcol_exporter_enqueue_failed_spans_total[5m]))` | > 0 = data loss |
| 2 | `query` (VM) | `sum(kafka_consumergroup_lag{consumergroup="otel-process-consumer"})` | > 50k = pipeline behind |
| 3 | `query` (VM) | `sum(rate(otelcol_exporter_send_failed_spans_total[5m])) by (job)` | Which collector failing |

### "Alert firing — what's wrong?"

| Step | Tool | Parameters | Interpret |
|------|------|-----------|-----------|
| 1 | `alerts` (VM) | state="firing" | List active alerts |
| 2 | `query` (VM) | Copy the alert expression | Reproduce the condition |
| 3 | `traceql-search` or `query_loki_logs` | Service + timeframe from alert | Correlate |

### "Pod crashing / OOMKilled"

| Step | Tool | Parameters | Interpret |
|------|------|-----------|-----------|
| 1 | `diagnose_pod_crash` (kubectl) | pod_name, namespace | Get crash reason |
| 2 | `get_previous_logs` (kubectl) | pod_name, namespace | Last output before crash |
| 3 | `query` (VM) | `container_memory_working_set_bytes{pod="X"}` | Memory trajectory |

### "Cost/cardinality spike"

| Step | Tool | Parameters | Interpret |
|------|------|-----------|-----------|
| 1 | `tsdb_status` (VM) | (no params) | Top metrics by series |
| 2 | `query` (VM) | `rate(vm_new_timeseries_created_total[5m])` | Creation rate |
| 3 | `metric_statistics` (VM) | match_pattern for suspect metric | Query frequency |

### "What happened at time T?"

| Step | Tool | Parameters | Interpret |
|------|------|-----------|-----------|
| 1 | `get_annotations` (Grafana) | time range around T | Deploys, incidents |
| 2 | `traceql-search` | `{duration > 1s}` with start/end around T | Traces at that time |
| 3 | `query_loki_logs` | `{eks_cluster="prd"} \|= "error"` with timeframe | Errors at that time |
| 4 | `query_range` (VM) | Suspect metric with start/end around T | Metric behavior |

## Query Best Practices

### VictoriaMetrics (MetricsQL)

- Always use `rate()` on counters — raw counter values meaningless across restarts
- Multi-cluster: filter by `eks_cluster` (environment: core/dev/prd) or `cluster` (k8s name)
- Use `keep_metric_names` when needed for aggregation: `rate(metric_total[5m]) keep_metric_names`
- Avoid high-cardinality selectors in labels (user_id, request_id)

### Tempo (TraceQL)

- Start broad, narrow down: service → duration → structural
- Use `get-attribute-names` first if unsure what attributes exist
- `histogram_over_time(duration)` for latency distribution (NOT `quantile_over_time`)

### Loki (via Grafana MCP)

- Use `query_loki_stats` first to check if stream has data (cheap)
- Labels: `service_namespace`, `service_workload`, `eks_cluster`
- Structured metadata: `trace_id` (snake_case, for correlation)
- Line filter BEFORE parser for performance

## Datasource UIDs

| Backend | UID | Use for |
|---------|-----|---------|
| VictoriaMetrics | `victoriametrics` | Metrics, SLO, recording rules |
| Tempo | `tempo` | Traces, service graph |
| Loki | `loki` | Logs |
| Pyroscope | `pyroscope` | Profiles |
| Alertmanager | `alertmanager` | Alert routing |
| CloudWatch | `cloudwatch` | AWS service metrics |

## Pipeline Health Quick-Check (run before trusting telemetry)

| Check | Query | Healthy |
|-------|-------|---------|
| OTel receiving | `sum(rate(otelcol_receiver_accepted_spans[5m]))` | > 0 |
| No drops | `sum(rate(otelcol_exporter_send_failed_spans_total[5m]))` | = 0 |
| Kafka lag | `sum(kafka_consumergroup_lag{group=~"otel.*"})` | < 50k |
| VM ingesting | `sum(rate(vm_rows_inserted_total[5m]))` | > 0 |
| Tempo receiving | `sum(rate(tempo_distributor_spans_received_total[5m]))` | > 0 |
| Loki receiving | `sum(rate(loki_distributor_lines_received_total[5m]))` | > 0 |

## Related skills

- `otel-pipeline-troubleshooting` — deep-dive when pipeline health fails
- `victoriametrics-investigation` — VM-specific issues
- `loki-logql-patterns` — LogQL query construction
- `tempo-trace-investigation` — TraceQL query construction
- `kafka-pipeline-health` — Kafka buffer issues

## Decision tree — "Which tool do I use?"

```
What evidence do I need?
│
├─ A NUMBER over time (rate, count, gauge value)
│  └── VictoriaMetrics: query / query_range
│
├─ WHO is calling WHOM (request flow, latency per hop)
│  └── Tempo: traceql-search → get-trace
│
├─ WHAT an application logged (error messages, stack traces)
│  └── Loki: query_loki_logs
│     └── First: query_loki_stats (confirm data exists — cheap)
│
├─ IS something UP or DOWN right now?
│  ├── Pod health → kubectl: check_pod_health, diagnose_pod_crash
│  ├── Endpoint externally → kuma-synthetic-status queries
│  └── Scrape target → VictoriaMetrics: query "up{job="X"}"
│
├─ WHAT changed recently? (deploy, config)
│  └── Grafana: get_annotations (tags: deploy, incident)
│
├─ HOW MUCH data exists for a metric/log stream?
│  ├── Metrics: tsdb_status (series counts)
│  └── Logs: query_loki_stats (stream byte counts)
│
└─ WHAT alerts are firing?
   └── VictoriaMetrics: alerts (state="firing")
```
