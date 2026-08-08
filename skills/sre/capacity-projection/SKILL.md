---
name: capacity-projection
description: "Use when assessing whether storage, ingestion rate, or resource usage will exhaust capacity before the next review cycle. Runs a bundled Python script that fits linear regression on time-series data and projects exhaustion dates per dimension. Covers VictoriaMetrics storage, Kafka partition size, EBS volumes, and any monotonically growing metric. Requires sandbox."
---

# Capacity Projection (Executable)

## When to use this skill

- Weekly capacity review (scheduled trigger)
- Storage growing faster than expected
- Need to project "when will disk X be full?"
- Planning capacity expansion timeline
- Justifying infrastructure spend with data

## When this skill does NOT apply

- Current saturation/OOM investigation → use `victoriametrics-self-metrics` or `k8s-workload-metrics`
- Cardinality explosion (series count, not storage) → use `cardinality-explosion-finder`
- Cost investigation → use `cost-explorer`
- Sandbox not enabled → this skill requires the sandbox environment

## Step 1: Collect trend data (7-30 days)

Query VictoriaMetrics for the dimension(s) to project. Use a range query with daily granularity:

```
→ query_range: vm_data_size_bytes{job="vmstorage"} / 1e9  (storage in GB, 30d, step=1h)
→ query_range: rate(vm_rows_inserted_total[1h])  (ingestion rate trend, 30d, step=1h)
→ query_range: kubelet_volume_stats_used_bytes / kubelet_volume_stats_capacity_bytes  (PVC fill %, 7d)
```

## Step 2: Write data file

```bash
cat > /tmp/capacity_data.json << 'EOF'
{
  "dimensions": [
    {
      "name": "VictoriaMetrics storage (vmstorage-0)",
      "current_value": 850,
      "unit": "GB",
      "threshold": 1000,
      "values": [[1722200000, "780"], [1722286400, "785"], [1722372800, "792"], ...]
    },
    {
      "name": "Kafka partition otlp_spans (total)",
      "current_value": 45,
      "unit": "GB",
      "threshold": 100,
      "values": [[1722200000, "38"], [1722286400, "39.2"], ...]
    }
  ]
}
EOF
```

## Step 3: Run the projection

```bash
sed -n '/^```python$/,/^```$/p' /aidevops/skills/user/capacity-projection/references/projection-script.md | sed '1d;$d' > /tmp/capacity.py
python3 /tmp/capacity.py --data-file /tmp/capacity_data.json
```

## Step 4: Interpret results

| Urgency | Meaning | Action |
|---------|---------|--------|
| `HEALTHY` | >90 days headroom | No action |
| `WATCH` | 30-90 days | Plan expansion this quarter |
| `WARNING` | 7-30 days | ⚠️ Create ticket, expand within month |
| `CRITICAL` | <7 days | ⚠️ Immediate action required |
| `CRITICAL_NOW` | Already breached | ⚠️ Investigate immediately |

Key fields: `days_to_exhaustion`, `growth_per_day`, `r_squared` (confidence: >0.8 = HIGH).

## Step 5: Summarize findings

1. **Worst dimension** — which resource exhausts first
2. **Days to exhaustion** — projected date at current growth rate
3. **Growth rate** — units/day (is it accelerating?)
4. **Confidence** — R² of the linear fit (LOW = noisy data, re-check with longer window)
5. **Recommendation** — expand capacity (⚠️ RECOMMENDATION ONLY) or "healthy, no action"

## Decision tree

```
Capacity concern detected
├── Which dimension is growing?
│   ├── Storage (disk/PV) → check retention policies + growth rate
│   ├── Ingestion (samples/s, logs/s) → check new workloads or cardinality spike
│   ├── Memory (RSS/heap) → check cache hit ratio + leak signals
│   └── CPU (cores) → check concurrency + query complexity
├── Is it urgent? (< 7 days to exhaustion)
│   ├── Yes → immediate mitigation: scale up, drop low-value data, throttle
│   └── No → planned: model trend, set budget, schedule expansion
└── Action
    ├── Short-term: vertical scale or horizontal replicas
    └── Long-term: retention reduction, streaming aggregation, architecture change
```

## Related skills

- `vm-capacity-review` — scheduled VictoriaMetrics capacity report (non-executable)
- `victoriametrics-self-metrics` — current VM health signals
- `karpenter-metrics` — node capacity and provisioning
- `cost-explorer` — cost justification for expansion
