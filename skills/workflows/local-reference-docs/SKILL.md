---
name: local-reference-docs
description: "Find vendored reference docs offline."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [local, reference, docs, workflows]
    category: workflows
    related_skills: [markdown-docs, api-docs-patterns]
---
# Local Reference Docs

Documentation and source repositories cloned locally for offline lookup and contextual search.

## When to Use

Index of external documentation cloned locally for offline reference. Use when you need to consult docs for stack components (OTel, Grafana, VictoriaMetrics, Loki, Tempo, Pyroscope, Fluent Bit, k6). The repos live under EXTERNAL-DOCS/.

## Location

```
<workspace>/EXTERNAL-DOCS/
```

## Available repositories

| Directory | Project | Purpose | Relevance |
|-----------|---------|-----------|------------|
| `grafana/` | Grafana | Grafana source code + docs (dashboards, datasources, plugins) | Dashboards, cross-signal correlation |
| `k6-docs/` | k6 | k6 load testing documentation | Load testing, performance |
| `opentelemetry-collector-contrib/` | OTel Collector Contrib | Receivers, processors, exporters contrib | k8sattributes, tail sampling, routing |
| `opentelemetry-collector/` | OTel Collector Core | OTel Collector core (service, pipeline, confmap) | Base architecture, config, pipeline |
| `plugin-tools/` | Grafana Plugin Tools | Tooling for Grafana plugin development | Building custom datasources/panels |
| `opentelemetry.io/` | OpenTelemetry Website | Official OTel docs (specs, API, SDK, instrumentation) | Semantic reference, conventions |
| `fluent-bit-docs/` | Fluent Bit | Fluent Bit docs (pipeline, parsers, outputs) | Log collection, multiline, Loki output |
| `VictoriaMetrics/` | VictoriaMetrics | Source code + docs (vmselect, vminsert, vmstorage, vmagent) | Metrics, alerting, streaming aggregation |
| `tempo/` | Grafana Tempo | Source code + docs (distributed tracing backend) | TraceQL, storage, compaction |
| `loki/` | Grafana Loki | Source code + docs (log aggregation) | LogQL, storage, ruler |
| `pyroscope/` | Grafana Pyroscope | Source code + docs (continuous profiling) | Profiling, trace correlation |
| `pyroscope-dotnet/` | Pyroscope .NET SDK | .NET profiler agent (Datadog fork) | Profiling .NET apps |

## Typical uses

- Verify component flags/settings before suggesting changes
- Read the source to understand real behavior (not just the docs)
- Look for configuration examples under `examples/`
- Validate version compatibility
- Search available processors/receivers in OTel Contrib

## How to search

```bash
# Find the config for a specific processor
grep -r "tail_sampling" opentelemetry-collector-contrib/processor/

# Find VictoriaMetrics flags
grep -r "dedup.minScrapeInterval" VictoriaMetrics/

# Find Fluent Bit docs about the Loki output
grep -r "loki" fluent-bit-docs/pipeline/outputs/

# Find TraceQL syntax
grep -r "TraceQL" tempo/docs/
```

## Maintenance

Repos should be refreshed periodically (`git pull`) to stay consistent with the versions running in the clusters.

## When NOT to use

- **Real-time upstream docs** — if local docs might be stale and you need the latest, use web search.
- **Organization-internal documentation** — see mkdocs-conventions or the devops-docs portal.
- **Code-level API references** — read the source or generated API docs directly.

## Decision tree

```
Which technology docs do you need?
├── OpenTelemetry (SDK, Collector, specs)?
│   └── EXTERNAL-DOCS/opentelemetry.io/content/en/docs/
├── Grafana Tempo (TraceQL, storage, config)?
│   └── EXTERNAL-DOCS/tempo/docs/
├── Grafana Loki (LogQL, schema, ingestion)?
│   └── EXTERNAL-DOCS/loki/docs/
├── Grafana Pyroscope (profiling, pprof, eBPF)?
│   └── EXTERNAL-DOCS/pyroscope/docs/
├── VictoriaMetrics (MetricsQL, cluster, vmagent)?
│   └── EXTERNAL-DOCS/VictoriaMetrics/docs/
└── Fluent Bit (pipelines, parsers, outputs)?
    └── EXTERNAL-DOCS/fluent-bit-docs/
```

## Related skills

- [mkdocs-conventions](../documentation/mkdocs-conventions/SKILL.md) — corporate docs authoring.
- [how-this-agent-works](../workflows/how-this-agent-works/SKILL.md) — understanding how skills reference docs.
- [skill-authoring](../workflows/skill-authoring/SKILL.md) — citing local docs in new skills.
