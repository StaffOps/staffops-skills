---
name: victoriametrics-investigation
description: >
  Diagnose VictoriaMetrics cluster issues — slow queries, ingestion bottlenecks,
  cache misses, storage pressure, remote_write backpressure from vmagent.
  Symptoms: dashboard queries timing out, vmselect OOMKilled, vmagent
  pending_data_bytes growing, vm_slow_row_inserts spiking, gaps in metric data.
  Cluster: vminsert/vmselect/vmstorage + vmagent.
---

# VictoriaMetrics Investigation

## When to use this skill

- Dashboard queries timing out or returning partial data
- vmselect pods OOMKilled or hitting concurrent query limits
- `vm_slow_row_inserts_total` spiking (TSID cache misses)
- `vmagent_remotewrite_pending_data_bytes` growing (backpressure)
- Gaps in metric dashboards (ingestion failure)
- `vm_rows_ignored_total` increasing (samples rejected)

## When this skill does NOT apply

- High cardinality is the suspected root cause → use `vm-cardinality-management`
- OTel pipeline dropping data before VM → use `otel-pipeline-troubleshooting`
- Need to configure streaming aggregation → use `streaming-aggregation`
- VMAlert rule evaluation issues → use `vmalert-configuration`

## Quick diagnostic procedure (run in order, stop at first failure)

Execute these sequentially. Each check builds on the previous. Stop investigating deeper when you find the broken layer.

```promql
# 1. Is VM alive and accepting writes?
up{job=~".*vminsert.*"}
# Expected: 1 for all instances. 0 = vminsert down.

# 2. Is data flowing in?
sum(rate(vm_rows_inserted_total[5m]))
# Expected: > 0. If 0 = nothing being written. Check upstream (vmagent/OTel).

# 3. Are writes healthy? (slow inserts = TSID miss = disk I/O per sample)
sum(rate(vm_slow_row_inserts_total[5m])) / sum(rate(vm_rows_inserted_total[5m]))
# Expected: < 0.01 (1%). If > 5% = cardinality or cache problem.

# 4. Are samples being rejected?
sum(rate(vm_rows_ignored_total[5m])) by (reason)
# Expected: 0. Non-zero by reason tells you exactly what's wrong.

# 5. Is vmagent backing up?
max(vmagent_remotewrite_pending_data_bytes)
# Expected: near 0. Growing = vminsert can't accept fast enough.

# 6. Is the query layer saturated?
max(vm_concurrent_select_current) / max(vm_concurrent_select_limit)
# Expected: < 0.5. > 0.7 = queries queuing, dashboards slow.

# 7. Disk space emergency check
min(vm_free_disk_space_bytes{job=~".*vmstorage.*"}) / 1024 / 1024 / 1024
# Returns GB free. < 10 GB = CRITICAL (VM goes readonly).
```

## Common patterns and their root causes

| Symptom | Query | Root cause |
|---------|-------|-----------|
| Dashboard gaps | `sum(rate(vm_rows_inserted_total[5m]))` = 0 for period | Upstream stopped writing |
| Slow dashboards | `vm_concurrent_select_current / limit > 0.7` | Query saturation → scale vmselect or add recording rules |
| vmselect OOM | `top_queries` MCP tool | Unbounded query (no label filter, huge range) |
| vmagent pending growing | `vmagent_remotewrite_pending_data_bytes` | vminsert saturated → scale vminsert |
| Slow inserts spike | `rate(vm_slow_row_inserts_total[5m])` | New series churn (cardinality explosion) |
| Samples ignored | `vm_rows_ignored_total` by reason | `duplicate`: dedup working. `out_of_order`: clock skew or double-write |
| High RAM on vmstorage | `vm_cache_entries{type="storage/tsid"}` | Cache holding too many entries → series count too high |

## Step 1: Check ingestion health (vminsert)

```promql
sum(rate(vm_rows_inserted_total[5m]))
sum(rate(vm_slow_row_inserts_total[5m]))
sum(rate(vm_rows_ignored_total[5m])) by (reason)
```

- **Normal**: slow_inserts ≈ 0, ignored ≈ 0
- **Degraded**: slow_inserts > 1% of inserted → new series churn or cache undersized
- **Critical**: ignored growing → check `reason` label (duplicate, out_of_order, nan_value)

## Step 2: Check query performance (vmselect)

```promql
vm_concurrent_select_current{job=~".*vmselect.*"}
sum(rate(vm_slow_queries_total[5m]))
```

Use `top_queries` MCP tool to identify expensive queries.

- **Normal**: concurrent_select well below limit, slow_queries ≈ 0
- **Critical**: near limit → queries queueing, dashboards timing out

## Step 3: Check cache health (vmstorage)

```promql
rate(vm_cache_misses_total{type="storage/tsid"}[5m])
/ rate(vm_cache_requests_total{type="storage/tsid"}[5m])
```

- **Normal**: miss rate < 5%
- **Degraded**: > 10% → new series churn too high or cache undersized

## Step 4: Check storage pressure

```promql
vm_free_disk_space_bytes{job=~".*vmstorage.*"}
vm_parts{job=~".*vmstorage.*"}
```

- **Critical**: free_disk < 10GB → VM enters readonly mode, all writes fail
- **Warning**: parts growing = merges not keeping up

## Step 5: Check remote write (vmagent → vminsert)

```promql
vmagent_remotewrite_pending_data_bytes
sum(rate(vmagent_remotewrite_errors_total[5m]))
sum(rate(vmagent_remotewrite_requests_total{status_code!="204"}[5m])) by (status_code)
```

- **Normal**: pending stable/near 0, errors = 0
- **Critical**: pending growing = backpressure; errors > 0 = data loss after retries

## Step 6: Summarize findings

1. **Status** — healthy / degraded / critical
2. **Root cause hypothesis** — cite observed values (e.g., "TSID cache miss rate 18%, slow_inserts 4%, correlates with 50k new series from istio_requests_total")
3. **Recommended remediation** — ranked:
   - Use `tsdb_status` to identify cardinality offenders
   - Use `top_queries` to find expensive queries
   - ⚠️ RECOMMENDATION ONLY — read-only agent, a human executes: Increase vmstorage cache flags
   - ⚠️ RECOMMENDATION ONLY — read-only agent, a human executes: Scale vmselect replicas
   - ⚠️ RECOMMENDATION ONLY — read-only agent, a human executes: Add streaming aggregation
4. **Confidence** — ≥3 signals to assert root cause

## Decision tree

```
Metrics missing or delayed?
├── vmagent pending_data growing → vminsert backpressure
│   └── vminsert CPU saturated → Scale vminsert
├── vm_slow_row_inserts high → Cardinality/cache issue → vm-cardinality-management
├── vm_rows_ignored > 0 → Check reason (duplicate/out_of_order/nan)
├── vmselect OOM → Query too broad → top_queries + optimize or recording rule
└── Dashboard gaps → Check pipeline before VM → otel-pipeline-troubleshooting
```

## Related skills

- `vm-cardinality-management` — when cardinality is the root cause
- `streaming-aggregation` — reduce cardinality at source
- `otel-pipeline-troubleshooting` — data loss before reaching VM
- `victoriametrics-self-metrics` — full metric reference table
- `vmalert-configuration` — rule evaluation issues
