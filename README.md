# StaffOps Skills

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Skills](https://img.shields.io/badge/skills-132-blue.svg)](#catalog)
[![Format](https://img.shields.io/badge/format-Hermes%20Agent-8A2BE2.svg)](https://github.com/NousResearch/hermes-agent)

A catalog of 132 platform engineering skills for AI coding agents, covering
observability, SRE, Kubernetes, AWS, security, and delivery workflows.

Each skill is a self-contained Markdown document that an agent loads on demand
when a topic becomes relevant — turning a general-purpose assistant into one
that knows how a specific component actually fails, which metric to query, and
what the anti-patterns are.

The catalog is packaged in the [Hermes Agent](https://github.com/NousResearch/hermes-agent)
skill format, which is also compatible with Claude Code and other agents that
read `SKILL.md` frontmatter.

## Why

Most agent knowledge about infrastructure is generic. These skills are the
opposite: they are grounded on specific chart versions, real metric names, and
failure modes observed in production. A skill about Argo CD tells you that
`argocd_app_reconcile_bucket` saturating means the reconciliation queue is
backing up — not that "Argo CD is a GitOps tool".

## Skill Format

Every skill lives at `skills/<category>/<name>/SKILL.md`:

```yaml
---
name: argocd-metrics
description: "Diagnose Argo CD sync failures and reconcile latency."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [argocd, metrics, apm-metrics]
    category: apm-metrics
    related_skills: [argocd-patterns]
---

# Argo CD Metrics

## When to Use
...
```

| Field | Purpose |
| --- | --- |
| `name` | Unique slug, matches the directory name, `^[a-z][a-z0-9_-]*$` |
| `description` | One sentence, **60 characters maximum**, ends with a period |
| `platforms` | OS gating; these skills are documentation, so all three |
| `metadata.hermes.tags` | Search tokens used by the skill hub |
| `metadata.hermes.category` | Matches the parent directory |
| `metadata.hermes.related_skills` | Cross-references to sibling skills |

The 60-character description limit is deliberate: an agent loads every skill's
frontmatter into context at all times and only expands the body on demand. Long
descriptions dilute attention across 132 entries.

## Installation

### Hermes Agent

Copy the categories you want into your Hermes skills directory:

```bash
git clone https://github.com/<your-account>/staffops-skills.git
cp -r staffops-skills/skills/* ~/.hermes/skills/
```

Or install a single category:

```bash
cp -r staffops-skills/skills/observability ~/.hermes/skills/
```

### Claude Code

Claude Code discovers skills under `~/.claude/skills/`. Because it reads the
same `name` + `description` frontmatter, the catalog works unmodified:

```bash
for dir in staffops-skills/skills/*/*/; do
  ln -s "$(pwd)/$dir" ~/.claude/skills/"$(basename "$dir")"
done
```

### Other agents

Any agent that scans a directory tree for `SKILL.md` files and reads YAML
frontmatter can consume this catalog. The extra Hermes-specific keys live under
`metadata.hermes` and are ignored by readers that do not understand them.

## Catalog

<details>
<summary><strong>apm-metrics</strong> (50) — Metric-by-metric diagnostic references for platform components.</summary>

| Skill | Description |
| --- | --- |
| `apm-metrics-cross-runtime` | Compare RED and runtime metrics across language runtimes. |
| `argo-events-metrics` | Diagnose Argo Events delivery and sensor triggers. |
| `argo-rollouts-metrics` | Diagnose progressive delivery and analysis runs. |
| `argo-workflows-metrics` | Diagnose workflow controller backlog and queues. |
| `argocd-metrics` | Diagnose Argo CD sync failures and reconcile latency. |
| `aws-csi-driver-metrics` | Diagnose EBS, EFS and S3 CSI volume operations. |
| `aws-load-balancer-controller-metrics` | Diagnose ALB controller reconcile and AWS API errors. |
| `backing-services-metrics` | Diagnose Redis, PostgreSQL and CoreDNS saturation. |
| `backstage-metrics` | Assess Backstage portal metric availability gaps. |
| `cert-manager-metrics` | Diagnose certificate issuance and ACME rate limits. |
| `collector-internal-metrics` | Diagnose OTel Collector loss and backpressure. |
| `crossplane-metrics` | Diagnose Crossplane reconcile and provider API health. |
| `datahub-metrics` | Diagnose DataHub JVM, Kafka lag and GraphQL latency. |
| `defectdojo-metrics` | Assess DefectDojo nginx exporter metric coverage. |
| `dependency-track-metrics` | Diagnose Dependency-Track ORM, pool and event health. |
| `descheduler-metrics` | Track pod eviction counts and descheduler loops. |
| `dotnet-apm-metrics` | Diagnose .NET GC, ThreadPool, Kestrel and EF Core. |
| `external-dns-metrics` | Diagnose DNS record sync and provider API errors. |
| `external-secrets-metrics` | Diagnose secret sync failures and store readiness. |
| `gitlab-runner-metrics` | Diagnose runner job capacity and queue saturation. |
| `go-apm-metrics` | Diagnose Go GC, scheduler and memory classes. |
| `grafana-self-metrics` | Diagnose Grafana HTTP, datasource and alert health. |
| `harbor-metrics` | Diagnose Harbor registry push, pull and job queues. |
| `ingress-nginx-metrics` | Diagnose ingress latency and upstream errors. |
| `istio-ambient-metrics` | Diagnose ztunnel and waypoint L4/L7 telemetry. |
| `k8s-pvc-tagger-metrics` | Track PVC tagging reconcile and AWS tag errors. |
| `k8s-workload-metrics` | Diagnose pod, container and workload resource health. |
| `karpenter-metrics` | Diagnose node provisioning and disruption events. |
| `keda-metrics` | Diagnose KEDA scaler errors and scaling activity. |
| `keycloak-metrics` | Diagnose Keycloak login, token and JVM health. |
| `kiali-metrics` | Diagnose Kiali API latency and graph generation. |
| `kubecost-metrics` | Diagnose Kubecost allocation and ETL pipeline health. |
| `kubescape-metrics` | Track posture scan results and control failures. |
| `kyverno-metrics` | Diagnose policy admission latency and rule results. |
| `loki-tempo-self-metrics` | Diagnose Loki and Tempo ingest, query and compaction. |
| `metrics-server-metrics` | Diagnose metrics-server scrape and API latency. |
| `nexus3-metrics` | Diagnose Nexus repository JVM and storage health. |
| `nodejs-apm-metrics` | Diagnose Node.js event loop, heap and HTTP health. |
| `opensearch-metrics` | Diagnose OpenSearch cluster, shard and JVM health. |
| `pyroscope-self-metrics` | Diagnose Pyroscope ingest and profile storage health. |
| `python-apm-metrics` | Diagnose Python GC, WSGI/ASGI and runtime health. |
| `reloader-metrics` | Track config and secret reload triggers. |
| `scaleops-metrics` | Diagnose ScaleOps rightsizing and automation health. |
| `sonarqube-metrics` | Diagnose SonarQube JVM, scan queue and DB health. |
| `strimzi-kafka-metrics` | Diagnose Kafka broker, topic and consumer lag. |
| `superset-metrics` | Diagnose Superset query, cache and worker health. |
| `trace-derived-metrics` | Use Tempo service graph metrics for RED analysis. |
| `traefik-metrics` | Diagnose Traefik router, service and TLS health. |
| `velero-metrics` | Track backup, restore and snapshot success rates. |
| `victoriametrics-self-metrics` | Diagnose VM ingest, query and storage saturation. |

</details>

<details>
<summary><strong>aws</strong> (8) — AWS service design and troubleshooting patterns.</summary>

| Skill | Description |
| --- | --- |
| `cloudfront-patterns` | Configure CloudFront origins, caching and WAF. |
| `cost-explorer` | Analyze AWS spend via Cost Explorer and CUR Athena. |
| `eks-management` | Manage EKS nodes, Karpenter, IRSA and upgrades. |
| `iam-patterns` | Design least-privilege IAM roles and policies. |
| `lambda-patterns` | Design Lambda cold start, VPC and observability. |
| `rds-patterns` | Design RDS sizing, failover and backup strategy. |
| `route53-patterns` | Design Route 53 zones, records and health checks. |
| `security-hub-patterns` | Configure Security Hub standards and aggregation. |

</details>

<details>
<summary><strong>development</strong> (13) — Language, framework, and instrumentation patterns.</summary>

| Skill | Description |
| --- | --- |
| `agent-platform-design` | Design autonomous agent execution and guardrails. |
| `anomaly-detection-deep` | Choose detection algorithms and tune false positives. |
| `dotnet-async-patterns` | Write async .NET workers, channels and pipelines. |
| `dotnet-otel-patterns` | Instrument .NET workers, spans and debug tracing. |
| `go-patterns` | Write idiomatic Go services, context and gRPC. |
| `grpc-distributed-tracing` | Propagate trace context across gRPC languages. |
| `mcp-server-development` | Build MCP servers with tools, resources and prompts. |
| `prophet-isolation-forest-patterns` | Forecast and detect outliers with Prophet. |
| `python-fastapi-patterns` | Build FastAPI services, deps and validation. |
| `python-grpc-aio` | Build async Python gRPC servers and clients. |
| `python-otel-patterns` | Instrument Python traces, metrics and logs. |
| `secrets-management-dotnet` | Load secrets into .NET configuration safely. |
| `telemetry-standard` | Adopt the shared OTel helper for .NET and Python. |

</details>

<details>
<summary><strong>documentation</strong> (5) — Technical writing, diagrams, and docs-site conventions.</summary>

| Skill | Description |
| --- | --- |
| `adr-template` | Write MADR architecture decision records. |
| `api-docs-patterns` | Generate API docs from OpenAPI and protobuf. |
| `diagram-patterns` | Choose Mermaid, drawio or ASCII for diagrams. |
| `markdown-docs` | Write structured, reviewable Markdown docs. |
| `mkdocs-conventions` | Configure MkDocs Material sites and navigation. |

</details>

<details>
<summary><strong>finops</strong> (3) — Cost analysis, rightsizing, and commitment planning.</summary>

| Skill | Description |
| --- | --- |
| `ec2-rightsizing-patterns` | Right-size EC2 with utilization and Optimizer data. |
| `savings-plans-strategy` | Plan Savings Plans and reserved capacity coverage. |
| `untagged-resources-bulk-fix` | Find and bulk-tag untagged AWS resources. |

</details>

<details>
<summary><strong>infrastructure</strong> (13) — GitOps, Helm, service mesh, and cluster infrastructure.</summary>

| Skill | Description |
| --- | --- |
| `argocd-patterns` | Configure ApplicationSets, sync waves and hooks. |
| `cosign-image-signing` | Sign and verify container images with cosign. |
| `external-secrets-aws-sm` | Sync AWS Secrets Manager into Kubernetes secrets. |
| `helm-chart-app` | Deploy apps with the shared application Helm chart. |
| `helm-chart-cronworkflow` | Schedule Argo CronWorkflows via the shared chart. |
| `helmfile-applicationset` | Register services in GitOps ApplicationSets. |
| `helmfile-k8s-addon` | Package cluster addons as helmfile releases. |
| `helmfile-templating` | Template helmfile values, envs and secrets. |
| `istio-ambient-debugging` | Debug ztunnel, waypoints and ambient traffic. |
| `istio-ambient-otel` | Wire ambient mesh telemetry into OTel. |
| `karpenter-consolidation` | Tune consolidation and disruption budgets. |
| `kyverno-policies` | Apply the shared Kyverno policy baseline. |
| `terraform-modules` | Use the shared Terraform module catalog. |

</details>

<details>
<summary><strong>observability</strong> (17) — Telemetry pipelines, query languages, and signal correlation.</summary>

| Skill | Description |
| --- | --- |
| `alertmanager-slack-config` | Route Alertmanager alerts to Slack with context. |
| `fluent-bit-loki-pipeline` | Ship logs to Loki with labels and multiline parsing. |
| `fluent-bit-vs-otel-logs` | Compare Fluent Bit and OTel log collection paths. |
| `grafana-cross-signal-correlation` | Link metrics, traces, logs and profiles in Grafana. |
| `kubelet-scrape-architecture` | Understand kubelet and cAdvisor scrape paths. |
| `loki-logql-patterns` | Query logs with LogQL filters and aggregations. |
| `monitoring-stack-overview` | Navigate the monitoring stack topology. |
| `multicluster-label-strategy` | Align cluster labels for multi-cluster queries. |
| `otel-collector-multi-cluster` | Design multi-cluster OTel Collector pipelines. |
| `otel-ebpf-instrumentation` | Instrument services with eBPF, no code changes. |
| `pyroscope-profiling-patterns` | Profile CPU and memory continuously with Pyroscope. |
| `streaming-aggregation` | Cut cardinality with streaming aggregation rules. |
| `tempo-traceql-patterns` | Query traces with TraceQL selectors and aggregates. |
| `victoriametrics-troubleshooting` | Debug VictoriaMetrics ingest and query failures. |
| `victoriametrics-tuning` | Tune VictoriaMetrics retention, memory and dedup. |
| `vm-cardinality-management` | Find and cut high-cardinality metric series. |
| `vmalert-configuration` | Configure VMAlert rules, groups and notifiers. |

</details>

<details>
<summary><strong>projects</strong> (1) — Working context for specific repositories.</summary>

| Skill | Description |
| --- | --- |
| `telemetry-helper` | Work on the shared OTel helper monorepo. |

</details>

<details>
<summary><strong>security</strong> (7) — Supply chain, hardening, compliance, and vulnerability management.</summary>

| Skill | Description |
| --- | --- |
| `aws-ftr-compliance` | Prepare AWS Foundational Technical Review evidence. |
| `container-image-apko` | Build hardened base images with apko. |
| `container-package-melange` | Build custom APK packages with melange. |
| `dependency-track-integration` | Upload SBOMs and manage projects via API. |
| `golden-ami-creation` | Build hardened AMIs with Packer and Ansible. |
| `sbom-vulnerability-management` | Generate SBOMs and triage vulnerabilities. |
| `security-hub-findings-mgmt` | Triage and remediate Security Hub findings. |

</details>

<details>
<summary><strong>sre</strong> (7) — Reliability engineering: SLOs, incidents, and error budgets.</summary>

| Skill | Description |
| --- | --- |
| `alerting-strategy` | Design symptom-based alerts and cut fatigue. |
| `error-budget-framework` | Track error budgets and burn rate alerts. |
| `incident-response-runbook` | Run incident command, severity and comms. |
| `post-mortem-templates` | Write blameless post-mortems with actions. |
| `root-cause-analysis` | Correlate signals to prove root cause. |
| `runbook-authoring` | Write actionable operational runbooks. |
| `sla-slo-design` | Define SLIs, SLOs and reliability targets. |

</details>

<details>
<summary><strong>workflows</strong> (8) — Team conventions and delivery workflows.</summary>

| Skill | Description |
| --- | --- |
| `conventional-commits` | Write Conventional Commits and changelogs. |
| `git-advanced` | Rebase, bisect and recover Git history safely. |
| `gitops-environment-onboard` | Onboard a service into the GitOps pipeline. |
| `how-this-agent-works` | Understand this agent's skills and steering. |
| `jira-conventions` | Write Jira issues with consistent conventions. |
| `local-reference-docs` | Find vendored reference docs offline. |
| `pipeline-template-apps` | Wire apps into the shared CI/CD templates. |
| `spec-writing` | Write requirements, design and task specs. |

</details>

## Validation

`tools/validate_skills.py` enforces the contract above — layout, required
frontmatter keys, the description limit, category consistency, resolvable
`related_skills`, and English-only prose:

```bash
python3 tools/validate_skills.py
# validated 132 skills, 0 error(s)
```

It requires only the Python standard library and exits non-zero on any failure,
so it can run directly in CI.

## Conventions

- **English only.** All prose, examples, and comments.
- **Organization-agnostic.** Placeholders (`<org>`, `<org-domain>`,
  `<ACCOUNT_ID>`, `<workspace>`) stand in for anything environment-specific.
  Never commit real hostnames, account ids, ARNs, or local paths.
- **Grounded, not general.** Cite the chart version, metric name, or release a
  claim comes from. Prefer "confirmed present in a live inventory" over
  "typically exposes".
- **Anti-patterns are first-class.** Most skills end with what not to do; that
  section is frequently the most valuable part.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the skill authoring checklist and
pull request process. In short: add `skills/<category>/<name>/SKILL.md`, keep
the description under 60 characters, run the validator, and open a PR.

## License

[MIT](LICENSE)
