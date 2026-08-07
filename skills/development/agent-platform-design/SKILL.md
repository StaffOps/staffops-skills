---
name: agent-platform-design
description: "Design autonomous agent execution and guardrails."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [agent, platform, design, development]
    category: development
    related_skills: [sla-slo-design, how-this-agent-works]
---
# Autonomous Agent Platform Design

Five execution patterns for AI agents operating independently within <org> infrastructure.

---

## When to Use

Autonomous agent platform design patterns. Use when designing AI agents that operate independently (cron-triggered, webhook-triggered, Slack bots, multi-agent orchestration, CI-triggered). Covers 5 execution patterns, state management, observability, safety guardrails, and <org> integration points.

## Pattern 1: Cron-triggered Agent

Scheduled execution on a fixed cadence. Simplest autonomous pattern.

**Use cases**: daily cost reports, weekly security audits, nightly data quality checks.

**Architecture**:
```
CronWorkflow → Agent Container → Read State (Redis/S3) → Execute → Write Results → Notify (Slack)
```

**State**: previous run results in S3/Redis. Execution MUST be idempotent — same input produces same output, safe to retry.

**<org> fit**: Argo CronWorkflow + corporate `cronworkflow` Helm chart. Image in Harbor (signed, multi-arch). Secrets via External Secrets. AWS access via IRSA.

**Example** — daily FinOps report:
```yaml
apiVersion: argoproj.io/v1alpha1
kind: CronWorkflow
metadata:
  name: finops-daily-report
spec:
  schedule: "0 8 * * *"
  workflowSpec:
    entrypoint: report
    templates:
      - name: report
        container:
          image: <harbor-registry>/<harbor-project>/finops-agent:v1.0.0
          env:
            - name: SERVICE_NAME
              value: finops-daily-report
            - name: ENVIRONMENT
              value: PRD
```

**Rules**: container exits after completion, timeout configured, failure alerts via Alertmanager → Slack, retry with backoff (Argo-native).

---

## Pattern 2: Webhook-triggered Agent

Event-driven execution triggered by external HTTP calls.

**Use cases**: PR review bot, alert enrichment, auto-remediation on specific alerts.

**Architecture**:
```
External Event (webhook) → HTTP Endpoint (FastAPI/Go) → Validate + Deduplicate → Agent Logic → Act
```

**State**: event log in PostgreSQL/DynamoDB for audit. Deduplication via event ID hash (GitLab `X-Gitlab-Event-UUID`, AlertManager `groupKey`).

**<org> fit**: K8s Deployment + Service + Istio VirtualService. KEDA ScaledObject on queue depth for async processing. Health endpoints mandatory.

**Example** — AlertManager enrichment:
```python
@app.post("/webhook/alertmanager")
async def handle_alert(request: Request):
    payload = await request.json()
    for alert in payload.get("alerts", []):
        alert["annotations"]["runbook"] = find_runbook(alert["labels"])
        alert["annotations"]["recent_deploys"] = await get_recent_deploys(
            service=alert["labels"].get("service_name")
        )
        await post_to_slack(alert)
    return {"status": "ok"}
```

**Rules**: respond within 5s (acknowledge fast, process async if heavy), validate webhook signature, rate limit inbound requests.

---

## Pattern 3: Slack Bot Agent

Interactive agent in Slack for ChatOps and knowledge access.

**Use cases**: `/deploy`, `/status`, `/rollback`, on-call helper, knowledge Q&A.

**Architecture**:
```
Slack User → Slack Events API → Message Queue (Redis/SQS) → Worker Process → Slack API Response
```

**State**: conversation context in Redis (TTL 5-15 min per thread), user preferences in DynamoDB, action audit log in PostgreSQL.

**<org> fit**: `devops-agent-api` project (Python, existing). Slack channels `#eks-notifications*`. Webhook secret in AWS Secrets Manager.

**Safety controls**:
- Destructive commands (`deploy`, `rollback`, `scale`) require confirmation button
- RBAC via Slack user group membership
- Rate limit per user
- All actions logged with user + timestamp

**Example** — `/deploy` flow:
```
User: /deploy people-api prd
Bot: ⚠️ Deploy people-api to PRD? [Confirm] [Cancel]
User: [clicks Confirm]
Bot: 🚀 Triggered ArgoCD sync for people-api (PRD). Tracking in thread...
Bot: ✅ Rollout complete. 3/3 pods healthy. Duration: 45s.
```

**Rules**: acknowledge slash commands within 3s, use threads for multi-step interactions, graceful degradation when backends unreachable.

---

## Pattern 4: Multi-Agent Orchestration

Multiple specialized agents coordinated by a central orchestrator.

**Use cases**: incident response, security audits, platform migrations.

**Architecture**:
```
Orchestrator → spawns [Agent A, Agent B, Agent C] (parallel) → Consolidate Results
```

**Coordination patterns**:

| Pattern | When | Example |
|---------|------|---------|
| Fan-out/fan-in | Independent parallel tasks | Check logs + metrics + deploys simultaneously |
| Pipeline | Sequential dependencies | Validate → migrate → verify |
| Supervisor/worker | Dynamic task distribution | Assign scan targets to N workers |

**State**: message passing via task queue (Redis Streams, SQS). NO shared memory. Orchestrator tracks completion and aggregates results.

**<org> fit**: staffops subagent model (already implemented — fan-out/fan-in with `summary` tool). Argo Workflows for container-based DAGs.

**Example** — incident response:
```go
func HandleIncident(ctx context.Context, alert Alert) (*Summary, error) {
    g, ctx := errgroup.WithContext(ctx)
    var logs, metrics, deploys interface{}
    g.Go(func() error { logs, _ = agents.AnalyzeLogs(ctx, alert); return nil })
    g.Go(func() error { metrics, _ = agents.CheckMetrics(ctx, alert); return nil })
    g.Go(func() error { deploys, _ = agents.FindRecentDeploys(ctx, alert); return nil })
    g.Wait()
    return consolidate(logs, metrics, deploys), nil
}
```

