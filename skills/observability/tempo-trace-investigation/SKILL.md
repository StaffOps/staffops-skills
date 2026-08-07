---
name: tempo-trace-investigation
description: "Investigate distributed traces using Tempo and TraceQL. Symptoms: high latency on a service, errors propagating across services, need to find which span in a request chain is slow, exemplar drill-down from a metric spike, or mapping service dependencies. Use TraceQL MCP tools (traceql-search, get-trace, get-attribute-names/values, traceql-metrics-instant/range)."
---

# Tempo Trace Investigation

## When to use this skill

- Latency investigation: which service/span is slow?
- Error propagation: where did the error originate?
- Dependency mapping: what calls what?
- Exemplar drill-down: metric spike → specific trace
- Cross-service request flow understanding
- Validate sampling: confirm errors/slow requests are retained (100% in PRD)

## When this skill does NOT apply

- Need to query metrics → use `victoriametrics-investigation`
- Need to search logs → use `loki-logql-patterns`
- Tempo backend is unhealthy → use `loki-tempo-self-metrics`
- Configuring trace-to-log/metric links → use `grafana-cross-signal-correlation`
- OTel pipeline dropping traces → use `otel-pipeline-troubleshooting`

## Step 1: Discover available attributes

Before building queries, check what's available in the data:

- `get-attribute-names` (scope: `resource` or `span`)
- `get-attribute-values` (e.g., `resource.service.name` → list all services)

Key attributes: `resource.service.name`, `resource.k8s.namespace.name`, `span.http.route`, `span.http.status_code`, `span.db.system`

## Step 2: Build the spanset selector

```traceql
# By service
{resource.service.name="my-service"}

# By service + condition
{resource.service.name="my-service" && duration > 1s}
{resource.service.name="my-service" && status = error}

# By endpoint
{span.http.route="/api/v1/users" && duration > 500ms}

# By namespace
{resource.k8s.namespace.name="dpm" && status = error}
```

## Step 3: Refine with structural queries (find WHERE in the chain)

```traceql
# Parent is gateway, child is slow (find downstream bottleneck)
{resource.service.name="gateway"} >> {duration > 2s}

# Database call is slow
{span.db.system="postgresql" && duration > 100ms}

# Trace passes through both services (dependency proof)
{resource.service.name="service-a"} && {resource.service.name="service-b"}
```

## Step 4: Compute metrics from traces (aggregate)

Use `traceql-metrics-instant` or `traceql-metrics-range` MCP tools:

```traceql
# Error rate by service
{status = error} | rate() by (resource.service.name)

# Latency distribution by service
{} | histogram_over_time(duration) by (resource.service.name)

# Request rate by endpoint
{resource.service.name="my-service"} | rate() by (span.http.route)
```

> ⚠️ Use `histogram_over_time` for latency distribution. `quantile_over_time` is NOT valid TraceQL — it's a PromQL function.

## Practical query cookbook (copy-paste)

### Find the slowest database calls in the last hour

```traceql
{span.db.system != nil && duration > 500ms} | rate() by (span.db.system, resource.service.name)
```

### Find all errors in a specific namespace

```traceql
{resource.k8s.namespace.name = "dpm" && status = error}
```

### Find traces where a specific service is the bottleneck (child slower than parent)

```traceql
{resource.service.name = "dpm-people-api"} >> {duration > 2s}
```

### Find HTTP 5xx responses on a specific endpoint

```traceql
{span.http.route = "/api/v1/people" && span.http.status_code >= 500}
```

### Find traces that pass through Redis and are slow

```traceql
{span.db.system = "redis" && duration > 100ms}
```

### Count traces by status code for a service (instant metric)

```traceql
{resource.service.name = "dpm-people-api"} | rate() by (span.http.status_code)
```

### Find gRPC failures

```traceql
{span.rpc.system = "grpc" && span.rpc.grpc.status_code != 0}
```

### Find traces with high span count (complex/chatty requests)

```traceql
{resource.service.name = "dpm-people-api"} | count() > 50
```

### Cross-service correlation: service A calling service B with errors

```traceql
{resource.service.name = "gateway" && status = ok} >> {resource.service.name = "dpm-people-api" && status = error}
```

### Find traces during a deploy window (correlate with annotations)

```traceql
# Use start/end time params on the MCP tool to narrow the window
{resource.service.name = "dpm-people-api" && duration > 1s}
# Set start="2026-08-06T14:00:00Z" end="2026-08-06T14:30:00Z"
```

## Step 5: Correlate with other signals

**Trace → Logs**: extract `trace_id` from trace, query in Loki:
```logql
{service_namespace="dpm"} | trace_id="<trace-id>"
```

**Metric → Trace**: exemplars in VictoriaMetrics histograms contain `traceID` — use `get-trace` with that ID.

**Alert → Traces**: get alert timeframe, query Tempo for that service + timeframe + condition.

## Expected output

The working TraceQL query plus what it proved. Example:
```
Query: {resource.service.name="dpm-people-api" && duration > 2s} >> {span.db.system="postgresql"}
Result: 12 traces in last 30m where PostgreSQL calls exceeded 2s. All show the same slow query on the enrichment table. Root span total duration 3.1s, DB span alone 2.7s.
```

## Decision tree

```
What are you investigating?
├── Slow requests → Step 2 (duration filter) + Step 3 (structural: find slow child)
├── Errors → Step 2 (status=error) + Step 3 (find originating service)
├── Specific trace from exemplar/log → get-trace with ID directly
├── Service dependencies → Step 3 (structural: A >> B, A && B)
├── Aggregate patterns → Step 4 (metrics from traces)
└── Trace not found → Check sampling (only errors + slow + 10% random kept in PRD)
```

## Sampling awareness

PRD tail sampling retains:
- 100% of error traces (status = ERROR)
- 100% of high-latency traces (duration > 1s)
- 10% probabilistic for normal traces
- 100% when `tracestate.debug=true`

If you can't find a trace, it may have been sampled out. Errors and slow requests are always kept.

## Related skills

- `loki-logql-patterns` — query logs for trace correlation
- `grafana-cross-signal-correlation` — configure exemplars, tracesToLogs
- `otel-pipeline-troubleshooting` — traces not arriving in Tempo
- `loki-tempo-self-metrics` — Tempo backend health metrics
