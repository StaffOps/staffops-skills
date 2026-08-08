---
name: victoriametrics-troubleshooting
description: "Debug VictoriaMetrics ingest and query failures."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [victoriametrics, troubleshooting, observability]
    category: observability
    related_skills: [victoriametrics-tuning, victoriametrics-self-metrics]
---
# VictoriaMetrics Distributed — Troubleshooting & Capacity Planning

Operational knowledge for analyzing, troubleshooting and capacity planning VictoriaMetrics environments — especially **vmagent + vminsert + vmstorage clusters**.

## When to Use

VictoriaMetrics distributed cluster troubleshooting and capacity planning. Use when diagnosing ingestion bottlenecks, vminsert/vmstorage issues, scaling decisions, or remote_write backpressure.

## Architecture overview

```
vmagent → vminsert → vmstorage
                  ↓
               vmselect
```

| Component | Responsibility |
|-----------|----------------|
| vmagent | Scraping metrics, batching, remote write queues, buffering |
| vminsert | Ingestion API, batching, routing to vmstorage |
| vmstorage | Persistent storage, compression, retention |
| vmselect | Query execution |

## Core ingestion metrics

Always analyze these first.

### Ingestion rate
```promql
sum(rate(vm_rows_inserted_total[5m]))
```
Primary capacity metric (samples/sec).

### Batch size
```
vm_rows_per_insert_bucket
```
Healthy: 1000–10000 samples per insert. Below 1000 = high CPU overhead.

```promql
histogram_quantile(0.5, vm_rows_per_insert_bucket)
```

### Concurrent inserts
```
vm_concurrent_insert_current
vm_concurrent_insert_capacity
vm_concurrent_insert_limit_reached_total
```

If `current == capacity` AND `limit_reached_total` increasing → vminsert overloaded.

### vmagent backlog
```
vmagent_remotewrite_pending_data_bytes
```
Increasing = backpressure (vminsert can't keep up).

## Key flags

### vminsert
| Flag | Purpose |
|------|---------|
| `-insert.maxConcurrentInserts=64` | Max parallel insert requests |
| `-insert.maxQueueDuration=10m` | Max wait time in queue |

### vmagent — remote_write
| Flag | Purpose |
|------|---------|
| `-remoteWrite.queues=32` | Parallel queues (more = more parallelism + memory) |
| `-remoteWrite.maxBlockSize=32MB` | Max batch size |
| `-remoteWrite.maxRowsPerBlock=50000` | Max samples per batch |

## Scaling rules of thumb

### CPU scales linearly with ingestion
| CPU | Concurrent inserts |
|-----|---------------------|
| 2 | ~32 |
| 4 | ~64 |
| 8 | ~128 |

### Cluster capacity
- 1 vminsert per ~200k samples/sec
- 1 vmstorage per ~200k samples/sec

### Scaling order (preferred)
1. Increase CPU of vminsert
2. Increase `insert.maxConcurrentInserts`
3. Add vminsert replicas
4. Add vmstorage nodes

Scale vmagent only if scraping itself becomes bottleneck.

## Investigation workflow

When ingestion problems appear:

1. Check ingestion rate — is it growing unexpectedly?
2. Check vmagent backlog — `vmagent_remotewrite_pending_data_bytes` rising?
3. Check vminsert concurrency — is it saturating?
4. Check batch size — too small? (<1000)
5. Check CPU usage — vminsert/vmstorage maxed?
6. Identify bottleneck layer

## Common anti-patterns

### Too many small batches
- Symptom: `rows_per_insert < 1000`
- Impact: high CPU overhead
- Fix: increase batch size in vmagent

### Queues too small
- Symptom: remote write backlog increasing
- Fix: increase `remoteWrite.queues`

### vminsert concurrency limit hit
- Symptom: `vm_concurrent_insert_limit_reached_total` rising
- Fix: increase `insert.maxConcurrentInserts` (or scale CPU)

## vmselect — query side issues

### `search.maxUniqueTimeseries` blocks delete operations

In clusters with many series, the limit (default 50M) blocks delete API operations. To purge series:
1. Temporarily raise `search.maxUniqueTimeseries` (e.g., to 700M)
2. Run delete query
3. Force merge
4. **Don't restart pods during force merge** — it cancels the process

### TSDB status shows historical series after delete
Until merge purges, deleted series still appear in `/api/v1/status/tsdb`. Wait for compactor.

## Reference

- VictoriaMetrics docs: https://docs.victoriametrics.com/
- Cluster mode: https://docs.victoriametrics.com/victoriametrics/cluster-victoriametrics/
- vmagent: https://docs.victoriametrics.com/vmagent/
- Capacity planning: https://docs.victoriametrics.com/victoriametrics/cluster-victoriametrics/#capacity-planning
- Local cache: `<workspace>/01-DEVOPS/EXTERNAL-DOCS/VictoriaMetrics/docs`

## When NOT to use

- For VM performance tuning flags → use `victoriametrics-tuning`
- For cardinality explosions and label management → use `vm-cardinality-management`
- For VMAlert rule configuration → use `vmalert-configuration`
## Decision tree

```
VictoriaMetrics issue?
├── Slow queries? → vmselect bottleneck
│   ├── High cardinality? → Check series count per metric (tsdb status)
│   ├── Wide time range? → Add step or reduce range
│   └── Resource starved? → Scale vmselect replicas or memory
├── Data gaps? → Missing samples in graphs
│   ├── Scrape failing? → Check vmagent targets + up{} metric
│   ├── Remote write lag? → vmagent pending_data_bytes growing
│   └── Retention expired? → Check retentionPeriod vs query range
├── OOM? → Component killed by K8s
│   ├── vmselect OOM? → Concurrent heavy queries — add memory or limit
│   ├── vmstorage OOM? → Cache pressure — tune cacheExpireDuration
│   └── vmagent OOM? → Too many targets or blocked remote_write
└── Disk full? → vmstorage running out of space
    ├── Growth rate? → Check vm_data_size_bytes rate of change
    ├── Quick fix? → Reduce retentionPeriod or add PV
    └── Long-term? → Drop unused metrics via relabeling
```


## Related skills

- `victoriametrics-tuning` — flag-level performance optimization
- `vm-cardinality-management` — detecting and fixing high-cardinality series
- `vmalert-configuration` — alert/recording rules evaluated against VM
- `monitoring-stack-overview` — VM's place in the overall pipeline
