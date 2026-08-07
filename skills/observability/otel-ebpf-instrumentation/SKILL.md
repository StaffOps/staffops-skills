---
name: otel-ebpf-instrumentation
description: "Instrument services with eBPF, no code changes."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [otel, ebpf, instrumentation, observability]
    category: observability
    related_skills: [istio-ambient-otel, python-otel-patterns, dotnet-otel-patterns, fluent-bit-vs-otel-logs]
---
# OTel eBPF Instrumentation (OBI)

eBPF auto-instrumentation for apps without an OTel SDK. Produces HTTP/gRPC/SQL/Redis traces and metrics with no code change.

## When to Use

OpenTelemetry eBPF Instrumentation (OBI) configuration. Use when configuring auto-instrumentation for apps without an SDK, network metrics, context propagation, service discovery, or tuning eBPF performance. Covers DaemonSet deployment, discovery by namespace, network inter-zone (FinOps), context propagation, routes/filters, and cardinality control.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ App (no OTel SDK)                                           │
└────────────────────────┬────────────────────────────────────┘
                         │ (eBPF hooks in the kernel)
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ otel-ebpf-instrumentation (DaemonSet, privileged)           │
│ Image: ghcr.io/open-telemetry/opentelemetry-ebpf-           │
│        instrumentation/ebpf-instrument:v0.9.0               │
│ ├── Produces HTTP/gRPC/SQL/Redis traces                     │
│ ├── Produces application + network metrics                  │
│ └── Exports OTLP → otel-agent-collector.monitoring:4317     │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ otel-agent → gateway → process → Tempo + VictoriaMetrics    │
└─────────────────────────────────────────────────────────────┘
```

## Key behavior

- **Ignores apps that already have an OTel SDK** by default (`exclude_otel_instrumented_services: true`)
- obi traces pass through the agent's tail sampling — same rules (10% in PRD, 100% for errors/high-latency)
- Traces feed the span_metrics connector in otel-process (service graph)
- Configured via a YAML file mounted as a ConfigMap (not env vars)
- Not an OTel Collector — a standalone binary with its own config format

## Deployment

Raw manifests under `monitoring/opentelemetry-collector/obi/`:
- `collector.yaml` — DaemonSet + ServiceAccount + ClusterRole + ClusterRoleBinding + ConfigMap
- `config.yaml` — obi configuration (injected via `tpl(readFile(...))`)

Follows the same organizational pattern as `profile/`, `agent/`, `gateway/`, `process/`.

## Discovery — Allow-list by team namespace

```yaml
discovery:
  exclude_instrument:
    - exe_path: '{*ebpf-instrument*,*otelcol*}'
  instrument:
    - k8s_namespace: 'ai*'
    - k8s_namespace: 'acum*'
    - k8s_namespace: 'apps*'
    - k8s_namespace: 'bm*'
    - k8s_namespace: 'ctp*'
    - k8s_namespace: 'dcp*'
    - k8s_namespace: 'deng*'
    - k8s_namespace: 'devops*'
    - k8s_namespace: 'dpm*'
    - k8s_namespace: 'mdt*'
    - k8s_namespace: 'plg*'
    - k8s_namespace: 'qua*'
```

Add each new team here. The glob accepts `*` as a wildcard (e.g. `dpm*` matches `dpm`, `dpm-people`, `dpm-benefits`).

### Additional filters available (not used by default)

| Filter | Example |
|--------|---------|
| `k8s_deployment_name` | `'my-deploy*'` |
| `k8s_pod_labels` | `{instrument: obi}` |
| `k8s_pod_annotations` | `{obi.instrument: 'true'}` |
| `open_ports` | `'8080,8443'` |
| `languages` | `'go'`, `'java'` |
| `containers_only` | `true` |

## Context propagation

```yaml
ebpf:
  context_propagation: headers
```

Injects `traceparent` into HTTP/1.1 requests leaving apps without an SDK. Creates end-to-end distributed traces spanning legacy and SDK-instrumented apps.

- `headers` mode: HTTP headers only, requires neither `hostNetwork` nor `CAP_NET_ADMIN`
- `tcp` mode: also works with HTTPS (injects at the TCP level), requires `hostNetwork` + `CAP_NET_ADMIN`
- gRPC and HTTP/2: **not supported** in `tcp` mode

## Network metrics

```yaml
metrics:
  features: ['application', 'network_inter_zone']
network:
  enable: true
  allowed_attributes:
    - k8s.src.owner.name
    - k8s.src.namespace
    - k8s.dst.owner.name
    - k8s.dst.namespace
    - k8s.src.owner.type
    - k8s.dst.owner.type
  cidrs:
    - cidr: 172.30.0.0/16
      name: 'vpc-nv'
    - cidr: 172.25.0.0/16
      name: 'vpc-oh'
    - cidr: 172.28.0.0/16
      name: 'vpc-sp'
    - cidr: 10.0.0.0/16
      name: 'k8s-services'
    - cidr: 169.254.0.0/16
      name: 'aws-link-local'
    - cidr: 0.0.0.0/0
      name: 'external'
