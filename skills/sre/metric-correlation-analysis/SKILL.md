---
name: metric-correlation-analysis
description: >
  Use when multiple metrics anomaly at the same time and you need to determine if they
  share a common cause. Runs a bundled Python script that detects Z-score anomalies per
  metric and finds temporal correlations across series. Requires sandbox. Load after
  collecting data from VictoriaMetrics MCP — this skill COMPUTES over collected data,
  it does not query backends directly.
---

# Metric Correlation Analysis (Executable)

## When to use this skill

- Multiple alerts fired within minutes of each other
- Latency and error rate spiked simultaneously across services
- Need to determine if anomalies are correlated (common cause) or independent
- Have collected metric data from VictoriaMetrics and need statistical analysis

## When this skill does NOT apply

- Single metric investigation → use `victoriametrics-investigation`
- Need to query metrics (data collection) → use MCP tools first, then this skill
- OTel pipeline health → use `collector-internal-metrics`
- Sandbox not enabled → this skill requires the sandbox environment

## Step 1: Collect metric data via MCP tools

Before running the correlation script, collect the relevant metrics. Use the VictoriaMetrics MCP to query each suspected metric over the same time range:

```
→ VictoriaMetrics_MCP_query_range(query="rate(http_server_request_duration_seconds_count{service_namespace='dpm'}[5m])", start="2h ago", step="1m")
→ VictoriaMetrics_MCP_query_range(query="rate(otelcol_exporter_send_failed_log_records[5m])", start="2h ago", step="1m")
→ VictoriaMetrics_MCP_query_range(query="mongodb_connections{state='current'}", start="2h ago", step="1m")
```

## Step 2: Write data to a file for the script

Write the collected data as JSON:

```bash
cat > /tmp/metrics.json << 'EOF'
{
  "metrics": [
    {"name": "http_server_request_duration_seconds_count", "labels": {"service_namespace": "dpm"}, "values": [[1722960000, "142.5"], [1722960060, "145.2"], ...]},
    {"name": "otelcol_exporter_send_failed_log_records", "labels": {}, "values": [[1722960000, "0"], [1722960060, "2840"], ...]},
    {"name": "mongodb_connections", "labels": {"state": "current"}, "values": [[1722960000, "450"], [1722960060, "890"], ...]}
  ]
}
EOF
```

## Step 3: Run the correlation analysis

The script is in `references/correlate-script.md` as a Python code block. The agent copies it to the sandbox filesystem and executes it:

```bash
# Copy the script from the skill reference to a runnable file
cat /aidevops/skills/user/metric-correlation-analysis/references/correlate-script.md | \
  sed -n '/^```python$/,/^```$/p' | sed '1d;$d' > /tmp/correlate.py

# Execute
python3 /tmp/correlate.py --data-file /tmp/metrics.json --threshold 2.0 --window 300
```

Parameters:
- `--threshold` — Z-score threshold for anomaly detection (default: 2.0 = 2 standard deviations)
- `--window` — seconds within which anomalies count as correlated (default: 300 = 5 minutes)

## Step 4: Interpret the output

The script outputs structured JSON:

```json
{
  "correlations": [
    {
      "metric_a": "mongodb_connections{state=\"current\"}",
      "metric_b": "http_server_request_duration_seconds_count{service_namespace=\"dpm\"}",
      "time_a": "2026-08-06T14:02:00",
      "time_b": "2026-08-06T14:03:00",
      "delta_seconds": 60,
      "zscore_a": 4.2,
      "zscore_b": 3.8
    }
  ],
  "conclusion": {
    "correlated_pairs": 2,
    "summary": "2 pairs with co-occurring anomalies within 300s."
  }
}
```

**Interpretation**:
- `delta_seconds` close to 0 → simultaneous (likely same root cause)
- metric_a anomaly BEFORE metric_b → possible causation direction (A caused B)
- High zscore on both → strong signal, not noise
- No correlations → anomalies are independent (different root causes)

## Step 5: Summarize findings

1. **Status** — correlated / independent / insufficient data
2. **Root cause hypothesis** — which metric anomaly came FIRST (potential cause)
3. **Correlated pairs** — which metrics moved together (blast radius)
4. **Confidence** — number of correlated pairs + zscore strength
5. **Recommended next step** — trace the earliest anomaly to its source

## Decision tree

```
Multiple metrics anomaly simultaneously?
├── Collected data from VictoriaMetrics MCP? 
│   ├── Yes → Write to file, run correlate.py
│   └── No → Collect data first (Step 1)
├── Correlations found?
│   ├── Yes, delta < 60s → Same root cause likely, investigate the earliest
│   ├── Yes, delta 60-300s → Possible cascade, trace the chain
│   └── No → Independent failures, investigate separately
└── Strongest correlation points to?
    ├── Deploy metric → check ArgoCD/gitops for recent deploy
    ├── Database metric → check backing-services-metrics
    ├── Pipeline metric → check collector-internal-metrics
    └── Resource metric → check k8s-workload-metrics
```

## Related skills

- `victoriametrics-investigation` — query individual metrics
- `backing-services-metrics` — MongoDB/Redis/PostgreSQL health
- `incident-triage` — severity classification after correlation found
- `root-cause-analysis` — formal RCA with ≥3 independent signals
