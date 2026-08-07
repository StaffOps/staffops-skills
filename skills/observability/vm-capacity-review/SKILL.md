---
name: vm-capacity-review
description: >
  Proactive VictoriaMetrics capacity and health review (Evaluation agent type).
  Produces a capacity report covering ingestion rate trend, storage growth and
  projected exhaustion date, cardinality state, TSID cache efficiency,
  query layer saturation, replication integrity, and retention vs actual usage.
  Each dimension reports headroom % and projected exhaustion date where applicable.
  NOT for active incidents — use victoriametrics-investigation for that.
---

# VictoriaMetrics Capacity Review

## When to use this skill

- Scheduled capacity review (monthly cadence recommended).
- Before onboarding a high-volume new service (pre-capacity check).
- After a significant change (new scrape targets, streaming aggregation rules, retention change).
- When asked "how much headroom does VM have?" or "when will we need to scale?"

## When this skill does NOT apply

- Active data loss or ingestion failure → use `victoriametrics-investigation` (reactive).
- Cardinality explosion in progress → use `vm-cardinality-management` (reactive).
- OTel pipeline dropping data before VM → use `otel-pipeline-troubleshooting`.
- Cost optimization of VM resources → use `cost-explorer` + this review's findings.

## Step 1: Ingestion rate trend and headroom

```promql
# Current ingestion rate (samples/sec)
sum(rate(vm_rows_inserted_total[5m]))

# 7-day average for comparison
sum(avg_over_time(rate(vm_rows_inserted_total[5m])[7d:1h]))

# 30-day average for growth trend
sum(avg_over_time(rate(vm_rows_inserted_total[5m])[30d:1h]))

# Growth rate (samples/sec per week)
# Formula: (current_rate - 30d_avg_rate) / 4 weeks ≈ weekly growth
```

**Pass**: Growth rate < 10% month-over-month. Current rate well below vminsert capacity.
**Finding (MEDIUM)**: Growth > 10%/month → project when vminsert saturation hits.
**Finding (HIGH)**: Current rate approaching `vm_concurrent_insert_capacity` (>70% saturation).

```promql
# Insert saturation (how close to vminsert capacity)
max(vm_concurrent_insert_current) / max(vm_concurrent_insert_capacity)
```

**Threshold**: < 70% = healthy (reasoning: 30% headroom absorbs daily peaks and burst onboarding). > 70% = plan scaling.

## Step 2: Storage capacity and projected exhaustion

```promql
# Current free disk per vmstorage node
vm_free_disk_space_bytes{job=~".*vmstorage.*"}

# Total disk (free + used)
vm_free_disk_space_bytes{job=~".*vmstorage.*"} + vm_data_size_bytes{job=~".*vmstorage.*"}

# Disk usage percentage
1 - (vm_free_disk_space_bytes / (vm_free_disk_space_bytes + vm_data_size_bytes))

# Growth rate over last 7 days (bytes/day)
# Use: (vm_data_size_bytes now - vm_data_size_bytes 7d ago) / 7
```

**Projected exhaustion formula**:
```
days_until_full = vm_free_disk_space_bytes / daily_growth_bytes
```

**Pass**: days_until_full > 90 days (3 months headroom). Reasoning: storage provisioning (EBS resize or PVC expansion) takes 1–2 weeks with testing; 90 days gives comfortable planning horizon.
**Finding (MEDIUM)**: 30–90 days until full → plan expansion within this quarter.
**Finding (HIGH)**: 15–30 days → urgent expansion needed.
**Finding (CRITICAL)**: < 15 days → immediate action required (VM enters readonly at near-zero free space).

## Step 3: Cardinality state

```promql
# Total active series (approximate)
vm_cache_entries{type="storage/metricName"}

# New series creation rate
rate(vm_new_timeseries_created_total[5m])

# Series churn (new series that are short-lived — high churn wastes TSID cache)
rate(vm_new_timeseries_created_total[5m]) - rate(vm_rows_inserted_total[5m]) * 0
# Better: use tsdb_status tool to get top offenders by series count
```

Use `tsdb_status` MCP tool to retrieve:
- Top 10 metric names by series count
- Top 10 labels by unique value count
- Top label=value pairs by series count

**Pass**: Total series growing < 5% week-over-week. No single metric > 100k series. No label with > 10k unique values.
**Finding (MEDIUM)**: Single metric > 100k series → candidate for streaming aggregation or relabeling.
**Finding (HIGH)**: New series rate > 1000/sec sustained → active cardinality issue, delegate to `vm-cardinality-management`.

## Step 4: Cache efficiency (TSID and metricName)

