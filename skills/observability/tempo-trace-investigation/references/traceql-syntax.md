# TraceQL Syntax Reference

## Spanset Selectors

```traceql
# Basic: { <conditions> }
{resource.service.name="api" && duration > 1s}
{span.http.status_code >= 500}
{status = error}
{duration > 500ms && duration < 5s}
```

## Attribute Scopes

| Scope | Prefix | Examples |
|-------|--------|---------|
| Resource | `resource.` | `resource.service.name`, `resource.k8s.namespace.name` |
| Span | `span.` | `span.http.route`, `span.db.statement`, `span.http.status_code` |
| Intrinsic | (none) | `duration`, `status`, `name`, `kind` |

## Structural Operators

| Operator | Meaning | Example |
|----------|---------|---------|
| `>>` | Descendant (any depth) | `{service="gw"} >> {duration > 2s}` |
| `>` | Direct child | `{service="gw"} > {span.db.system="pg"}` |
| `~` | Sibling | `{service="a"} ~ {service="b"}` |
| `&&` | Both exist in trace | `{service="a"} && {service="b"}` |

## Metrics Functions (Tempo 2.4+)

| Function | Use | Example |
|----------|-----|---------|
| `rate()` | Count per second | `{status=error} \| rate() by (resource.service.name)` |
| `count_over_time()` | Total count | `{} \| count_over_time() by (resource.service.name)` |
| `histogram_over_time(field)` | Distribution | `{} \| histogram_over_time(duration) by (resource.service.name)` |
| `min_over_time(field)` | Min | `{} \| min_over_time(duration)` |
| `max_over_time(field)` | Max | `{} \| max_over_time(duration)` |

> ⚠️ `quantile_over_time` is NOT valid TraceQL. Use `histogram_over_time` for latency analysis.

## Pipeline Operations

```traceql
# Select specific fields in output
{resource.service.name="api"} | select(duration, span.http.route)

# Aggregate
{status = error} | rate() by (resource.service.name)
```

## Common Patterns

```traceql
# Slow requests
{resource.service.name="my-service" && duration > 1s}

# Errors on specific endpoint
{span.http.route="/api/v1/users" && status = error}

# Find downstream bottleneck
{resource.service.name="gateway"} >> {duration > 2s}

# Database slow queries
{span.db.system="postgresql" && duration > 100ms}

# Specific trace
{traceID="abc123def456"}
```

## Tempo Health Metrics (verify backend is working)

| Metric | Normal | Investigate |
|--------|--------|------------|
| `tempo_distributor_spans_received_total` | > 0 | = 0 (no ingestion) |
| `tempo_discarded_spans_total` | 0 | > 0, check `reason` label |
| `tempo_query_frontend_request_duration_seconds` | p99 < 10s | p99 > 30s |

Discard reasons:
- `trace_too_large` — trace has too many spans (usually a loop)
- `rate_limited` — ingestion rate exceeded limits

## Sampling Awareness (PRD)

| Condition | Retention |
|-----------|-----------|
| status = ERROR | 100% kept |
| duration > 1s | 100% kept |
| tracestate.debug=true | 100% kept |
| Normal traces | 10% probabilistic |
| DEV/HML/LOCAL | 100% (no sampling) |