```

### Metrics produced

| Metric | What it measures |
|---------|-----------|
| `obi_network_flow_bytes_total` | Bytes between endpoints with src/dst owner and namespace |
| `obi_network_inter_zone_bytes_total` | Cross-AZ bytes (AWS cost ~$0.01-0.02/GB) |

### Cardinality control

- `allowed_attributes`: aggregate by **owner** (Deployment), not by individual pod
- `cidrs`: classify traffic into known categories (vpc, services, aws, external)

### Network filter — Allow-list by namespace

```yaml
filter:
  network:
    k8s_dst_namespace:
      match: '{ai*,acum*,apps*,bm*,ctp*,dcp*,deng*,devops*,dpm*,mdt*,plg*,qua*}'
    k8s_src_namespace:
      match: '{ai*,acum*,apps*,bm*,ctp*,dcp*,deng*,devops*,dpm*,mdt*,plg*,qua*}'
```

Uses `match` (allow-list) instead of `not_match` (deny-list) — infrastructure namespaces are skipped automatically with no maintenance.

## Routes — URL cardinality control

```yaml
routes:
  ignored_patterns:
    - /healthz
    - /ready
    - /metrics
    - /health
    - /live
    - /ping
  unmatched: heuristic
```

- `ignored_patterns`: drops healthcheck traces/metrics (30-50% volume reduction)
- `patterns`: defines templates for grouping URLs (e.g. `/api/v1/users/{id}`)
- `unmatched: heuristic`: automatically groups unmapped URLs

## Performance tuning

```yaml
ebpf:
  http_request_timeout: 30s   # requests with no response → status 408
  high_request_volume: true   # avoids event drops under high load
  # wakeup_len: 1000          # reduces CPU under high load (default: 500)
```

### When to tune further

| Symptom | Action |
|---------|------|
| High obi CPU | `wakeup_len: 1000-2000` |
| Event drops | `high_request_volume: true` (already enabled) |
| Too many series | `attributes.select` to exclude labels |
| High trace volume | `otel_traces_export.sampler` with a ratio |
| Irrelevant protocols adding overhead | `instrumentations: ['http', 'grpc']` |

## Available metrics features

| Feature | Description | Used? |
|---------|-----------|----------|
| `application` | http/grpc/sql/redis duration | Yes |
| `network_inter_zone` | Cross-AZ bytes | Yes |
| `network` | Flow bytes (L4) | Via `network.enable` |
| `application_service_graph` | Who calls whom | No — redundant (already provided by the spanmetrics connector) |
| `application_span` | Legacy spanmetrics | No — redundant |
| `application_span_otel` | Spanmetrics in OTel format | No — redundant |
| `application_host` | Per-host metrics | No — irrelevant on Kubernetes |
| `application_span_sizes` | Request/response body sizes | Optional (future) |

## Kubernetes metadata

```yaml
attributes:
  kubernetes:
    enable: true
    meta_restrict_local_node: true  # each obi pod keeps only its own node's metadata
```

Labels decorated automatically: `k8s.namespace.name`, `k8s.deployment.name`, `k8s.pod.name`, `k8s.node.name`, `k8s.container.name`, etc.

## Supported instrumentation

| Protocol | Versions |
|-----------|---------|
| HTTP | 1.0/1.1 (context propagation), 2.0 (no TCP propagation) |
| gRPC | 1.0+ |
| PostgreSQL | All |
| MySQL | All |
| Redis | All |
| MongoDB | 5.0+ |
| Kafka | All |
| AWS S3/SQS | All |

## Relationship with the shared Telemetry Helper library

- Apps **with an SDK** (via the helper): obi **skips** them automatically (no duplicate traces)
- Apps **without an SDK**: obi produces traces + metrics via eBPF
- Metric export interval: the library uses 60s (OTel default), obi uses 30s (configurable)
- Both export to the same endpoint: `otel-agent-collector.monitoring:4317`

## Anti-patterns

- Avoid `k8s_namespace: '*'` — needlessly instruments infrastructure
- Avoid a deny-list in the network filter — hard to maintain; prefer an allow-list by namespace
- Avoid `application_service_graph` when the spanmetrics connector is already present — duplicates metrics
- Avoid sampling in obi when agent-side tail sampling already covers it — double reduction
- Do not skip `meta_restrict_local_node` on large clusters — wastes memory
- Avoid network metrics without `allowed_attributes` — cardinality explodes (aggregates per pod)
- Do not leave healthchecks unfiltered in `routes.ignored_patterns` — useless volume

## Local docs

Full documentation at:
```
EXTERNAL-DOCS/opentelemetry.io/content/en/docs/zero-code/obi/
├── configure/    # All configuration options
├── setup/        # Kubernetes, Docker, standalone
├── metrics.md    # Emitted metrics
├── network/      # Network observability
└── distributed-traces.md
```

## When NOT to use

- For SDK-based instrumentation patterns (.NET/Python/Go) → use language-specific `*-otel-patterns` skills
- For OTel Collector pipeline topology → use `otel-collector-multi-cluster`
- For Pyroscope profiling (eBPF profiler, not tracing) → use `pyroscope-profiling-patterns`

## Related skills

- `otel-collector-multi-cluster` — where eBPF-generated telemetry is routed
- `pyroscope-profiling-patterns` — eBPF profiling (different from tracing)
- `monitoring-stack-overview` — how eBPF instrumentation fits the overall pipeline
- `dotnet-otel-patterns` / `python-otel-patterns` — SDK-based alternative