```promql
# TSID cache miss rate (THE critical efficiency metric)
rate(vm_cache_misses_total{type="storage/tsid"}[30m])
/ rate(vm_cache_requests_total{type="storage/tsid"}[30m])

# metricName cache miss rate
rate(vm_cache_misses_total{type="storage/metricName"}[30m])
/ rate(vm_cache_requests_total{type="storage/metricName"}[30m])

# Slow inserts (direct consequence of TSID cache misses — disk lookup per insert)
rate(vm_slow_row_inserts_total[30m]) / rate(vm_rows_inserted_total[30m])
```

**Pass**: TSID miss rate < 5%, slow inserts < 1% of total. Reasoning: TSID cache is the hot path; misses force disk I/O per sample, degrading ingestion throughput by 10–100x per miss.
**Finding (MEDIUM)**: TSID miss rate 5–10% → cache may be undersized or cardinality churn is moderate.
**Finding (HIGH)**: TSID miss rate > 10% or slow inserts > 5% → cache undersized relative to active series count, or cardinality explosion in progress.

Remediation formula for cache sizing:
```
recommended_cache_size = vm_cache_entries{type="storage/tsid"} * 1.5
```

## Step 5: Query layer saturation

```promql
# Current concurrent queries vs limit
max(vm_concurrent_select_current{job=~".*vmselect.*"})
max(vm_concurrent_select_limit{job=~".*vmselect.*"})

# Saturation ratio
max(vm_concurrent_select_current) / max(vm_concurrent_select_limit)

# Slow queries rate
sum(rate(vm_slow_queries_total[30m]))
```

Use `top_queries` MCP tool to identify:
- Most frequently executed queries
- Queries with highest average duration
- Queries consuming most total execution time

**Pass**: Saturation < 50%, slow queries < 1/min. Reasoning: 50% leaves headroom for dashboard bursts (someone opening a 12-panel dashboard = 12 concurrent queries).
**Finding (MEDIUM)**: Saturation 50–70% or slow queries 1–5/min → identify expensive queries via `top_queries`.
**Finding (HIGH)**: Saturation > 70% or slow queries > 5/min → scale vmselect or add recording rules.

## Step 6: Replication and deduplication integrity

```promql
# Hard data loss — rows dropped on overload (permanent)
increase(vm_rpc_rows_dropped_on_overload_total[24h])

# Replication gap — data written to fewer replicas than RF
increase(vm_rpc_rows_incompletely_replicated_total[24h])

# RPC connection errors (transient but risky under replication)
rate(vm_rpc_connection_errors_total[30m])

# Dedup metrics (if deduplication is enabled)
rate(vm_deduplicated_samples_total[30m])
```

**Pass**: `vm_rpc_rows_dropped_on_overload_total` increase = 0 over 24h, RPC errors < 1/min transient.
**Finding (CRITICAL)**: ANY `vm_rpc_rows_dropped_on_overload_total` increase > 0 → data permanently lost, investigate vmstorage health. Check `vm_rpc_vmstorage_is_reachable` for which node.
**Finding (MEDIUM)**: `vm_rpc_rows_incompletely_replicated_total` > 0 → replication degraded (data exists but not fully replicated). RPC errors > 0 sustained → network instability between vminsert and vmstorage.

## Step 7: Retention vs actual usage

```promql
# Current retention setting (check helm values or vmstorage flags)
# Typically: -retentionPeriod=90d (check via vmstorage logs or config)
```

Use `metric_statistics` MCP tool to identify:
- Metrics with 0 queries in the last 30 days (stored but never read)
- Metrics queried < 5 times in 30 days (rarely used)

Use `tsdb_status` to get storage breakdown by metric.

**Analysis**:
- If >30% of stored data is never queried → retention is paying to store waste.
- Calculate cost of unused storage: `unused_bytes × $/GB/month`

**Pass**: >70% of stored metrics are actively queried. Retention matches actual dashboard/alert lookback windows.
**Finding (MEDIUM)**: 30–50% of data never queried → consider reducing retention for low-value metrics via per-metric retention flags, or add `metric_relabel_configs` to drop at source.
**Finding (LOW)**: < 30% unused but some obvious waste (e.g., DEV metrics at 90d retention when 7d suffices).

## Step 8: Produce the capacity report