**Rules**: orchestrator has global timeout, individual agent failures produce partial results (not crash), results are immutable once produced.

---

## Pattern 5: CI-triggered Agent

Runs as a job within CI/CD pipelines, triggered by code changes.

**Use cases**: automated code review, security scanning with AI triage, test generation, documentation generation.

**Architecture**:
```
MR Created → GitLab CI Job → Agent Container (reads repo) → Produce Artifacts (MR comments, files)
```

**State**: Git repo IS the state. No persistent state needed — deterministic on same commit SHA.

**<org> fit**: GitLab CI shared templates (extend `review` stage). Harbor-hosted agent image. GitLab CI job token for MR API access.

**Example** — observability review:
```yaml
review:observability:
  stage: review
  image: <harbor-registry>/<harbor-project>/otel-review-agent:v1.0.0
  script:
    - agent-review --diff "${CI_MERGE_REQUEST_DIFF_BASE_SHA}..${CI_COMMIT_SHA}"
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  allow_failure: true  # Advisory, not blocking
```

**Rules**: results advisory by default (`allow_failure: true`), deterministic output, fast execution (cache aggressively), isolated container with minimal permissions.

---

## Cross-cutting Concerns

### State Management

| Store | Use for | TTL |
|-------|---------|-----|
| Redis | Caches, conversation context, dedup keys | Minutes–hours |
| S3 | Reports, artifacts, baselines | Indefinite |
| DynamoDB/PostgreSQL | Audit logs, structured state, preferences | Indefinite |

**Rule**: agents are stateless processes (12-factor). ALL state in backing services. Pod dies → no data loss.

### Observability

All agents emit telemetry via <org> OTel Helper (`services.AddOtelHelper()` / `setup_telemetry()`).

Custom metrics per agent:

| Metric | Type | Labels |
|--------|------|--------|
| `agent_executions_total` | Counter | `agent_name`, `status` |
| `agent_execution_duration_seconds` | Histogram | `agent_name` |
| `agent_errors_total` | Counter | `agent_name`, `error_type` |
| `agent_llm_tokens_total` | Counter | `agent_name`, `model`, `direction` |

Traces: one root trace per execution (use `StartRootActivity` / `start_root_span` for workers).

### Safety Guardrails

| Guardrail | Implementation |
|-----------|----------------|
| Read-only default | No write capability unless explicitly granted |
| Human-in-the-loop | Destructive actions require approval (Slack button, MR approval) |
| Rate limiting | Max N executions per minute/hour |
| Circuit breaker | Disable if error rate > 50% over 5 min |
| Audit log | Every action recorded with timestamp + context |
| Kill switch | ConfigMap toggle — disable without redeploy |

### Cost Control

| Control | Implementation |
|---------|----------------|
| Response caching | Hash input → check Redis before LLM call |
| Budget limits | Daily/monthly token cap per agent (alert 80%, stop 100%) |
| Model tiering | Large model for reasoning, small for classification |
| Token monitoring | `agent_llm_tokens_total` → Grafana dashboard + alerts |

### Security

- **AWS access**: IRSA (one IAM role per agent, least privilege)
- **Secrets**: External Secrets Operator (never in code)
- **Network**: NetworkPolicies restricting egress to required endpoints
- **Images**: signed with cosign, scanned with Trivy, pulled through Harbor
- **Input**: sanitize all webhook payloads, reject malformed input

---

## Decision Matrix

| Trigger | Latency | State complexity | Pattern |
|---------|---------|-----------------|---------|
| Time-based | Minutes OK | Low | **Cron** |
| External event | Seconds | Medium | **Webhook** |
| Human interaction | Real-time | High (conversation) | **Slack Bot** |
| Complex workflow | Minutes | High (coordination) | **Multi-Agent** |
| Code change | Minutes | Low (repo is state) | **CI-triggered** |

Patterns compose: cron detects anomaly → webhook enriches → Slack bot notifies. Slack bot receives `/investigate` → multi-agent orchestration → reports in thread.

---

## Anti-patterns

- ❌ Agent without observability — invisible failures
- ❌ Agent without kill switch — can't stop runaway execution
- ❌ Shared mutable state between agents — race conditions
- ❌ No rate limiting on LLM calls — cost explosion overnight
- ❌ Agent requiring human for every action — not autonomous
- ❌ Agent without audit log — "what did it do at 3 AM?" unanswerable
- ❌ Monolithic agent doing everything — use specialized agents
- ❌ No timeout on execution — infinite loops consume resources forever
- ❌ Agent that modifies its own config — unpredictable self-modification
- ❌ Deploying to PRD without testing in DEV — production is not a test environment

---

## Related skills

When extending an autonomous agent with external tools/data sources, expose them via MCP — see [`mcp-server-development`](../mcp-server-development/SKILL.md). Common pattern: cron-triggered agent calls MCP tools that wrap APIs (Grafana, ArgoCD, Cost Explorer) instead of duplicating client code.

For specific implementation patterns:
- `python-fastapi-patterns` — webhook endpoint design (Pattern 2)
- `python-grpc-aio` — multi-agent gRPC orchestration (Pattern 4)
- `dotnet-otel-patterns` — `StartRootActivity` for worker traces
- `telemetry-standard` — observability integration (`AddOtelHelper`/`setup_telemetry`)
- `helm-chart-cronworkflow` — corporate cron chart for Pattern 1
- `helm-chart-app` — corporate app chart for Patterns 2/3
- `cosign-image-signing` — golden/base image signing (app images inherit trust)
