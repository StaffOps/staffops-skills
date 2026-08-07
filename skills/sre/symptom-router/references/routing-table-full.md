# Routing Table — Full (40+ Symptoms)

Extended version of the quick-reference table in SKILL.md.

Every skill name below is verified against the directory listing of `skills/`.

---

## Telemetry Pipeline Symptoms

| # | Symptom | First skill | Then | Why this order |
|---|---------|-------------|------|----------------|
| 1 | Logs missing in Grafana | `collector-internal-metrics` | `loki-tempo-self-metrics` | Pipeline drops most common; backend rejection second |
| 2 | Traces missing in Tempo | `otel-pipeline-troubleshooting` | `loki-tempo-self-metrics` | Pipeline loss precedes backend discard |
| 3 | Metrics gaps in dashboards | `victoriametrics-self-metrics` | `collector-internal-metrics` | Backend ingestion health; pipeline if backend OK |
| 4 | Kafka consumer lag (OTel topics) | `kafka-pipeline-health` | `otel-pipeline-troubleshooting` | Lag source (broker vs consumer); pipeline config if consumer is slow |
| 5 | Collector pod OOMKilled | `k8s-workload-metrics` | `collector-internal-metrics` | Confirm OOM; then pipeline config causing memory growth |
| 6 | otelcol_exporter_enqueue_failed > 0 | `collector-internal-metrics` | `kafka-pipeline-health` | Queue saturation diagnosis; Kafka health if exporter target is Kafka |
| 7 | otelcol_receiver_refused > 0 | `collector-internal-metrics` | `otel-collector-multi-cluster` | Memory limiter triggering; multi-cluster routing if only some sources refused |
| 8 | Exemplar links broken (metric→trace) | `grafana-cross-signal-correlation` | `tempo-trace-investigation` | Datasource config first; Tempo retention if link valid but trace expired |

## Application Performance Symptoms

| # | Symptom | First skill | Then | Why this order |
|---|---------|-------------|------|----------------|
| 9 | API is slow / high P99 | `apm-metrics-cross-runtime` | `tempo-trace-investigation` | Metrics isolate the layer; traces pinpoint the span |
| 10 | .NET thread pool starvation | `dotnet-apm-metrics` | `tempo-trace-investigation` | ThreadPool queue length confirms; traces show blocking call |
| 11 | .NET memory leak / high GC | `dotnet-apm-metrics` | `k8s-workload-metrics` | GC heap metrics first; container limits if runtime looks OK |
| 12 | Python GC pressure | `python-apm-metrics` | `k8s-workload-metrics` | cpython_gc_count; container RSS if GC alone doesn't explain |
| 13 | Go goroutine leak | `go-apm-metrics` | `k8s-workload-metrics` | go_goroutines growth; resource exhaustion as consequence |
| 14 | Database connection exhaustion | `backing-services-metrics` | `python-apm-metrics` or `dotnet-apm-metrics` | PG connection count first; app-side pool config if PG has capacity |
| 15 | Redis connection refused | `backing-services-metrics` | `apm-metrics-cross-runtime` | Redis rejected_connections; app-side pool if Redis is healthy |
| 16 | DNS resolution slow | `backing-services-metrics` | `istio-ambient-debugging` | CoreDNS latency; Istio DNS interception if CoreDNS is fast |
| 17 | gRPC errors across services | `istio-ambient-debugging` | `istio-ambient-metrics` | Ambient hostname mismatch; mesh metrics for magnitude |
| 18 | Cascading failure across services | `trace-derived-metrics` | `tempo-trace-investigation` | Service graph edges show propagation; traces confirm chain |

## Kubernetes Workload Symptoms

| # | Symptom | First skill | Then | Why this order |
|---|---------|-------------|------|----------------|
| 19 | Pods stuck Pending | `eks-node-troubleshooting` | `karpenter-metrics` | Scheduling constraints; provisioner if capacity issue |
| 20 | OOMKilled | `k8s-workload-metrics` | runtime-specific APM skill | Confirm OOM + frequency; runtime leak analysis |
| 21 | CrashLoopBackOff | `k8s-workload-metrics` | `incident-triage` | Exit code + lastState; escalation if cause unclear |
| 22 | CPU throttling | `k8s-workload-metrics` | runtime-specific APM skill | cfs_throttled_periods; runtime to find hot path |
| 23 | Replica count < desired | `keda-metrics` | `karpenter-metrics` | KEDA scaler errors first; node capacity if HPA is correct |
| 24 | Pod topology constraint violation | `karpenter-consolidation` | `eks-node-troubleshooting` | Anti-affinity zone cap; node availability per zone |
| 25 | Image pull failure | `argocd-patterns` | `helm-chart-app` | Image reference validity; chart config if image tag is correct |