```
## VictoriaMetrics Capacity Review — [date]

### Summary

| Dimension | Status | Current value | Headroom | Projected exhaustion |
|-----------|--------|---------------|----------|---------------------|
| Ingestion rate | PASS/FINDING | X samples/sec | Y% to limit | [date if >70%] |
| Storage | PASS/FINDING | X% disk used | Y days until full | [date] |
| Cardinality | PASS/FINDING | X total series, Y new/sec | Z% of safe ceiling | — |
| Cache efficiency | PASS/FINDING | TSID miss X%, slow inserts Y% | — | — |
| Query layer | PASS/FINDING | X% saturation, Y slow/min | Z% headroom | — |
| Replication | PASS/FINDING | rows_lost=X, rpc_errors=Y/min | — | — |
| Retention usage | PASS/FINDING | X% actively queried | — | — |

### Findings (ranked by severity)

1. [CRITICAL/HIGH/MEDIUM]: [description] — measured X vs threshold Y
   - Recommendation: [action] ⚠️ RECOMMENDATION ONLY — read-only agent, a human executes
   - Arithmetic: [show the math — e.g., "at 50GB/day growth, 200GB free = 4 days"]
   
2. ...

### Dimensions with no findings

- [Dimension N]: PASS — [measured value] well within threshold [value]

### Scaling recommendations (if applicable)

| Component | Current | Recommended | Reasoning | Timeline |
|-----------|---------|-------------|-----------|----------|
| vmstorage PVC | 500Gi | 1Ti | 45 days at current growth | ⚠️ This quarter |
| vmselect replicas | 3 | 5 | Saturation at 68% | ⚠️ Next sprint |

---
**Overall VM health**: HEALTHY | PLAN SCALING | URGENT ACTION
**Budget consumed**: [per investigation-cost-guardrail]
**Next recommended review**: [date — typically 30 days]
```

## Decision tree

```
Start VM capacity review
├── Step 1: Ingestion growing >10%/month? → Flag + project saturation date
├── Step 2: Disk < 90 days to full? → Flag + severity by urgency
├── Step 3: Cardinality: new series > 1000/sec? → Delegate vm-cardinality-management
├── Step 4: TSID miss > 5%? → Cache undersized → recommend increase
├── Step 5: Query saturation > 50%? → Identify expensive queries → recommend recording rules or scale
├── Step 6: rows_lost > 0? → CRITICAL → immediate investigation
├── Step 7: >30% data never queried? → Retention waste → recommend per-metric retention
└── Compile report with arithmetic, dates, and ranked recommendations
```

## Quick sizing formulas (reference)

### Storage sizing

```
storage_bytes_per_day = ingestion_rate_samples_per_sec × 86400 × bytes_per_sample
  where bytes_per_sample ≈ 1.5–2.0 (VM compressed, with index overhead)

total_storage_needed = storage_bytes_per_day × retention_days × replication_factor
  typical: 800k samples/sec × 86400 × 1.7 × 90d × 2 (RF) ≈ 18 TB

days_until_full = free_disk_bytes / storage_bytes_per_day
```

### Memory sizing

```
vmstorage_ram = active_series × 1KB (approximate: each active series ~1KB in TSID cache + index)
  example: 3M active series → ~3 GB RAM for cache alone
  recommended: vmstorage RAM = active_series × 1.5 KB (headroom for hot data)

vmselect_ram = depends on query complexity. Rule of thumb:
  base: 2 GB + (concurrent_queries × avg_series_per_query × 200 bytes)
  typical: 2GB + (20 queries × 10k series × 200B) = 2GB + 40MB = safe at 4GB
  heavy dashboards: 8–16 GB per vmselect replica

vminsert_ram = minimal (stateless). 1–2 GB per replica is typical.
```

### CPU sizing

```
vminsert_cpu = ingestion_rate / 200k samples/sec/core (approximate)
  example: 800k samples/sec → 4 cores minimum

vmselect_cpu = depends on query volume and complexity
  rule of thumb: 1 core per 5 concurrent heavy queries

vmstorage_cpu = merge operations dominate. 2–4 cores for moderate workloads.
  scale if vm_merge_duration_seconds_total rate is high.
```

### Scaling triggers (when to add replicas)

| Component | Scale when | Add |
|-----------|-----------|-----|
| vminsert | `concurrent_insert_current / capacity > 70%` | +1 replica |
| vmselect | `concurrent_select_current / limit > 60%` OR slow_queries > 5/min | +1 replica |
| vmstorage | disk < 90 days to full OR TSID miss > 10% | +1 node (rebalance) |
| vmagent | `pending_data_bytes` growing sustained | +1 shard (via `-promscrape.cluster`) |

## Related skills

- `victoriametrics-self-metrics` — full metric reference (all vm_* metric names)
- `victoriametrics-investigation` — reactive investigation for active issues
- `vm-cardinality-management` — cardinality deep-dive when Step 3 flags
- `streaming-aggregation` — remediation for cardinality via pre-aggregation
- `investigation-cost-guardrail` — bounds this review to Evaluation budget tier (8 min / $4.00)
