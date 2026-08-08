# observability

Telemetry pipelines, query languages, and signal correlation.

28 skills.

- **alertmanager-slack-config** — Route Alertmanager alerts to Slack with context. _(references/)_
- **cardinality-explosion-finder** — Use when VictoriaMetrics is OOMing, vmselect queries are slow, or TSDB cardinality is growing unexpectedly. Runs a bundled Python script that analyzes TSDB status data (top metrics, labels, and lab... _(references/)_
- **fluent-bit-loki-pipeline** — Ship logs to Loki with labels and multiline parsing.
- **fluent-bit-vs-otel-logs** — Compare Fluent Bit and OTel log collection paths.
- **grafana-cross-signal-correlation** — Link metrics, traces, logs and profiles in Grafana.
- **kafka-pipeline-health** — Monitor and troubleshoot the Kafka buffer in the OTel telemetry pipeline (Strimzi-managed, KRaft mode). Symptoms: growing consumer lag for otel-process-consumer, under-replicated partitions, broker... _(references/)_
- **kubelet-scrape-architecture** — Understand kubelet and cAdvisor scrape paths.
- **kuma-synthetic-status** — Use when you need to verify whether an API endpoint is actually responding from an external perspective (synthetic test), check endpoint latency as seen by clients, determine 24h/30d uptime ratios,...
- **log-pattern-analyzer** — Use when investigating log volume spikes, identifying dominant error patterns, or detecting anomalous log messages during an incident. Runs a bundled Python script that normalizes log lines into pa... _(references/)_
- **loki-logql-patterns** — Query logs with LogQL filters and aggregations.
- **monitoring-stack-overview** — Navigate the monitoring stack topology.
- **multicluster-label-strategy** — Align cluster labels for multi-cluster queries.
- **observability-tooling** — Route observability symptoms to the correct MCP tool with correct parameters. Use as the FIRST skill loaded when any observability investigation begins. Maps symptoms (slow service, errors spiking,... _(references/)_
- **otel-collector-multi-cluster** — Design multi-cluster OTel Collector pipelines. _(references/)_
- **otel-ebpf-instrumentation** — Instrument services with eBPF, no code changes.
- **otel-pipeline-review** — Proactive operational review of the OTel telemetry pipeline (Evaluation agent type). Produces a findings report covering end-to-end data loss, queue headroom, tail-sampling correctness, cardinality... _(references/)_
- **otel-pipeline-troubleshooting** — Diagnose data loss, backpressure, and failures in the OTel Collector pipeline. Symptoms: missing telemetry in Tempo/Loki/VictoriaMetrics, growing Kafka lag, otelcol_exporter_enqueue_failed > 0, ote... _(references/)_
- **pyroscope-profiling-patterns** — Profile CPU and memory continuously with Pyroscope.
- **streaming-aggregation** — Cut cardinality with streaming aggregation rules.
- **tempo-trace-investigation** — Investigate distributed traces using Tempo and TraceQL. Symptoms: high latency on a service, errors propagating across services, need to find which span in a request chain is slow, exemplar drill-d... _(references/)_
- **tempo-traceql-patterns** — Query traces with TraceQL selectors and aggregates.
- **tempo-v3-kafka-operations** — Use when migrating Grafana Tempo v2→v3, operating the v3 Kafka-based ingest path, or debugging partition-ring errors, orphan partitions, OOM on replay, or missing PDBs. Covers the ingester→block-bu...
- **victoriametrics-investigation** — Diagnose VictoriaMetrics cluster issues — slow queries, ingestion bottlenecks, cache misses, storage pressure, remote_write backpressure from vmagent. Symptoms: dashboard queries timing out, vmsele... _(references/)_
- **victoriametrics-troubleshooting** — Debug VictoriaMetrics ingest and query failures.
- **victoriametrics-tuning** — Tune VictoriaMetrics retention, memory and dedup.
- **vm-capacity-review** — Proactive VictoriaMetrics capacity and health review (Evaluation agent type). Produces a capacity report covering ingestion rate trend, storage growth and projected exhaustion date, cardinality sta... _(references/)_
- **vm-cardinality-management** — Find and cut high-cardinality metric series.
- **vmalert-configuration** — Configure VMAlert rules, groups and notifiers. _(references/)_
