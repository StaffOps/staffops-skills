# StaffOps Skills

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Skills](https://img.shields.io/badge/skills-242-blue.svg)](#catalog)
[![Format](https://img.shields.io/badge/format-Hermes%20Agent-8A2BE2.svg)](https://github.com/NousResearch/hermes-agent)
[![Harness Score](https://img.shields.io/badge/harness--score-L4%20(95%2F108)-brightgreen.svg)](https://paladini.github.io/harness-score/)

A catalog of 242 platform engineering skills for AI coding agents, covering
observability, SRE, Kubernetes, AWS, security, AI/LLM-ops, and delivery workflows.

Each skill is a self-contained Markdown document that an agent loads on demand
when a topic becomes relevant — turning a general-purpose assistant into one
that knows how a specific component actually fails, which metric to query, and
what the anti-patterns are.

The catalog is packaged in the [Hermes Agent](https://github.com/NousResearch/hermes-agent)
skill format, which is also compatible with Claude Code, Kiro CLI, and other
agents that read `SKILL.md` frontmatter — see **Installation** below for the
one adjustment each platform needs (none, for Kiro; a flattening symlink
step, for Claude Code).

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

### Layout

Skills that ship supporting material use these conventions, which the Hermes
skill format expects:

```
skills/<category>/<name>/
├── SKILL.md          the skill itself, kept navigable (~200 lines)
├── references/       long-form tables and specifications
├── scripts/          runnable helpers, shellcheck-clean (where present)
└── examples/         worked examples (where present)
```

Only `SKILL.md` is required. `references/`, `scripts/`, and `examples/` are
added when they earn their place, not as a template to fill in for every
skill — see **Depth varies by skill** below.

**Depth varies by skill, intentionally.** A handful of early skills
(`skills/shell/`, and `linux-command-line`, `linux-filesystem`,
`linux-process-management`, `systemd-services` in `skills/linux/`) go all
the way: `scripts/` and `examples/` there are shellcheck/shfmt-clean and were
executed against a real Ubuntu 24.04 container (including one running actual
systemd as PID 1) during authoring — verification caught and fixed several
real bugs along the way, documented in the commit history. That depth is
valuable but expensive, and is being treated as an option to expand into
later rather than a bar every skill must clear immediately. Most skills in
this catalog prioritize clear concepts, accurate specifics, and a few basic
inline examples over exhaustively tested tooling. Contributions that add
`scripts/`/`examples/` depth to an existing skill are welcome.

The 60-character description limit is deliberate: an agent loads every skill's
frontmatter into context at all times and only expands the body on demand. Long
descriptions dilute attention across 229 entries.

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

Claude Code discovers skills under `~/.claude/skills/` as direct children of
that one flat directory — because it reads the same `name` + `description`
frontmatter, the catalog works unmodified, it just needs one symlink per
skill to flatten the category nesting:

```bash
./tools/install.sh install
```

The script validates the catalog first (`tools/validate_skills.py`), never
overwrites an entry it doesn't own (a same-named skill already installed by
something else is skipped with a warning, not clobbered), and supports
`uninstall`, `status`, and `clean` (remove only this repo's broken symlinks,
e.g. after a skill is renamed) the same way — see `./tools/install.sh help`.
Every command accepts `--dry-run`. Override the target directory with
`CLAUDE_SKILLS_DIR=/path ./tools/install.sh install` if needed.

### Kiro CLI

Kiro needs no install step: it reads `SKILL.md` files directly off disk via
a `skill://` glob resource declared in an agent's JSON `resources` array, and
that glob already supports this catalog's `skills/<category>/<name>/`
nesting natively — no flattening, no symlinks. Print the exact line to add
to your own agent's `resources` array:

```bash
./tools/install.sh kiro-resource-line
```

This only prints; it never writes to a Kiro agent file the catalog doesn't
own.

### Other agents

Any agent that scans a directory tree for `SKILL.md` files and reads YAML
frontmatter can consume this catalog. The extra Hermes-specific keys live under
`metadata.hermes` and are ignored by readers that do not understand them.

## Catalog

<!-- catalog:start -->

<details>
<summary><strong>ai</strong> (19) — AI/LLM-ops and AI-security: agents, evals, cost, and supply chain.</summary>

| Skill | Description | Includes |
| --- | --- | --- |
| `agent-evals` | Use when building golden-dataset regression suites to measure agent/skill correctness over time, designing rubrics for graded evaluation, setting r... | `references/` |
| `agent-memory-patterns` | Use when designing memory and context systems for AI agents — short-term session buffers, long-term knowledge bases, episodic recall. Covers memory... | — |
| `agent-observability` | Use when instrumenting LLM agent calls with OTel spans for token counts, cost tracking, tool-call structure, and sensitive-content redaction — the ... | — |
| `ai-agent-security` | Use when designing or auditing the security posture of an AI agent — tool permission scoping, blast-radius tiering, exfiltration prevention, creden... | — |
| `ai-coding-agent-guardrails` | Use when scoping file, shell, and git permissions for coding agents (Claude Code, Cursor, Copilot, Codex) — deciding which actions auto-apply vs re... | `references/` |
| `ai-pipeline-orchestration` | Use when designing multi-step LLM pipelines — chaining prompts, routing between models, implementing fallback/retry, managing context windows acros... | — |
| `ai-red-teaming` | Use when adversarially testing an AI agent's security controls — probing for prompt injection bypasses, tool abuse, privilege escalation, data exfi... | — |
| `ai-security-hardening` | Use when hardening AI/ML infrastructure — securing model serving endpoints, API key rotation, rate limiting LLM APIs, network isolation for inferen... | — |
| `ai-sre-incident-response` | Use when an AI/LLM system is involved in a production incident — agent runaway loops, cost spikes, model degradation, hallucination-caused bad acti... | — |
| `llm-app-security` | Use when building application-layer security for LLM-powered features — output validation, PII filtering, content moderation, output format enforce... | — |
| `llm-caching` | Use when reducing LLM API costs and latency through semantic caching, prompt caching (provider-native), response memoization, and embedding-based c... | — |
| `llm-cost-optimization` | Use when reducing LLM API spend — model tier selection per task, token budget management, prompt compression, batch API usage for async workloads, ... | — |
| `llmops-platform-engineering` | Use when building the platform layer for LLM operations — API gateway for model routing, shared inference infrastructure, A/B model deployment, fea... | — |
| `mcp-server-security` | Use when securing MCP (Model Context Protocol) servers — transport encryption, tool-level authorization, input validation on tool arguments, output... | — |
| `mcp-tool-design-patterns` | Use when designing MCP (Model Context Protocol) tools — input schemas, error handling, idempotency, pagination, naming conventions. Covers validati... | `references/` |
| `model-registry-governance` | Use when managing model lifecycle governance — tracking which models are deployed where, version control for model artifacts, approval workflows fo... | — |
| `model-supply-chain-security` | Use when securing the model artifact supply chain — verifying model provenance, detecting tampered weights, signing model artifacts, scanning for e... | — |
| `prompt-injection-defense` | Use when defending against prompt injection carried in untrusted input — detecting injected instructions in fetched content, tool results, RAG chun... | — |
| `rag-observability-evals` | Use when measuring RAG pipeline quality — retrieval precision/recall, answer groundedness (faithfulness to retrieved context), chunk relevance scor... | — |

</details>

<details>
<summary><strong>apm-metrics</strong> (50) — Metric-by-metric diagnostic references for platform components.</summary>

| Skill | Description | Includes |
| --- | --- | --- |
| `apm-metrics-cross-runtime` | Compare RED and runtime metrics across language runtimes. | — |
| `argo-events-metrics` | Diagnose Argo Events delivery and sensor triggers. | — |
| `argo-rollouts-metrics` | Diagnose progressive delivery and analysis runs. | — |
| `argo-workflows-metrics` | Diagnose workflow controller backlog and queues. | — |
| `argocd-metrics` | Diagnose Argo CD sync failures and reconcile latency. | — |
| `aws-csi-driver-metrics` | Diagnose EBS, EFS and S3 CSI volume operations. | — |
| `aws-load-balancer-controller-metrics` | Diagnose ALB controller reconcile and AWS API errors. | — |
| `backing-services-metrics` | Diagnose Redis, PostgreSQL and CoreDNS saturation. | — |
| `backstage-metrics` | Assess Backstage portal metric availability gaps. | — |
| `cert-manager-metrics` | Diagnose certificate issuance and ACME rate limits. | — |
| `collector-internal-metrics` | Diagnose OTel Collector loss and backpressure. | — |
| `crossplane-metrics` | Diagnose Crossplane reconcile and provider API health. | — |
| `datahub-metrics` | Diagnose DataHub JVM, Kafka lag and GraphQL latency. | — |
| `defectdojo-metrics` | Assess DefectDojo nginx exporter metric coverage. | — |
| `dependency-track-metrics` | Diagnose Dependency-Track ORM, pool and event health. | — |
| `descheduler-metrics` | Track pod eviction counts and descheduler loops. | — |
| `dotnet-apm-metrics` | Diagnose .NET GC, ThreadPool, Kestrel and EF Core. | — |
| `external-dns-metrics` | Diagnose DNS record sync and provider API errors. | — |
| `external-secrets-metrics` | Diagnose secret sync failures and store readiness. | — |
| `gitlab-runner-metrics` | Diagnose runner job capacity and queue saturation. | — |
| `go-apm-metrics` | Diagnose Go GC, scheduler and memory classes. | — |
| `grafana-self-metrics` | Diagnose Grafana HTTP, datasource and alert health. | — |
| `harbor-metrics` | Diagnose Harbor registry push, pull and job queues. | — |
| `ingress-nginx-metrics` | Diagnose ingress latency and upstream errors. | — |
| `istio-ambient-metrics` | Diagnose ztunnel and waypoint L4/L7 telemetry. | — |
| `k8s-pvc-tagger-metrics` | Track PVC tagging reconcile and AWS tag errors. | — |
| `k8s-workload-metrics` | Diagnose pod, container and workload resource health. | — |
| `karpenter-metrics` | Diagnose node provisioning and disruption events. | — |
| `keda-metrics` | Diagnose KEDA scaler errors and scaling activity. | — |
| `keycloak-metrics` | Diagnose Keycloak login, token and JVM health. | — |
| `kiali-metrics` | Diagnose Kiali API latency and graph generation. | — |
| `kubecost-metrics` | Diagnose Kubecost allocation and ETL pipeline health. | — |
| `kubescape-metrics` | Track posture scan results and control failures. | — |
| `kyverno-metrics` | Diagnose policy admission latency and rule results. | — |
| `loki-tempo-self-metrics` | Diagnose Loki and Tempo ingest, query and compaction. | — |
| `metrics-server-metrics` | Diagnose metrics-server scrape and API latency. | — |
| `nexus3-metrics` | Diagnose Nexus repository JVM and storage health. | — |
| `nodejs-apm-metrics` | Diagnose Node.js event loop, heap and HTTP health. | — |
| `opensearch-metrics` | Diagnose OpenSearch cluster, shard and JVM health. | — |
| `pyroscope-self-metrics` | Diagnose Pyroscope ingest and profile storage health. | — |
| `python-apm-metrics` | Diagnose Python GC, WSGI/ASGI and runtime health. | — |
| `reloader-metrics` | Track config and secret reload triggers. | — |
| `scaleops-metrics` | Diagnose ScaleOps rightsizing and automation health. | — |
| `sonarqube-metrics` | Diagnose SonarQube JVM, scan queue and DB health. | — |
| `strimzi-kafka-metrics` | Diagnose Kafka broker, topic and consumer lag. | — |
| `superset-metrics` | Diagnose Superset query, cache and worker health. | — |
| `trace-derived-metrics` | Use Tempo service graph metrics for RED analysis. | — |
| `traefik-metrics` | Diagnose Traefik router, service and TLS health. | — |
| `velero-metrics` | Track backup, restore and snapshot success rates. | — |
| `victoriametrics-self-metrics` | Diagnose VM ingest, query and storage saturation. | — |

</details>

<details>
<summary><strong>aws</strong> (21) — AWS service design and troubleshooting patterns.</summary>

| Skill | Description | Includes |
| --- | --- | --- |
| `agent-instruction-authoring` | Use when writing or editing an agents_md or a SKILL.md for the AWS DevOps Agent. Carries the rule that an instruction must prescribe substance rath... | — |
| `agent-skills-adversarial-review` | Refute a document with independent reviewers before commit. | — |
| `agent-skills-cost-modelling` | Estimate agent cost from observed duration, not guesses. | — |
| `agent-skills-debugging` | Troubleshooting guide for when a skill doesn't load, loads but produces empty results, or loads but the agent ignores its procedure. | — |
| `agent-skills-harness-guide` | How to run the behaviour harness, interpret results, add new cases, understand costs, and recover from common failures. | — |
| `agent-skills-import-and-harness` | Use when importing assets to the agentspace or running the behaviour harness. Carries every API constraint that cost a failed attempt — sourceUrl b... | — |
| `agent-skills-metric-verification` | Use before writing, editing or reviewing any metric name or PromQL query in this repo. Carries the verified environment traps — the inconsistent `_... | — |
| `agent-skills-new-skill-checklist` | Step-by-step procedure for adding a new skill to the AWS DevOps Agent catalog — from scaffolding through import and validation. | — |
| `agent-skills-readonly-invariant` | Use when touching the read-only prohibition, the agents_md, the tool associations, or anything about what the agent may execute. Carries the invari... | — |
| `agent-skills-sandbox-development` | How to build skills with executable code for the AWS DevOps Agent sandbox — bundling Python/bash scripts, filesystem layout, pre-installed packages... | — |
| `agent-skills-specs-authoring` | Where planning artefacts go, and what makes one valid. | — |
| `aws-devops-agent-skills` | Use when authoring, importing, validating, or troubleshooting skills for the AWS DevOps Agent (aidevops) — writing SKILL.md, choosing agent_types, ... | — |
| `cloudfront-patterns` | Configure CloudFront origins, caching and WAF. | — |
| `cost-explorer` | Analyze AWS spend via Cost Explorer and CUR Athena. | — |
| `eks-management` | Manage EKS nodes, Karpenter, IRSA and upgrades. | — |
| `eks-node-troubleshooting` | Use when pods are Pending with scheduling failures, nodes show NotReady, Karpenter isn't provisioning, spot interruptions caused rescheduling, or n... | — |
| `iam-patterns` | Design least-privilege IAM roles and policies. | — |
| `lambda-patterns` | Design Lambda cold start, VPC and observability. | — |
| `rds-patterns` | Design RDS sizing, failover and backup strategy. | — |
| `route53-patterns` | Design Route 53 zones, records and health checks. | — |
| `security-hub-patterns` | Configure Security Hub standards and aggregation. | — |

</details>

<details>
<summary><strong>containers</strong> (8) — Docker, Compose, image building, and runtime debugging.</summary>

| Skill | Description | Includes |
| --- | --- | --- |
| `buildkit-cache-optimization` | Use when Docker builds are slow in CI. Covers layer ordering, cache mounts, registry cache backend, BuildKit inline cache, before/after patterns, a... | — |
| `container-image-optimization` | Shrink image size and speed up builds and pulls. | `references/` |
| `container-runtime-debugging` | Debug crashing, hanging or misbehaving containers. | `references/` |
| `docker-cli-operations` | Run, inspect and debug containers with the Docker CLI. | `references/` |
| `docker-compose-patterns` | Compose multi-container apps with healthchecks and profiles. | `references/` |
| `dockerfile-authoring` | Write small, cacheable, secure Dockerfiles. | `references/` |
| `multi-arch-builds` | Use when building container images for mixed amd64/arm64 clusters (Graviton). Covers buildx setup, Dockerfile TARGETARCH, CI parallel builds, tag c... | — |
| `registry-operations` | Use when managing container registries (Harbor, ECR, GHCR). Covers garbage collection, retention policies, replication, vulnerability scanning inte... | — |

</details>

<details>
<summary><strong>development</strong> (21) — Language, framework, and instrumentation patterns.</summary>

| Skill | Description | Includes |
| --- | --- | --- |
| `agent-platform-design` | Design autonomous agent execution and guardrails. | — |
| `anomaly-detection-deep` | Choose detection algorithms and tune false positives. | — |
| `dotnet-async-patterns` | Write async .NET workers, channels and pipelines. | — |
| `dotnet-otel-patterns` | Instrument .NET workers, spans and debug tracing. | — |
| `frontend-design` | Use when building or restyling a UI that needs a distinct identity — choosing color palettes, typeface pairings, layout concepts, and avoiding gene... | `references/`, `scripts/` |
| `go-patterns` | Write idiomatic Go services, context and gRPC. | — |
| `grpc-distributed-tracing` | Propagate trace context across gRPC languages. | — |
| `interactive-debugging` | Use when you need live process state (locals, call stack, breakpoints) that logs/traces can't answer — via DAP CLI. Covers Python debugpy, Go dlv, ... | `references/` |
| `linkedin-connection-pipeline` | Use when building or extending a vendor-agnostic LinkedIn outreach pipeline — SQLite state machine, retry policies, account rotation, liveness sche... | `scripts/` |
| `mcp-server-development` | Build MCP servers with tools, resources and prompts. | — |
| `prophet-isolation-forest-patterns` | Forecast and detect outliers with Prophet. | — |
| `python-cli-tools` | Use when building a pip-installable CLI with subcommands using Click or Typer, configuring entry points, or migrating from argparse to a proper CLI... | `references/` |
| `python-fastapi-patterns` | Build FastAPI services, deps and validation. | — |
| `python-grpc-aio` | Build async Python gRPC servers and clients. | — |
| `python-otel-patterns` | Instrument Python traces, metrics and logs. | — |
| `python-packaging` | Use when creating a new Python project with pyproject.toml, managing dependencies, configuring virtual environments, or publishing packages. Covers... | `references/` |
| `python-performance` | Use when profiling slow Python code, choosing between threading/multiprocessing/asyncio, diagnosing GIL contention, or optimizing hot paths. Covers... | `references/` |
| `python-scripting` | Use when writing standalone Python scripts that need argument parsing, safe file/path handling, subprocess calls, or structured logging. Covers the... | `references/` |
| `python-testing` | Use when writing pytest test suites, designing fixtures, mocking external dependencies, parametrizing test cases, or measuring coverage. Covers con... | `references/` |
| `secrets-management-dotnet` | Load secrets into .NET configuration safely. | — |
| `telemetry-standard` | Use when integrating telemetry into apps via the shared OTel helper for .NET and Python, choosing between manual OTel SDK config vs the corporate l... | — |

</details>

<details>
<summary><strong>documentation</strong> (9) — Technical writing, diagrams, and docs-site conventions.</summary>

| Skill | Description | Includes |
| --- | --- | --- |
| `adr-template` | Write MADR architecture decision records. | `references/` |
| `api-docs-patterns` | Generate API docs from OpenAPI and protobuf. | `references/` |
| `diagram-patterns` | Choose Mermaid, drawio or ASCII for diagrams. | `references/` |
| `file-organizer` | Scan, dedupe, plan, apply, and undo file reorganizations. | `scripts/` |
| `image-enhancer` | Upscale, sharpen, denoise, and resize images via Pillow. | `scripts/` |
| `invoice-organizer` | Extract, rename, organize, and CSV-export invoices/receipts. | `scripts/` |
| `markdown-docs` | Write structured, reviewable Markdown docs. | — |
| `mkdocs-conventions` | Configure MkDocs Material sites and navigation. | `references/` |
| `pdf-operations` | Extract, merge, split, watermark, OCR, and fill PDF forms. | `references/`, `scripts/` |

</details>

<details>
<summary><strong>finops</strong> (6) — Cost analysis, rightsizing, and commitment planning.</summary>

| Skill | Description | Includes |
| --- | --- | --- |
| `cost-anomaly-detection` | Use when a cost spike appears in billing — AWS Cost Anomaly Detection, CUR queries via Athena, correlation with deploy/traffic changes. Decision tr... | — |
| `data-transfer-cost-analysis` | Use when investigating high data transfer costs in AWS/cloud — cross-AZ, cross-region, internet egress. Covers VPC Flow Logs analysis, OTel eBPF ne... | — |
| `ec2-rightsizing-patterns` | Right-size EC2 with utilization and Optimizer data. | — |
| `reserved-capacity-planning` | Use when evaluating commitment purchases (Reserved Instances, Savings Plans, capacity reservations). Covers utilization analysis, break-even calcul... | — |
| `savings-plans-strategy` | Plan Savings Plans and reserved capacity coverage. | — |
| `untagged-resources-bulk-fix` | Find and bulk-tag untagged AWS resources. | — |

</details>

<details>
<summary><strong>infrastructure</strong> (14) — GitOps, Helm, service mesh, and cluster infrastructure.</summary>

| Skill | Description | Includes |
| --- | --- | --- |
| `argocd-patterns` | Configure ApplicationSets, sync waves and hooks. | `references/` |
| `cosign-image-signing` | Sign and verify container images with cosign. | `references/` |
| `external-secrets-aws-sm` | Sync AWS Secrets Manager into Kubernetes secrets. | `references/` |
| `gitops-environments` | Use when tracing which GitOps repo controls a service, understanding the organization domain-to-namespace-to-cluster mapping, investigating why a d... | `references/` |
| `helm-chart-app` | Deploy apps with the shared application Helm chart. | `references/` |
| `helm-chart-cronworkflow` | Schedule Argo CronWorkflows via the shared chart. | — |
| `helmfile-applicationset` | Register services in GitOps ApplicationSets. | — |
| `helmfile-k8s-addon` | Package cluster addons as helmfile releases. | — |
| `helmfile-templating` | Template helmfile values, envs and secrets. | `references/` |
| `istio-ambient-debugging` | Debug ztunnel, waypoints and ambient traffic. | — |
| `istio-ambient-otel` | Wire ambient mesh telemetry into OTel. | — |
| `karpenter-consolidation` | Tune consolidation and disruption budgets. | — |
| `kyverno-policies` | Apply the shared Kyverno policy baseline. | `references/` |
| `terraform-modules` | Use the shared Terraform module catalog. | — |

</details>

<details>
<summary><strong>linux</strong> (6) — Command line, filesystem, processes, systemd, and performance.</summary>

| Skill | Description | Includes |
| --- | --- | --- |
| `linux-command-line` | Navigate the shell with pipes, globs and job control. | `references/`, `scripts/`, `examples/` |
| `linux-filesystem` | Manage permissions, mounts, links and disk usage. | `references/`, `scripts/` |
| `linux-performance-analysis` | Diagnose CPU, memory, disk and network bottlenecks. | `references/` |
| `linux-process-management` | Inspect processes, signals, limits and cgroups. | `references/`, `scripts/`, `examples/` |
| `systemd-services` | Write, debug and manage systemd units and timers. | `references/`, `scripts/`, `examples/` |
| `ubuntu-administration` | Manage packages, users, network and updates on Ubuntu. | `references/`, `scripts/` |

</details>

<details>
<summary><strong>networking</strong> (7) — TCP/IP, DNS, TLS, firewalls, and packet-level debugging.</summary>

| Skill | Description | Includes |
| --- | --- | --- |
| `dns-troubleshooting` | Diagnose DNS resolution failures with dig and resolvectl. | `references/` |
| `linux-firewall` | Write and debug nftables/iptables firewall rules. | `references/` |
| `load-balancer-troubleshooting` | Use when debugging ALB/NLB/ingress controller target group issues — 502/503/504 errors, failing health checks, connection draining problems, cross-... | — |
| `network-troubleshooting-tools` | Use ss, tcpdump, curl and traceroute to diagnose issues. | `references/` |
| `service-mesh-troubleshooting` | Use when debugging service mesh issues — mTLS failures, sidecar injection problems, traffic policy misroutes, proxy latency overhead, or config syn... | — |
| `tcp-ip-fundamentals` | Understand TCP handshakes, states and packet flow. | `references/` |
| `tls-troubleshooting` | Diagnose certificate chains, expiry and handshake failures. | `references/` |

</details>

<details>
<summary><strong>observability</strong> (28) — Telemetry pipelines, query languages, and signal correlation.</summary>

| Skill | Description | Includes |
| --- | --- | --- |
| `alertmanager-slack-config` | Route Alertmanager alerts to Slack with context. | `references/` |
| `cardinality-explosion-finder` | Use when VictoriaMetrics is OOMing, vmselect queries are slow, or TSDB cardinality is growing unexpectedly. Runs a bundled Python script that analy... | `references/` |
| `fluent-bit-loki-pipeline` | Ship logs to Loki with labels and multiline parsing. | — |
| `fluent-bit-vs-otel-logs` | Compare Fluent Bit and OTel log collection paths. | — |
| `grafana-cross-signal-correlation` | Link metrics, traces, logs and profiles in Grafana. | — |
| `kafka-pipeline-health` | Monitor and troubleshoot the Kafka buffer in the OTel telemetry pipeline (Strimzi-managed, KRaft mode). Symptoms: growing consumer lag for otel-pro... | `references/` |
| `kubelet-scrape-architecture` | Understand kubelet and cAdvisor scrape paths. | — |
| `kuma-synthetic-status` | Use when you need to verify whether an API endpoint is actually responding from an external perspective (synthetic test), check endpoint latency as... | — |
| `log-pattern-analyzer` | Use when investigating log volume spikes, identifying dominant error patterns, or detecting anomalous log messages during an incident. Runs a bundl... | `references/` |
| `loki-logql-patterns` | Query logs with LogQL filters and aggregations. | — |
| `monitoring-stack-overview` | Navigate the monitoring stack topology. | — |
| `multicluster-label-strategy` | Align cluster labels for multi-cluster queries. | — |
| `observability-tooling` | Route observability symptoms to the correct MCP tool with correct parameters. Use as the FIRST skill loaded when any observability investigation be... | `references/` |
| `otel-collector-multi-cluster` | Design multi-cluster OTel Collector pipelines. | `references/` |
| `otel-ebpf-instrumentation` | Instrument services with eBPF, no code changes. | — |
| `otel-pipeline-review` | Proactive operational review of the OTel telemetry pipeline (Evaluation agent type). Produces a findings report covering end-to-end data loss, queu... | `references/` |
| `otel-pipeline-troubleshooting` | Diagnose data loss, backpressure, and failures in the OTel Collector pipeline. Symptoms: missing telemetry in Tempo/Loki/VictoriaMetrics, growing K... | `references/` |
| `pyroscope-profiling-patterns` | Profile CPU and memory continuously with Pyroscope. | — |
| `streaming-aggregation` | Cut cardinality with streaming aggregation rules. | — |
| `tempo-trace-investigation` | Investigate distributed traces using Tempo and TraceQL. Symptoms: high latency on a service, errors propagating across services, need to find which... | `references/` |
| `tempo-traceql-patterns` | Query traces with TraceQL selectors and aggregates. | — |
| `tempo-v3-kafka-operations` | Use when migrating Grafana Tempo v2→v3, operating the v3 Kafka-based ingest path, or debugging partition-ring errors, orphan partitions, OOM on rep... | — |
| `victoriametrics-investigation` | Diagnose VictoriaMetrics cluster issues — slow queries, ingestion bottlenecks, cache misses, storage pressure, remote_write backpressure from vmage... | `references/` |
| `victoriametrics-troubleshooting` | Debug VictoriaMetrics ingest and query failures. | — |
| `victoriametrics-tuning` | Tune VictoriaMetrics retention, memory and dedup. | — |
| `vm-capacity-review` | Proactive VictoriaMetrics capacity and health review (Evaluation agent type). Produces a capacity report covering ingestion rate trend, storage gro... | `references/` |
| `vm-cardinality-management` | Find and cut high-cardinality metric series. | — |
| `vmalert-configuration` | Configure VMAlert rules, groups and notifiers. | `references/` |

</details>

<details>
<summary><strong>projects</strong> (1) — Working context for specific repositories.</summary>

| Skill | Description | Includes |
| --- | --- | --- |
| `telemetry-helper` | Use when working on the StaffOps otel-libs monorepo — releasing new versions, understanding the .NET/Python helper API, or referring to sample apps... | — |

</details>

<details>
<summary><strong>security</strong> (11) — Supply chain, hardening, compliance, and vulnerability management.</summary>

| Skill | Description | Includes |
| --- | --- | --- |
| `aws-ftr-compliance` | Prepare AWS Foundational Technical Review evidence. | — |
| `container-image-apko` | Build hardened base images with apko. | — |
| `container-package-melange` | Build custom APK packages with melange. | — |
| `dependency-track-integration` | Upload SBOMs and manage projects via API. | — |
| `golden-ami-creation` | Build hardened AMIs with Packer and Ansible. | — |
| `linux-hardening` | Apply baseline OS hardening: sysctl, PAM, mounts, kernel. | `references/` |
| `linux-security-auditing` | Audit a Linux host for common misconfigurations. | — |
| `sbom-vulnerability-management` | Generate SBOMs and triage vulnerabilities. | — |
| `secrets-handling-shell` | Avoid leaking secrets through shell history, env and logs. | — |
| `security-hub-findings-mgmt` | Triage and remediate Security Hub findings. | — |
| `ssh-hardening` | Configure SSH for key-only, restricted, auditable access. | `references/` |

</details>

<details>
<summary><strong>shell</strong> (5) — Bash scripting, text processing, CLI design, and shell testing.</summary>

| Skill | Description | Includes |
| --- | --- | --- |
| `bash-error-handling` | Make shell scripts fail fast, loudly, and cleanly. | `references/`, `scripts/`, `examples/` |
| `bash-scripting` | Write portable, safe Bash scripts that fail loudly. | `references/`, `scripts/`, `examples/` |
| `shell-cli-design` | Design CLI tools with sane flags, streams and codes. | `references/`, `scripts/`, `examples/` |
| `shell-testing-linting` | Lint with shellcheck and test scripts with bats. | `references/`, `scripts/`, `examples/` |
| `shell-text-processing` | Transform text with awk, sed, grep, sort and jq. | `references/`, `examples/` |

</details>

<details>
<summary><strong>sre</strong> (17) — Reliability engineering: SLOs, incidents, and error budgets.</summary>

| Skill | Description | Includes |
| --- | --- | --- |
| `alerting-strategy` | Use when designing new alert rules, reducing alert fatigue, routing alerts to correct channels, evaluating alert quality (MTTA/MTTR/false-positive ... | `references/` |
| `capacity-projection` | Use when assessing whether storage, ingestion rate, or resource usage will exhaust capacity before the next review cycle. Runs a bundled Python scr... | `references/` |
| `chaos-engineering-patterns` | Use when designing chaos experiments or running game days. Covers steady state hypothesis, experiment design (pod kill, network partition, CPU stre... | `references/` |
| `deploy-correlation-checker` | Use when an anomaly is detected and you need to determine if a recent deploy caused it. Cross-references deploy timestamps (from ArgoCD) with metri... | `references/` |
| `error-budget-framework` | Use when implementing error budget tracking, burn rate alerting, or defining budget exhaustion policies. Provides complete VMRule recording rules a... | `references/` |
| `incident-response-runbook` | Run incident command, severity and comms. | `references/` |
| `incident-skip-criteria` | Incident Triage agent ONLY. Evaluate whether an alert should be SKIPPED (no paid investigation) or INVESTIGATED. Triggers: every incoming alert bef... | `references/` |
| `incident-triage` | Use when an alert fires (SLOBurnRateP1/P2, PodCrashLooping, HighErrorRate), a user reports service degradation, or pods are in CrashLoopBackOff/OOM... | — |
| `investigation-cost-guardrail` | Applies to EVERY investigation before the first query is executed. Triggered always — enforces time/cost budgets per incident severity, prevents un... | `references/` |
| `metric-correlation-analysis` | Use when multiple metrics anomaly at the same time and you need to determine if they share a common cause. Runs a bundled Python script that detect... | `references/` |
| `on-call-handoff-protocol` | Use when handing off an on-call shift or starting a new one. Structured checklist covering active incidents, recent deploys, error budget burn, sil... | `references/` |
| `post-mortem-templates` | Use when writing a blameless post-mortem after a production incident (SEV1-2 mandatory, SEV3 encouraged). Provides copy-paste templates by severity... | `references/` |
| `root-cause-analysis` | Use when investigating production incidents where the root cause is unknown. Provides structured techniques (5 Whys, fault tree, elimination), cros... | — |
| `runbook-authoring` | Use when writing an operational runbook for a new or existing alert. Every production alert MUST have a linked runbook. Provides copy-paste templat... | — |
| `sla-slo-design` | Use when defining reliability targets (SLI/SLO/SLA) for a new or existing service, choosing service tier, writing recording rules for VictoriaMetri... | — |
| `slo-burn-rate-calculator` | Use when an SLO burn rate alert fires, when assessing budget health during an incident, or when determining how long until the error budget exhaust... | `references/` |
| `symptom-router` | ENTRY POINT — load FIRST when any symptom is reported: \"API is slow\", \"high latency\", \"logs missing\", \"traces missing\", \"metrics missing\"... | `references/` |

</details>

<details>
<summary><strong>troubleshooting</strong> (5) — Systematic diagnosis across systems, network, and logs.</summary>

| Skill | Description | Includes |
| --- | --- | --- |
| `disk-and-memory-issues` | Diagnose OOM kills, leaks, disk pressure and swap. | `references/` |
| `incident-triage-linux` | Triage a live Linux incident quickly and safely. | `references/` |
| `linux-troubleshooting-methodology` | Apply a systematic approach to diagnosing Linux issues. | `references/` |
| `log-analysis` | Extract signal from logs with grep, awk and journalctl. | `references/` |
| `systematic-debugging` | Investigate root cause before proposing any fix. | `references/`, `scripts/`, `examples/` |

</details>

<details>
<summary><strong>workflows</strong> (14) — Team conventions and delivery workflows.</summary>

| Skill | Description | Includes |
| --- | --- | --- |
| `conventional-commits` | Write Conventional Commits and changelogs. | — |
| `git-advanced` | Rebase, bisect and recover Git history safely. | — |
| `git-guardrails` | Block destructive git commands before Claude runs them. | `references/`, `scripts/` |
| `gitops-environment-onboard` | Onboard a service into the GitOps pipeline. | — |
| `harness-score-audit` | Use when auditing a repository's AI agent harness maturity or improving its score. The harness-score tool (MIT, npx harness-score) measures 6 dimen... | `references/` |
| `how-this-agent-works` | Understand this agent's skills and steering. | — |
| `jira-conventions` | Write Jira issues with consistent conventions. | — |
| `local-reference-docs` | Find vendored reference docs offline. | — |
| `pipeline-template-apps` | Wire apps into the shared CI/CD templates. | — |
| `session-handoff` | Hand off an incident or migration to the next on-call shift. | `references/` |
| `skill-authoring` | Use when creating a new SKILL.md, rewriting a description that doesn't trigger correctly, splitting an overgrown skill into references/, or decidin... | `references/` |
| `skill-eval-harness` | Use when validating whether a skill edit actually improved behavior, running paired budget-capped evals against case files, checking trigger collis... | `references/`, `scripts/` |
| `skill-share` | Use when scaffolding a new skill directory, running per-skill validation, packaging a skill as a zip for distribution, or formatting an announcemen... | `scripts/` |
| `spec-writing` | Write requirements, design and task specs. | — |

</details>

<!-- catalog:end -->

## Validation

`tools/validate_skills.py` enforces the contract above — layout, required
frontmatter keys, the description limit, category consistency, resolvable
`related_skills`, and English-only prose:

```bash
python3 tools/validate_skills.py
# validated 229 skills, 270 error(s)   <- 270 pre-existing: bulk-imported
#                                          skills lack version/author/license/platforms
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
