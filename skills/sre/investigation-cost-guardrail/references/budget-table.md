# Investigation Budget Table

## Cost model

| Unit | Cost |
|------|------|
| Per second | $0.0083 |
| Per minute | $0.50 |
| Per hour | $30.00 |
| Per MCP query (~avg 12s) | ~$0.10 |

## Budget ceilings by severity

| Severity | Max time | Max cost | Max queries | Budget exhaustion signal |
|----------|----------|----------|-------------|------------------------|
| P1 | 10 min | $5.00 | 25–30 | 80% = 8 min → start wrapping up |
| P2 | 7 min | $3.50 | 18–22 | 80% = 5.5 min → start wrapping up |
| P3 | 4 min | $2.00 | 10–14 | 80% = 3.2 min → start wrapping up |
| P4 | 2 min | $1.00 | 5–8 | 80% = 1.6 min → start wrapping up |
| Eval | 8 min | $4.00 | 20–25 | 80% = 6.4 min → start wrapping up |

## Concurrency impact

| Concurrent investigations | Effective quota remaining | Risk |
|---------------------------|--------------------------|------|
| 1–3 | 7–9 slots free | Normal operation |
| 4–6 | 4–6 slots free | Monitor — no new P4 investigations |
| 7–9 | 1–3 slots free | Critical — only P1/P2 should proceed |
| 10 | 0 slots free | Starved — queue new requests |

## Query cost reference (approximate)

| Query type | Typical duration | Relative cost |
|-----------|-----------------|---------------|
| `kubectl get pods -n <ns>` | 3–5s | Low |
| `query` (instant, single metric) | 4–8s | Low |
| `query_range` (1h, step=1m) | 6–12s | Medium |
| `query_range` (24h, step=1m) | 15–30s | High |
| `query_range` (30d, step=5m) | 30–60s | Very High |
| `traceql-search` (30 min window) | 8–15s | Medium |
| `traceql-search` (no time bound) | 30–120s | Extreme |
| `query_loki_logs` (limit=10) | 5–10s | Low |
| `query_loki_logs` (limit=100, 24h) | 15–30s | High |
| `tsdb_status` | 8–15s | Medium |
| `list_prometheus_metric_names` (no regex) | 10–20s | High |
