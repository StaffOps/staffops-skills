# VictoriaMetrics Investigation — Reference

## Cluster Architecture

```
vmagent (scrape + remote_write) → vminsert (routing) → vmstorage (persistence)
vmselect (query execution, fan-out to all vmstorage nodes)
```

| Component | Internal endpoint |
|-----------|------------------|
| vmselect | `vm-cluster-vmselect.monitoring:8481` |
| vminsert | `vm-cluster-vminsert.monitoring:8480` |

## Key Metrics

| Metric | Type | Normal Range | Investigation Threshold | Notes |
|--------|------|-------------|------------------------|-------|
| `vm_rows_inserted_total` | Counter | baseline-relative | Sudden drop to 0 = ingestion failure | Compare to 7d rate |
| `vm_slow_row_inserts_total` | Counter | ≈ 0 | > 1% of rows_inserted | TSID cache miss → disk I/O |
| `vm_rows_ignored_total` | Counter | 0 | > 0, check reason label | Rejected samples |
| `vm_concurrent_select_current` | Gauge | Well below limit | Near limit | Query saturation |
| `vm_slow_queries_total` | Counter | ≈ 0 | > 0 sustained | Queries exceeding threshold |
| `vm_cache_misses_total{type="storage/tsid"}` / requests | Ratio | < 5% | > 10% | New series churn |
| `vm_cache_misses_total{type="storage/metricName"}` / requests | Ratio | < 5% | > 10% | MetricName cache undersized |
| `vm_free_disk_space_bytes` | Gauge | > 50GB | < 10GB = readonly mode | Critical threshold |
| `vm_parts` | Gauge | Stable | Growing = merges not keeping up | Storage pressure |
| `vm_data_size_bytes` | Gauge | Slow growth | Rapid growth = cardinality or retention | Capacity |
| `vmagent_remotewrite_pending_data_bytes` | Gauge | Near 0, stable | Growing unbounded | vminsert backpressure |
| `vmagent_remotewrite_errors_total` | Counter | 0 | > 0 | Data loss (retries exhausted) |
| `vmagent_remotewrite_requests_total{status_code!="204"}` | Counter | 0 | > 0, check status_code | Write failures by type |

## vm_rows_ignored reasons

| Reason | Meaning | Fix |
|--------|---------|-----|
| `duplicate` | Same timestamp+labels written twice | Normal with HA vmagent; check dedup config |
| `out_of_order` | Timestamp older than last written | Clock skew or late-arriving data |
| `nan_value` | NaN sample | Source sending NaN (SDK bug or gauge reset) |
| `too_big_timestamp` | Future timestamp beyond threshold | Clock skew on source |

## MCP Tools for Investigation

| Tool | Use for |
|------|---------|
| `query` / `query_range` | Execute MetricsQL against VM |
| `tsdb_status` | Cardinality: top metrics, labels, label values |
| `top_queries` | Most expensive/frequent queries |
| `metric_statistics` | Which metrics are queried (find unused) |
| `active_queries` | Currently running queries |
| `alerts` | Firing/pending alerts |

## Common Issues

| Symptom | Likely Cause | First check |
|---------|-------------|-------------|
| Slow queries on specific metric | High cardinality | `tsdb_status` with match filter |
| `vm_slow_row_inserts` spike | TSID cache miss, new series churn | `vm_cache_misses{type="storage/tsid"}` rate |
| `vm_rows_ignored` increasing | Duplicates, NaN, out-of-order | Check `reason` label |
| vmagent pending_data growing | vminsert saturated | Check vminsert CPU + network |
| vmselect OOM | Query too broad | `vm_concurrent_select_current` + `vm_rows_read_per_query` (histogram p99) |
| Gaps in dashboards | Scrape target down or pipeline | Check `up{}` + pipeline health |

> ⚠️ Check vmstorage dedup timing before making changes — dedup runs periodically and temporarily increases resource usage. Do not confuse with a real problem.
