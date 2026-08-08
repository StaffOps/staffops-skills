---
name: agent-skills-debugging
description: Troubleshooting guide for when a skill doesn't load, loads but produces empty results, or loads but the agent ignores its procedure.
---

# Agent Skills Debugging

Three failure modes when a skill doesn't work as expected. Diagnose which one you're hitting before attempting fixes.

---

## Skill never loads

The skill exists but is never selected during execution.

| Cause | Diagnosis | Fix |
|-------|-----------|-----|
| Description too vague | Skill loses selection lottery against more specific skills with overlapping scope | Make description more specific — include concrete symptom keywords the router matches on |
| Not in symptom-router | Skill is invisible as an entry point; router never considers it | Add the skill to the symptom-router mapping for the relevant symptom keywords |
| Wrong `agent_types` scope | Skill only loads when `taskType` matches the declared `agent_types` | Verify the `agent_types` array includes the execution context you're testing (e.g., `TROUBLESHOOTING`, `INVESTIGATION`) |
| Import failed silently | Skill was imported but validation failed without surfacing an error | Run `list-assets` and confirm the skill appears with status `ACTIVE`; re-import if missing |
| Skill deactivated | `metadata.status=INACTIVE` — skill exists but is excluded from selection | Check asset metadata; reactivate or re-import with correct status |

### Quick check

```
list-assets → find your skill ID → confirm status=ACTIVE
list-journal-records → check if skill bundle appears in utilization
```

If the skill doesn't appear in `list-assets` output at all, the import failed. Re-import and watch for `ValidationException`.

---

## Skill loads but produces no data (silent false negative)

The skill is selected and its procedure runs, but queries return empty results. The agent concludes "no problem found" — a false negative.

### Metric name wrong

The most common cause. The procedure references a metric name that doesn't exist in the target datasource.

- `_total` suffix inconsistency: some metrics have it (`otelcol_exporter_send_failed_spans_total`), others don't. Check the actual metric name in VictoriaMetrics with `label_values(__name__)` or the metrics catalog.
- `histogram_quantile()` on a Summary metric → returns empty, not an error. Summaries use `{quantile="0.99"}` label selectors instead.
- Metric was renamed between versions (e.g., `otelcol_receiver_accepted_spans` vs `otelcol_receiver_accepted_spans_total`).

### Loki label mismatch

OTel-mapped labels in Loki differ from what you might expect:

| Correct (OTel-mapped) | Wrong (won't match) |
|------------------------|---------------------|
| `service_name` | `service`, `app`, `service_workload` |
| `service_namespace` | `namespace` (this is k8s namespace, different field) |
| `eks_cluster` | `cluster_name`, `cluster` |

Always verify available labels with `list_loki_label_names` before writing queries.

### MCP tool name is latent

Tool names in the MCP layer use fully qualified names. Use `Knowledge_MCP_search_knowledge` not bare `search_knowledge`. If the procedure calls a tool that doesn't resolve, the step silently produces nothing.

### Wrong datasource

| Datasource | Contains |
|------------|----------|
| Default VictoriaMetrics | Infrastructure + application metrics (most signals) |
| `vm-custommetrics-mdt` | Business/domain-specific custom metrics (MDT team) |

If the metric exists but the procedure queries the wrong datasource, results are empty without error.

---

## Skill loads but agent ignores procedure

The skill is selected, data is available, but the agent doesn't follow the procedure steps.

| Cause | Diagnosis | Fix |
|-------|-----------|-----|
| Platform overrides output shape | On deep `INVESTIGATION` tasks, the platform ignores structured labels and only surfaces raw facts | Restructure procedure to emit facts early; don't rely on labeled output sections |
| Tested via `create_chat` but rule applies to typed execution | `create_chat` uses conversational mode; `create-backlog-task` uses typed execution with different procedure adherence | Test with the same execution mode the skill will be invoked under |
| Skill competes with another for same symptom | Two skills match; the other wins routing priority and its procedure runs instead | Check routing priority; make descriptions mutually exclusive or merge competing skills |

---

## How to diagnose which skill loaded

### Method 1: Journal records

```
list-journal-records → look for utilization records → they name the loaded bundles
```

The utilization record explicitly lists which skill assets were loaded for that execution.

### Method 2: Harness event dump

```
--dump-events → inspect load_skill blocks in the event stream
```

Shows the exact moment a skill was loaded and which procedure was injected.

### Method 3: Pin a specific skill

Force a specific skill to load by passing `assetIds` in the `SendMessage` call:

```json
{
  "assetIds": ["arn:aws:aidevops:us-east-1:123456789:skill/my-skill-id"]
}
```

This bypasses the router entirely — useful to confirm the skill works when loaded, isolating the problem to selection vs execution.

---

## Debugging checklist

1. **Does the skill exist?** → `list-assets`, confirm `ACTIVE`
2. **Is it being selected?** → `list-journal-records`, check utilization
3. **Are queries returning data?** → Run the same query manually against the datasource
4. **Is the procedure being followed?** → Pin the skill with `assetIds`, check output structure
5. **Is another skill winning?** → Check competing descriptions, narrow scope

## When NOT to use

- Writing a new skill from scratch — use `agent-skills-new-skill-checklist`
- Importing skills into the agentspace — use `agent-skills-import-and-harness`
- Verifying metric names in PromQL expressions — use `agent-skills-metric-verification`

## Decision tree

```
├── Skill never loads?
│   └── Check: description keywords, agent_types, import status (ACTIVE)
├── Loads but produces empty results?
│   └── Check: metric names exist, query syntax, time range, target labels
└── Loads but agent ignores the procedure?
    └── Check: instruction tone (prescriptive > descriptive), competing skills
```

## Related skills

- `agent-skills-import-and-harness` — when the issue is an import API error, not a loaded skill misbehaving
- `agent-skills-harness-guide` — when you need to run the behaviour harness to reproduce a failure
- `agent-skills-new-skill-checklist` — when creating a skill that doesn't exist yet
- `agent-skills-metric-verification` — when the problem is a wrong metric name returning empty results