## GitOps & Deployment Symptoms

| # | Symptom | First skill | Then | Why this order |
|---|---------|-------------|------|----------------|
| 26 | Deploy did not roll out | `argocd-metrics` | `gitops-environments` | Sync error; topology if app not found |
| 27 | ArgoCD stuck OutOfSync | `argocd-metrics` | `argocd-patterns` | Reconciliation failures; generator patterns if app misconfigured |
| 28 | Rollout stuck at canary step | `argocd-patterns` | `istio-ambient-metrics` | Rollout analysis run; traffic splitting if analysis passes but traffic fails |
| 29 | Helm values not applied | `helm-chart-app` | `gitops-environments` | Chart values precedence; environment values override hierarchy |
| 30 | Service not reachable after deploy | `istio-ambient-metrics` | `argocd-patterns` | Mesh routing post-deploy; sync state if manifest didn't apply |

## Security & Secrets Symptoms

| # | Symptom | First skill | Then | Why this order |
|---|---------|-------------|------|----------------|
| 31 | Certificate expired / TLS error | `cert-manager-metrics` | `external-secrets-aws-sm` | cert-manager lifecycle; ESO if cert rotation depends on secret |
| 32 | Secret not syncing to pod | `external-secrets-aws-sm` | `iam-patterns` | ESO status; IRSA if SecretStore auth fails |
| 33 | Pod AccessDenied to AWS | `iam-patterns` | `external-secrets-aws-sm` | IRSA trust/policy; secret path if credential is file-based |
| 34 | mTLS failure between services | `istio-ambient-debugging` | `cert-manager-metrics` | Ambient ztunnel mTLS; cert if custom certs used |

## Alerting & SLO Symptoms

| # | Symptom | First skill | Then | Why this order |
|---|---------|-------------|------|----------------|
| 35 | Alert never fired (should have) | `vmalert-configuration` | `alerting-strategy` | Rule eval issues; routing if rule evaluates correctly |
| 36 | Alert fires constantly (noise) | `alerting-strategy` | `vmalert-configuration` | Threshold/routing; evalDelay if threshold is correct |
| 37 | SLO burn rate alert | `error-budget-framework` | `incident-triage` | Budget state; incident response if budget exhausted |
| 38 | Recording rule returns NaN | `vmalert-configuration` | `victoriametrics-self-metrics` | queryStep/label issues; VM ingestion if metric vanished |

## Cost & Capacity Symptoms

| # | Symptom | First skill | Then | Why this order |
|---|---------|-------------|------|----------------|
| 39 | Cost spiked | `cost-explorer` | `karpenter-metrics` | Tag attribution; node churn if EKS-related |
| 40 | Nodes not consolidating | `karpenter-consolidation` | `karpenter-metrics` | Disruption blockers; provisioner state |
| 41 | Autoscaling not working (KEDA) | `keda-metrics` | `karpenter-metrics` | Scaler errors; node capacity if pods scale but can't schedule |
| 42 | Cardinality explosion | `vm-cardinality-management` | `streaming-aggregation` | Identify offender; remediation pattern |
| 43 | VictoriaMetrics OOM | `victoriametrics-self-metrics` | `vm-cardinality-management` | Component health; cardinality if vmselect query OOM |

## Observability Stack Self-Health

| # | Symptom | First skill | Then | Why this order |
|---|---------|-------------|------|----------------|
| 44 | Grafana dashboard "no data" | `observability-tooling` | `victoriametrics-self-metrics` | Datasource config; backend health |
| 45 | Loki discarding logs | `loki-tempo-self-metrics` | `collector-internal-metrics` | Backend rate limit; pipeline label cardinality if backend capacity OK |
| 46 | Tempo discarding spans | `loki-tempo-self-metrics` | `otel-pipeline-troubleshooting` | Backend limits (trace_too_large); pipeline batching if traces normal size |
| 47 | Service map blank in Grafana | `grafana-cross-signal-correlation` | `trace-derived-metrics` | Datasource config; metrics-generator health if config correct |
