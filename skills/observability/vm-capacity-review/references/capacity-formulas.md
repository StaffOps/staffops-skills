# VictoriaMetrics Capacity Formulas

## Storage exhaustion projection

```
daily_growth_bytes = (vm_data_size_bytes[now] - vm_data_size_bytes[7d_ago]) / 7
days_until_full = vm_free_disk_space_bytes / daily_growth_bytes
exhaustion_date = today + days_until_full
```

### Severity mapping

| Days until full | Severity | Action timeline |
|-----------------|----------|----------------|
| > 90 days | PASS | No action needed, review next month |
| 30–90 days | MEDIUM | Plan expansion this quarter |
| 15–30 days | HIGH | Urgent — initiate PVC expansion now |
| < 15 days | CRITICAL | Emergency — VM will go readonly |

### Cost of inaction

When vmstorage reaches near-zero free space:
1. Enters readonly mode — ALL writes fail
2. vmagent buffers fill → `pending_data_bytes` grows
3. After vmagent buffer exhaustion → permanent data loss
4. Recovery requires PVC resize + pod restart + buffer drain (30+ min)

## Ingestion headroom projection

```
current_rate = sum(rate(vm_rows_inserted_total[5m]))
weekly_growth = (current_rate - rate_30d_ago) / 4
monthly_growth_pct = weekly_growth * 4 / rate_30d_ago * 100
weeks_to_saturation = (vm_concurrent_insert_capacity - vm_concurrent_insert_current) / weekly_growth_in_concurrency
```

### vminsert scaling threshold

| Insert saturation % | Status | Action |
|--------------------|--------|--------|
| < 50% | Healthy | No action |
| 50–70% | Monitor | Review monthly |
| 70–85% | Plan scaling | Add vminsert replica within 2 weeks |
| > 85% | Urgent | Scale NOW — burst traffic will saturate |

## Cache sizing formula

```
recommended_tsid_cache = vm_cache_entries{type="storage/tsid"} * 1.5
# 1.5x multiplier: accounts for churn (some entries expire while new ones enter)

recommended_metricname_cache = vm_cache_entries{type="storage/metricName"} * 1.3
```

### Cache efficiency targets

| Cache type | Target miss rate | Impact of misses |
|-----------|-----------------|------------------|
| storage/tsid | < 5% | Each miss = disk lookup per INSERT (10–100x slower) |
| storage/metricName | < 3% | Each miss = extra disk read per QUERY |
| indexdb/tagFilters | < 10% | Each miss = index scan (slower label matching) |

## Query layer capacity

```
effective_capacity = vm_concurrent_select_limit × vmselect_replica_count
current_demand_peak = max_over_time(sum(vm_concurrent_select_current)[24h:1m])
headroom_pct = (1 - current_demand_peak / effective_capacity) * 100
```

### Dashboard burst estimation

A typical Grafana dashboard with N panels fires N concurrent queries on load:
- Standard dashboard: 6–12 panels = 6–12 concurrent queries
- Heavy dashboard: 20+ panels = 20+ concurrent queries
- Multiple users opening dashboards simultaneously = multiplicative

**Planning rule**: ensure `effective_capacity > 3 × max single dashboard burst`

## Retention cost analysis

```
storage_cost_per_gb_month = [EBS gp3 cost in region, typically $0.08/GB/month]
unused_data_gb = total_data_gb × (1 - pct_actively_queried / 100)
monthly_waste = unused_data_gb × storage_cost_per_gb_month
annual_waste = monthly_waste × 12
```

### Metric usage classification

| Query count (30d) | Classification | Recommendation |
|-------------------|---------------|----------------|
| 0 | Dead metric | Drop at source or reduce retention to 7d |
| 1–5 | Rarely used | Consider 30d retention |
| 6–50 | Moderately used | Keep current retention |
| > 50 | Actively used | Keep full retention |

Use `metric_statistics` MCP tool with `le=0` to find metrics never queried.
