---
name: cardinality-explosion-finder
description: >
  Use when VictoriaMetrics is OOMing, vmselect queries are slow, or TSDB cardinality is
  growing unexpectedly. Runs a bundled Python script that analyzes TSDB status data (top
  metrics, labels, and label-value pairs by series count), identifies the explosion source,
  flags known problematic patterns (user_id, request_id, raw URLs), and recommends remediation.
  Requires sandbox. Collect TSDB status from VictoriaMetrics MCP first.
---

# Cardinality Explosion Finder (Executable)

## When to use this skill

- VictoriaMetrics vmselect OOMKilling or slow
- `vm_new_timeseries_created_total` rate spiking
- Total active series growing faster than expected
- Dashboard "Cardinality Explorer" shows sudden jumps
- A new service was deployed and series count exploded

## When this skill does NOT apply

- General VM troubleshooting → use `victoriametrics-investigation`
- Streaming aggregation configuration → use `streaming-aggregation`
- Known cardinality issue with remediation plan → use `vm-cardinality-management`
- Sandbox not enabled → this skill requires the sandbox environment

## Step 1: Detect the explosion (before collecting TSDB status)

Run these detection queries first to confirm cardinality is actually the problem:

```promql
# Is new series creation spiking? (THE primary signal)
rate(vm_new_timeseries_created_total[5m])
# Normal: < 500/sec. Warning: 500-1000. Critical: > 1000.

# Compare to baseline — is this a spike or organic growth?
rate(vm_new_timeseries_created_total[5m]) / rate(vm_new_timeseries_created_total[5m] offset 1d)
# > 2 = doubled from yesterday = likely explosion

# Total active series (are we in danger zone?)
vm_cache_entries{type="storage/metricName"}
# Context: 1M = healthy for medium cluster. 5M+ = large. 10M+ = potential pressure.

# TSID cache miss rate (consequence of high cardinality)
rate(vm_cache_misses_total{type="storage/tsid"}[5m]) / rate(vm_cache_requests_total{type="storage/tsid"}[5m])
# > 10% = cardinality is hurting performance

# Slow inserts (direct consequence — new series bypass cache, hit disk)
rate(vm_slow_row_inserts_total[5m]) / rate(vm_rows_inserted_total[5m])
# > 5% = actively degrading ingestion

# vmselect under pressure? (cardinality → slow queries → OOM)
max(vm_concurrent_select_current) / max(vm_concurrent_select_limit)
# > 0.7 with slow_queries growing = cardinality + query amplification
```

### Identifying WHEN the explosion started

```promql
# Overlay new_timeseries rate with deploy/change annotations
rate(vm_new_timeseries_created_total[5m])
# Use query_range with 24h window to see the step function (spike start)

# Correlate with scrape config changes (new targets added)
count(up) - count(up offset 1d)
# Positive = more scrape targets than yesterday
```

## Step 1b: Identify the offending metric/label using MCP tools

Use `tsdb_status` MCP tool (preferred — returns structured data):
```
→ tsdb_status(topN=20)
```

Or via instant queries to narrow down:
```promql
# Which metric family has the most series? (group by __name__)
topk(10, count by (__name__) ({__name__=~".+"}))
# WARNING: This is VERY expensive. Prefer tsdb_status MCP tool.

# Once you identify a suspect metric, check its label cardinality:
# → Use label_values MCP tool:
# label_values(label_name="pod", match='{__name__="suspect_metric"}')
# High count = that label is the unbounded dimension.
```

## Step 2: Collect TSDB status from VictoriaMetrics

```
→ VictoriaMetrics_MCP_tsdb_status(topN=20)
```

Or query directly:
```
→ query: vm_rows_inserted_total (check growth rate)
→ query: vm_new_timeseries_created_total (new series creation rate)
```

## Step 2: Write TSDB status to file

```bash
cat > /tmp/tsdb_status.json << 'EOF'
{
  "totalSeries": 2500000,
  "totalLabelValuePairs": 850000,
  "seriesCountByMetricName": [
    {"name": "http_server_request_duration_seconds_bucket", "value": 45000},
    {"name": "istio_requests_total", "value": 32000}
  ],
  "seriesCountByLabelName": [
    {"name": "pod", "value": 180000},
    {"name": "user_id", "value": 95000}
  ],
  "seriesCountByLabelValuePair": [
    {"name": "job=kubernetes-pods", "value": 120000},
    {"name": "namespace=dpm", "value": 45000}
  ]
}
EOF
```

## Step 3: Run the cardinality analyzer

```bash
sed -n '/^```python$/,/^```$/p' /aidevops/skills/user/cardinality-explosion-finder/references/cardinality-script.md | sed '1d;$d' > /tmp/cardinality.py
python3 /tmp/cardinality.py --data-file /tmp/tsdb_status.json
```

## Step 4: Interpret results

The script identifies:
- **CRITICAL** — known problematic patterns (`user_id`, `request_id`, `trace_id`, `email`, raw URLs)
- **HIGH** — disproportionate histograms (>10% of total) or non-histograms with >5% share
- **Top offender** — the single label or metric causing most bloat

### Common findings and fixes

| Finding | Fix |
|---------|-----|
| `user_id` as label | Remove from metrics, use traces/logs for per-user |
| Histogram with 45K series | Reduce bucket count or use streaming aggregation |
| Raw URL path as label | Switch to `http.route` (templated) |
| Non-histogram at 8% | Inspect label set — one label is unbounded |

## Step 5: Summarize findings

1. **Top offender** — which metric or label is causing the explosion
2. **Impact** — how many series it accounts for (% of total)
3. **Root cause** — why it's unbounded (new service, bad instrumentation, misconfigured scrape)
4. **Remediation** — specific fix (⚠️ RECOMMENDATION ONLY — read-only agent)
5. **Urgency** — is vmselect OOMing now (immediate) or trending (days)

## Decision tree

```
Cardinality growing or VM OOM?
├── Collect TSDB status (topN=20)
├── Run cardinality.py
├── Recommendations:
│   ├── CRITICAL (known bad pattern) → Fix immediately, likely a code change needed
│   ├── HIGH (disproportionate histogram) → streaming aggregation or bucket reduction
│   ├── HIGH (non-histogram >5%) → Find the unbounded label with label_values()
│   └── None found → Growth is organic; capacity planning, not explosion
├── Verify the fix target:
│   ├── label_values(__name__, metric="<offender>") → confirm series count
│   └── label_values(<suspected_label>, metric="<offender>") → confirm cardinality
└── Remediation path:
    ├── relabeling in scrape config (drop label) → streaming-aggregation skill
    ├── Code change (remove label from instrumentation) → developers
    └── metric_relabel_configs in vmagent → vm-cardinality-management skill
```

## Related skills

- `vm-cardinality-management` — remediation patterns (relabeling, drops)
- `streaming-aggregation` — pre-aggregate high-cardinality at scrape time
- `victoriametrics-self-metrics` — VM health and capacity signals
- `victoriametrics-investigation` — diagnosing slow queries from cardinality
