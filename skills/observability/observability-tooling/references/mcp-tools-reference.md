# Observability MCP Tools — Reference

## VictoriaMetrics MCP

| Tool | Purpose | When |
|------|---------|------|
| `query` | Instant query (single point) | Current value of a metric |
| `query_range` | Range query (time series) | Trends, rates over time |
| `metrics` | List metric names | Discovery — what metrics exist |
| `metrics_metadata` | Metric type, help, unit | Understanding a metric |
| `labels` | List all label names | Discovery — what labels exist |
| `label_values` | Values for a label | Discovery — what services/namespaces |
| `series` | Find series matching selector | Check if a metric+labels exists |
| `rules` | Alerting and recording rules | See all configured rules |
| `alerts` | Firing/pending alerts | Active alert investigation |
| `tsdb_status` | Cardinality statistics | Top metrics/labels by series count |
| `top_queries` | Most frequent/slowest queries | Query performance investigation |
| `active_queries` | Currently running queries | Debug slow query |
| `metric_statistics` | Usage stats per metric | Find unused metrics |
| `explain_query` | Explain MetricsQL expression | Understand complex query |
| `prettify_query` | Format query | Readability |
| `documentation` | Search VM docs | Reference |

## Tempo MCP

| Tool | Purpose | When |
|------|---------|------|
| `traceql-search` | Search traces by attributes/duration/status | Find slow/error traces |
| `get-trace` | Retrieve specific trace by ID | Drill into known trace |
| `get-attribute-names` | List available attributes | Discovery before query |
| `get-attribute-values` | Values for an attribute | List services/endpoints |
| `traceql-metrics-instant` | Metric from traces (instant) | Aggregate at single point |
| `traceql-metrics-range` | Metric from traces (series) | Aggregate over time |
| `docs-traceql` | TraceQL documentation | Syntax reference |

## Grafana MCP (Loki + dashboards + alerting)

| Tool | Purpose | When |
|------|---------|------|
| `query_loki_logs` | Execute LogQL query | Search logs |
| `query_loki_stats` | Stream statistics (cheap) | Check if stream has data first |
| `query_loki_patterns` | Detected patterns | Find anomalous log patterns |
| `list_loki_label_names` | Available log labels | Discovery |
| `list_loki_label_values` | Values for a log label | Discovery |
| `search_dashboards` | Find dashboards | Locate relevant dashboard |
| `get_dashboard_by_uid` | Full dashboard JSON | Inspect panel queries |
| `alerting_manage_rules` | Alert rules CRUD | Check alert config |
| `alerting_manage_routing` | Notification policies | Debug alert routing |
| `get_annotations` | Dashboard annotations | Correlate with deploys |
| `check_datasources_health` | Datasource connectivity | Verify backends reachable |

## kubectl MCP (cluster health)

| Tool | Purpose | When |
|------|---------|------|
| `check_pod_health` | Pod health status | Quick pod check |
| `diagnose_pod_crash` | Crash loop analysis | Pod restarting |
| `get_logs` / `get_previous_logs` | Pod logs | Container output |
| `get_pod_metrics` | CPU/memory usage | Resource saturation |
| `get_events` | K8s events | OOMKill, scheduling failures |

## Cross-Signal Correlation Flow

```
Start: Metric spike observed
  │
  ├─ VictoriaMetrics: query the metric, confirm spike
  │
  ├─ Check exemplars → get trace_id from histogram data point
  │
  ├─ Tempo: get-trace with trace_id → identify slow/error span
  │
  ├─ Loki: query_loki_logs with trace_id → get log context
  │
  └─ Conclude: root cause identified from 3 independent signals
```

**Rule**: Never conclude from a single signal. Always cross-validate across metrics + traces + logs. ≥3 independent signals to assert root cause.
