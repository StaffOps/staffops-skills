---
name: agent-skills-metric-verification
description: Use before writing, editing or reviewing any metric name or PromQL query in this repo. Carries the verified environment traps — the inconsistent `_total` suffix, Summary-vs-Histogram, Tempo v3 without ingester/compactor metrics, LEGACY-only .NET, unscraped Strimzi, latent MCP tool names — and the verification procedure. A wrong metric name returns an empty result, which the agent reads as "no problem found".
---

# Verifying metric names in this repo

The highest-severity defect class here, and the one that passes review every time.

## Why it matters more than it looks

A query naming a metric that does not exist returns an **empty result**. Not an error. The agent reads empty as "no problem found" and closes the investigation.

During a real incident that is a silent outage, caused by a skill that looked fine.

## The procedure

Ground truth is the **live backend**. Not documentation, not another skill in this repo, not recollection of usual naming.

```
metrics(match='{__name__=~"prefix_.*"}')
```

The `metrics` tool of the VictoriaMetrics MCP returns only names that exist with data. Exact string match when comparing — `kind_load_image` and `kind_load_image_archive` are different names, and prefix matching has already caused a wrong removal.

If a name does not come back, it does not exist here. No exceptions, no "but the docs say".

## This has gone wrong twice, both times looking like success

| Incident | What happened |
|----------|---------------|
| VictoriaMetrics family | An audit used a sibling skill as ground truth and renamed four **real** metrics into names that do not exist: `vm_active_merges`, `vm_merges_total`, `vm_pending_rows`, `vm_new_timeseries_created_total` |
| cert-manager | An audit removed `certmanager_controller_sync_error_count` as "does not exist in v1.19+". It exists |

Both arrived as tidy before/after tables, indistinguishable from correct work. **Spot-check any audit report against the backend before accepting it** — a wrong correction is more expensive than the original error because it comes wearing the clothes of rigour.

When delegating an audit, state explicitly that the live backend is the only ground truth and that secondary sources are forbidden. Without that, a subagent uses whatever is most accessible.

## Verified traps

| Trap | Detail |
|------|--------|
| `_total` is **inconsistent per signal type** | `otelcol_receiver_accepted_spans_total` exists; `..._log_records_total` does not. Never apply the suffix by rule. Use `{__name__=~"metric(_total)?"}` when both forms may occur |
| `histogram_quantile()` on a Summary returns empty, silently | Confirm a `_bucket` series exists first. Summaries found so far: `go_gc_duration_seconds`, `keda_internal_scale_loop_latency_seconds`, `karpenter_pods_startup_duration_seconds`, `karpenter_nodes_termination_duration_seconds`, `certmanager_http_acme_client_request_duration_seconds`. Query them as `metric{quantile="0.99"}` |
| Tempo runs **v3 with Kafka** | `tempo_ingester_*` and `tempo_compactor_*` do not exist at all. Use `tempo_live_store_*` and `tempo_backend_scheduler_*` |
| Only **LEGACY** .NET metrics | `process_runtime_dotnet_*`. NATIVE `dotnet_*`, `microsoft_entityframeworkcore_*` and most `kestrel_*` are absent |
| Strimzi operator not scraped | `strimzi_*` returns empty. Fall back to `controller_runtime_reconcile_errors_total` |
| Strimzi JMX is lowercase | `kafka_server_brokertopicmetrics_messagesin_total`, never CamelCase |
| Istio uses `_milliseconds` | Not `_seconds` |
| Loki labels are Fluent Bit-mapped | `service_namespace`, `service_workload`, `eks_cluster` — not raw k8s names. Structured metadata field is `trace_id`, not `traceID` |
| Two cluster labels coexist | `cluster` is the k8s cluster name, `eks_cluster` is the environment (`core`/`dev`/`prd`). Using the wrong one silently mixes environments or returns nothing |
| MCP tools are **latent** | The bare name is not invocable. Use `Knowledge_MCP_search_knowledge`. If it will not resolve, discover once with `search_user_tools(tool_names=[...])` — passing `prompt` and `tool_names` together is rejected |
| `search_knowledge` indexes two sources | Pass `source="knowledge"` for platform facts; without it `devops-docs` ranks first and the fact looks undocumented |

## When a name cannot be resolved

Annotate `⚠️ not present in current inventory — verify before use`. Do not delete the query silently, and do not assert the name anyway.

## Not yet verified

Every family has now been checked at least once. If a new family is added, it starts unverified — say so in the skill rather than implying it was checked.

## When NOT to use

- Writing a new skill that doesn't involve metrics — use `agent-skills-new-skill-checklist`
- Debugging a skill that loads but ignores instructions — use `agent-skills-debugging`
- Querying VictoriaMetrics for live troubleshooting — use `victoriametrics-investigation`

## Decision tree

```
├── Does the metric exist at all?
│   └── metrics(match='{__name__=~"prefix_.*"}') → empty = does not exist
├── Wrong suffix (_total present/absent)?
│   └── Check both with and without _total — environment is inconsistent
├── Metric exists but not scraped for this target?
│   └── Verify ServiceMonitor/PodMonitor exists and matches labels
└── Summary vs Histogram confusion?
    └── Check _bucket (histogram) vs _count/_sum only (summary)
```

## Related skills

- `agent-skills-debugging` — when the skill loads but produces wrong output (not metric-specific)
- `agent-skills-new-skill-checklist` — when creating a metric-focused skill from scratch
- `victoriametrics-investigation` — live VM queries for troubleshooting (not skill authoring)
- `agent-skills-harness-guide` — running the harness to validate metric queries produce results
