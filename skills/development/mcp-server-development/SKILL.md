---
name: mcp-server-development
description: "Build MCP servers with tools, resources and prompts."
version: 1.1.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [mcp, server, development]
    category: development
    related_skills: [metrics-server-metrics, skill-eval-harness, external-secrets-aws-sm, telemetry-standard]
---
# MCP Server Development

How to build Model Context Protocol (MCP) servers from scratch, deployable on <org> infrastructure.

---

## When to Use

Use when building MCP (Model Context Protocol) servers — Python SDK, TypeScript SDK, tool/resource/prompt primitives, transport (stdio vs HTTP), Kiro CLI integration, Docker/Harbor deploy, IRSA, OTel observability. Covers protocol basics, server architecture, testing, production deploy patterns at <org>.

## Overview

MCP (Model Context Protocol) is an open standard that lets AI assistants (Claude, Kiro CLI, custom agents) interact with external systems through a unified interface. An MCP server exposes **tools**, **resources**, and **prompts** that clients discover and invoke dynamically — no hardcoded integrations.

**When to build an MCP server** (vs use existing):
- You need to expose <org>-internal systems (VictoriaMetrics, ArgoCD, GitLab, AWS) to AI agents
- No community server covers your use case
- You want fine-grained access control over what the agent can do
- You need <org>-specific enrichment (mandatory tags, IRSA, OTel)

**When NOT to build**: if a well-maintained community server exists (filesystem, GitHub, PostgreSQL) — use it and configure access.

> Cross-reference: for autonomous agents that USE MCP servers as tool sources, see `agent-platform-design` skill.

---

## Verify Against Live Docs, Not Cached Knowledge

MCP is a young, actively evolving protocol. SDK method names, the spec itself, and even parts of this skill's own code samples can drift out of date between when they were written and when you read them. Treat every snippet below as a **pattern**, not a permanent API contract — before writing real code, confirm the exact current method names against the live docs:

- MCP spec: WebFetch `https://modelcontextprotocol.io/sitemap.xml` to find the current version path, then fetch that page with a `.md` suffix
- Python SDK: WebFetch `https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/README.md`
- TypeScript SDK: WebFetch `https://raw.githubusercontent.com/modelcontextprotocol/typescript-sdk/main/README.md`

**Worked example of why this matters**: the TypeScript SDK's tool-registration call moved from `server.tool(name, description, schema, handler)` to `server.registerTool(name, config, handler)`, where `config` bundles `title`, `description`, `inputSchema`, `outputSchema`, and `annotations` into one object (see the Tool Annotations checklist under "Defining Tools" below). A server built from an older tutorial — or from a stale copy of this exact skill — still compiles and runs against `server.tool()` today, but silently ships without the annotations that clients and reviewers now expect, and sits on a call that the SDK may eventually drop. The lesson isn't "use `registerTool`" specifically — that fact itself will age. It's that you re-verify current method names each time against the live SDK README, rather than trusting any single cached source, including this skill, to still be accurate.

---

## Protocol Basics

MCP uses **JSON-RPC 2.0** over two transport modes: stdio (local) or HTTP+SSE (remote).

### Message flow

```
Client                          Server
  │── initialize ──────────────→│   (capability negotiation)
  │←── initialize result ───────│   (server capabilities + info)
  │── initialized ─────────────→│   (client confirms)
  │                              │
  │── tools/list ──────────────→│   (discover available tools)
  │←── tools/list result ───────│   (tool schemas)
  │── tools/call ──────────────→│   (invoke a tool)
  │←── tools/call result ───────│   (tool output)
  │                              │
  │── resources/list ──────────→│   (discover resources)
  │── resources/read ──────────→│   (read a resource)
  │── prompts/list ────────────→│   (discover prompts)
  │── prompts/get ─────────────→│   (get a prompt template)
```

### Capability negotiation

During `initialize`, server declares what it supports:

```json
{
  "capabilities": {
    "tools": {},
    "resources": { "subscribe": true },
    "prompts": {}
  },
  "serverInfo": { "name": "<org>-victoria-metrics", "version": "1.0.0" }
}
```

Client only calls primitives the server declared. Omit `"prompts"` if you don't expose any.

---

## Server Architecture — The 3 Primitives

### Tools (callable actions)

Functions the agent can invoke. Side effects allowed.

| Use when | Example |
|----------|---------|
| Agent needs to ACT on a system | `query_metrics`, `create_alert_rule`, `restart_rollout` |
| Operation has parameters | `scale_deployment(name, replicas)` |
| Result depends on runtime state | `get_pod_logs(namespace, pod, since)` |

Response format: `content[]` array with `type: "text"` or `type: "image"`.

### Resources (read-only data)

Static or semi-static data the agent can read. No side effects.

| Use when | Example |
|----------|---------|
| Exposing documentation/config | `resource://runbooks/high-cpu` |
| Current state snapshot | `resource://cluster/dev/namespaces` |
| Data that changes infrequently | `resource://tags/cost-centers` |

URI pattern: `resource://<domain>/<path>`. Content types: `text/plain`, `text/markdown`, `application/json`.

### Prompts (templated interactions)

Pre-built prompt templates with parameters. Guide the agent's behavior for specific workflows.

| Use when | Example |
|----------|---------|
| Standardized analysis workflow | `prompt://incident-triage(service, timerange)` |
| Complex multi-step reasoning | `prompt://cost-analysis(cost_center, period)` |
| Enforcing output format | `prompt://generate-runbook(alert_name)` |

---

## Python SDK Quickstart

### Install

```bash
docker run --rm -v $(pwd):/app -w /app python:3.11-slim \
  pip install "mcp[cli]" -q
```

### Minimal server

```python
# server.py
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool, Resource
import asyncio

server = Server("<org>-example")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="query_metrics",
            description="Query VictoriaMetrics with MetricsQL",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "MetricsQL expression"},
                    "step": {"type": "string", "default": "1m"},
                },
                "required": ["query"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "query_metrics":
        result = await do_vm_query(arguments["query"], arguments.get("step", "1m"))
        return [TextContent(type="text", text=result)]
    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
```

### Decorator-based (mcp[cli] FastMCP)

```python
# server_fast.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("<org>-vm-server")


@mcp.tool()
async def query_metrics(query: str, step: str = "1m") -> str:
    """Query VictoriaMetrics with MetricsQL expression."""
    result = await do_vm_query(query, step)
    return result


@mcp.resource("resource://cluster/{cluster_name}/namespaces")
async def list_namespaces(cluster_name: str) -> str:
    """List namespaces in a given cluster."""
    return await get_namespaces(cluster_name)


@mcp.prompt()
async def incident_triage(service: str, timerange: str = "1h") -> str:
    """Triage an incident for a given service."""
    return f"""Analyze the following service for anomalies:
Service: {service}
Timerange: last {timerange}

Steps:
1. Query error rate via query_metrics
2. Check recent logs
3. Identify root cause
4. Suggest mitigation"""


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

---

## TypeScript SDK Quickstart

```typescript
// server.ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const server = new McpServer({ name: "<org>-example", version: "1.0.0" });

server.registerTool(
  "query_metrics",
  {
    title: "Query Metrics",
    description: "Query VictoriaMetrics with MetricsQL",
    inputSchema: { query: z.string(), step: z.string().default("1m") },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
  },
  async ({ query, step }) => {
    const result = await doVmQuery(query, step);
    return { content: [{ type: "text", text: result }] };
  }
);

const transport = new StdioServerTransport();
await server.connect(transport);
```

> Note `registerTool()` here, not the older `server.tool()` form — see "Verify Against Live Docs" above for why that distinction matters and why you should still double-check it against the live SDK docs rather than trusting this example indefinitely.

Build via Docker (no local Node):
```bash
docker run --rm -v $(pwd):/app -w /app node:20-slim sh -c \
  "npm install && npx tsc"
```

---

## Transport Modes

### stdio (local)

```
Client process ←→ stdin/stdout ←→ Server process
```

- **When**: CLI tools (Kiro, Claude Desktop), local development, single-user
- **Pros**: zero network config, simplest setup, no auth needed
- **Cons**: must run on same machine, one client per server process

### HTTP + SSE (remote)

```
Client ──HTTP POST──→ Server (stateless)
Client ←──SSE────── Server (streaming responses)
```

- **When**: shared server (multi-tenant), remote access, production deployment
- **Pros**: multi-client, OAuth support, load-balanceable, standard HTTP infra
- **Cons**: needs auth, TLS, more complex setup

**<org> recommendation**: start with stdio for development/Kiro CLI integration. Move to HTTP when the server needs to serve multiple agents or run as a shared service in EKS.

---

## Defining Tools

### Scope discipline: fewer, higher-leverage tools

It's tempting to default to "comprehensive API coverage" — one tool per REST endpoint. Resist that by default. Every tool definition (name, description, full JSON Schema) is loaded into the agent's context on every turn a client has that server attached, whether or not the tool gets called — a server with 40 thin wrapper tools taxes every conversation that connects to it, not just the ones that use all 40.

Prefer a smaller set of **workflow tools** that compose what an agent actually needs to do in one call, over a large set of **thin wrapper tools** that each expose one endpoint 1:1:

| Prefer | Over |
|--------|------|
| `triage_incident(service, timerange)` — queries metrics + logs + recent deploys, returns one synthesized summary | `query_metrics()`, `query_logs()`, `list_deploys()` called separately, with the agent responsible for chaining and correlating them itself |
| `get_pod_status(namespace, pod)` returning health + recent events + restart count in one payload | 3 separate tools the agent must remember to call and merge |

**Rough ceiling**: if a single server is heading past ~15-20 tools, stop and ask whether it should split by domain (see the anti-pattern list below) or whether several of those tools should collapse into fewer, higher-leverage ones. Treat this as a flag for reconsideration, not a hard limit — a server wrapping a genuinely wide API surface may justify more, but justify it deliberately rather than defaulting to it. This is a departure from "when uncertain, prioritize comprehensive coverage": that default produces bloated servers unless something actively counterbalances it, and at <org> scale — agents juggling MCP servers from several domains in one session — the context-window cost of tool definitions is a bigger everyday constraint than API completeness.

### Naming conventions

- Lowercase with underscores: `query_metrics`, `list_pods`, `create_alert`
- Verb-first: action the tool performs
- Scoped prefix for multi-domain servers: `vm_query`, `loki_search`, `argo_sync`

### Input schema (JSON Schema)

```python
Tool(
    name="scale_deployment",
    description="Scale a deployment to N replicas. Requires approval for PRD.",
    inputSchema={
        "type": "object",
        "properties": {
            "namespace": {"type": "string"},
            "deployment": {"type": "string"},
            "replicas": {"type": "integer", "minimum": 0, "maximum": 50},
            "cluster": {"type": "string", "enum": ["dev", "prd-nv", "core-devops"]},
        },
        "required": ["namespace", "deployment", "replicas", "cluster"],
    },
)
```

### Tool annotations (mandatory before shipping)

Every tool ships with a hint object describing its behavior. Clients — and human reviewers — use these to decide what's safe to call without confirmation, what needs an approval gate, and what's safe to retry:

| Annotation | Type | Default | Meaning |
|------------|------|---------|---------|
| `readOnlyHint` | boolean | `false` | Tool does not modify state |
| `destructiveHint` | boolean | `true` | Tool may perform destructive updates (only meaningful when `readOnlyHint: false`) |
| `idempotentHint` | boolean | `false` | Repeated calls with identical arguments have no additional effect |
| `openWorldHint` | boolean | `true` | Tool interacts with an external, not-fully-enumerable system |

```python
Tool(
    name="query_metrics",
    description="Query VictoriaMetrics with MetricsQL",
    inputSchema={...},
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
```

Checklist before merging any new tool:

- [ ] `readOnlyHint` set explicitly — don't rely on the `false` default for a tool that IS read-only; an unset hint reads as "assume destructive"
- [ ] `destructiveHint` set to `true` for anything that deletes, scales, restarts, or otherwise mutates state (`scale_deployment`, `restart_rollout`, `create_alert_rule`)
- [ ] `idempotentHint` set to `true` only when calling twice with the same arguments is provably safe
- [ ] Annotations cross-checked against the Security Checklist's "read-only by default" rule below — a tool with `readOnlyHint: false` and no `"dangerous": true` marker is a gap, not a convenience

**Annotations are hints, not enforcement** — a buggy or malicious tool implementation can lie about them. Don't treat them as your only safety control; combine with input validation, least-privilege IRSA, and the explicit `"dangerous"` marker from the Security Checklist.

### Error handling

Return `isError: true` in the response — don't raise exceptions that crash the server:

```python
@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await execute(name, arguments)
        return [TextContent(type="text", text=result)]
    except ValidationError as e:
        return [TextContent(type="text", text=f"Validation error: {e}")]
    except Exception as e:
        # Log via OTel, return error to client
        logger.exception("Tool execution failed")
        return [TextContent(type="text", text=f"Error: {e}")]
```

---

## Defining Resources

### URI patterns

```python
@mcp.resource("resource://runbooks/{alert_name}")
async def get_runbook(alert_name: str) -> str:
    """Fetch runbook for a specific alert."""
    path = RUNBOOK_DIR / f"{alert_name}.md"
    if not path.exists():
        return f"No runbook found for alert: {alert_name}"
    return path.read_text()


@mcp.resource("resource://tags/cost-centers")
async def get_cost_centers() -> str:
    """List all valid CostCenter values."""
    return json.dumps(COST_CENTERS, indent=2)
```

### Listing

Clients call `resources/list` to discover available resources. Return URI templates for parameterized resources.

---

## Defining Prompts

```python
@mcp.prompt()
async def generate_runbook(alert_name: str, severity: str = "critical") -> str:
    """Generate a runbook template for a new alert."""
    return f"""Write an operational runbook for alert '{alert_name}' (severity: {severity}).

Include:
- Summary (1 sentence)
- Impact assessment
- Diagnostic commands (kubectl, MetricsQL queries)
- Mitigation steps
- Escalation path

Follow <org> runbook template (see runbook-authoring skill)."""
```

Prompts are NOT executed — they're returned to the client as message templates. The client (agent) then uses them to structure its reasoning.

---

## Testing Locally

### Kiro CLI integration

Add to your agent JSON (`mcpServers` field):

```json
{
  "mcpServers": {
    "<org>-vm": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-v", "/path/to/server:/app",
        "-w", "/app",
        "python:3.11-slim",
        "python", "server.py"
      ]
    }
  }
}
```

### Manual JSON-RPC testing (stdio)

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | \
  docker run --rm -i -v $(pwd):/app -w /app python:3.11-slim python server.py
```

### MCP Inspector (official dev tool)

```bash
docker run --rm -v $(pwd):/app -w /app node:20-slim \
  npx @modelcontextprotocol/inspector python server.py
```

---

## Evaluating Server Quality

Passing `tools/list` and manually poking at a tool in MCP Inspector proves the server *runs*. It does not prove the server *helps*. The real measure of an MCP server's quality is whether an LLM with only your tools — no other context — can answer realistic questions correctly, with a reasonable number of tool calls. Not code coverage. Not how many endpoints you wrapped.

Don't build a second, ad hoc evaluation script for this. This catalog already has a general-purpose harness for exactly this shape of problem — `skill-eval-harness` (`skills/workflows/skill-eval-harness/SKILL.md`) — with a mandatory cost preflight, a paired baseline/candidate release gate, and a JSONL case format. Use that harness; what follows is how to write MCP-server-specific cases against it, not a replacement for it.

### Step 1 — Generate ~10 QA pairs via read-only exploration

1. Have a subagent explore your server's tools and resources using ONLY read-only, non-destructive calls — no writes, no state mutation, even for a call that would be idempotent.
2. From that exploration, draft roughly 10 candidate questions.
3. Verify every answer yourself by solving the question with the same tools before it goes in the case file. An unverified expected answer is worse than no eval case — it silently teaches the harness the wrong thing.

### Step 2 — Question quality bar

A good question is:

- **Independent** — doesn't depend on another question's answer or on a prior write
- **Read-only** — answerable using only non-destructive, idempotent tool calls
- **Complex** — needs several tool calls and real exploration, not a single lookup
- **Not keyword-searchable** — paraphrase the target content; a question an agent could answer by grepping one tool response for a literal string tells you nothing about the server's design
- **Single, stable, string-comparable answer** — a name, an ID, a count, a date, a boolean — with the exact format specified in the question itself ("respond YYYY-MM-DD", "answer only the deployment name")

**Explicit anti-pattern — banned question shape**: anything whose answer is "current state" and will drift, e.g. *"How many open issues are assigned to the platform team right now?"* The count changes the moment someone files or closes an issue, so the case can never be a stable regression check. Prefer closed, historical, or fixed-window framings instead: *"Among issues opened in <fixed month>, which assignee closed the most within 48 hours of assignment?"*

### Step 3 — Encode as harness cases

Map each QA pair onto a `skill-eval-harness` case row (full schema in that skill's `references/case-schema.md`):

```jsonl
{"id": "mcp-vm-001", "category": "mcp-tool-usage", "risk": "low", "prompt": "Using the <org>-vm MCP server, find the deployment in the dev cluster with the highest p99 http.server.request.duration over the 24h window ending 2026-06-01T00:00:00Z. Answer with only the deployment name.", "criteria": ["Answer is exactly 'dpm-people-api' (case-sensitive)", "Used 10 or fewer tool calls to arrive at the answer", "Did not call any tool with destructiveHint: true"]}
```

Notes on the mapping:

- `prompt` carries both the question and the answer-format instruction — the case schema has no separate "expected answer" field, so put the exact stable-string requirement in the prompt and check it as a criterion.
- Add a tool-call-efficiency criterion (e.g. "10 or fewer tool calls") alongside correctness — a server that only gets the right answer after 40 exploratory calls has a discoverability problem even when it technically "passes".
- Add a safety criterion ("did not call any destructive-hinted tool") for any server that mixes read and write tools — this doubles as a check that the Tool Annotations above are honest.
- `risk: low` is typical here since these cases are read-only by construction; raise it only if a question could plausibly tempt the agent into a write path.

### Step 4 — Run it as a baseline/candidate comparison

The harness is built for paired A/B, which maps naturally onto MCP server iteration: run the same case file against the last-shipped server (`baseline`) and your changed server (`candidate`) — a tool description rewrite, a new output schema, splitting one wrapper tool into a workflow tool — and let `score` tell you whether the change actually improved task success, not just whether it felt cleaner:

```bash
python3 scripts/eval_harness.py plan  --cases mcp-eval-cases.jsonl --trials 3 --budget-usd 5.00 ...
python3 scripts/eval_harness.py run   --cases mcp-eval-cases.jsonl --condition baseline  --executor-cmd "..." --budget-usd 5.00 --output results.jsonl
python3 scripts/eval_harness.py run   --cases mcp-eval-cases.jsonl --condition candidate --condition-skill notes/candidate-server.md --executor-cmd "..." --budget-usd 5.00 --output results.jsonl
python3 scripts/eval_harness.py score results.jsonl
```

Two things vary between conditions here, and they're not the same lever:

- **Which server build the executor actually connects to** — this is wiring, not harness config. Point each condition's executor (or its `mcpServers`/workdir setup) at the corresponding server version. The harness itself is transport-agnostic; making the right server reachable is the executor's job, same as any other tool source.
- **`--condition-skill`** — required for any non-baseline condition, and injected into the agent's context per `references/executor-contract.md` in `skill-eval-harness`. It doesn't have to be literal skill content: point it at a short markdown note identifying which server build/config this condition uses, so a custom executor (or a human debugging a transcript) can tell the two conditions apart.

If you don't yet have a prior version to compare against — first eval of a brand-new server — run only the `candidate` condition and treat the raw accuracy and tool-call numbers as your baseline for next time. The paired release gate matters most for iteration, not for a one-off first measurement.

---

## Production Deploy at <org>

### Dockerfile (multi-arch)

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir ".[prod]"
COPY src/ src/

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /app/src ./src
COPY server.py .

USER 65534
ENTRYPOINT ["python", "server.py"]
```

Build multi-arch (both amd64 and arm64, mandatory for Graviton scheduling):
```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t <harbor-registry>/<harbor-project>/mcp-vm-server:${SHA} --push .
```

Sign with cosign (mandatory for all production images — see `cosign-image-signing`):
```bash
cosign sign --key cosign.key --new-bundle-format=false ${IMAGE}@${DIGEST} -y
```

### Credentials and secrets

Any MCP server that talks to an authenticated upstream (GitHub, GitLab, VictoriaMetrics with auth, a customer API) needs a token or key at runtime. Never pass it as a literal `env.value` — that's readable in `kubectl describe pod`, in the Helm release manifest, in crash dumps, and in CI logs. Use the same External Secrets Operator pattern as every other <org> service: see `external-secrets-aws-sm` for the full `ExternalSecret`/`SecretStore` reference. The `externalSecrets` block in the Helm values below is that pattern applied to this server — it syncs into a real Kubernetes `Secret`, which you then mount as a file (`VM_AUTH_TOKEN_FILE=/etc/secrets/vm-auth-token`) where the server supports it, or consume via `envFrom.secretRef` as a fallback. Either keeps the value out of the pod spec itself. A hardcoded token in `values.yaml`, a plaintext env var in the Dockerfile, or a `.env` file baked into the image are all the same mistake with different packaging.

### Helm values (corporate `app` chart)

```yaml
# values-prd.yaml
replicaCount: 2
image:
  repository: <harbor-registry>/<harbor-project>/mcp-vm-server
  tag: "abc1234"

labels:
  Environment: "PRD"
  CostCenter: "<cost-center>"
  CostScope: "API"
  CostProject: "MCP-SERVERS"

env:
  - name: SERVICE_NAME
    value: mcp-vm-server
  - name: ENVIRONMENT
    value: PRD
  - name: OTEL_EXPORTER_OTLP_ENDPOINT
    value: http://otel-agent-collector.monitoring:4317
  - name: TRANSPORT
    value: http  # HTTP transport for shared server

serviceAccount:
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::<ACCOUNT_ID>:role/mcp-vm-server-role

externalSecrets:
  - name: mcp-vm-secrets
    secretStore: aws-secrets-manager
    data:
      - secretKey: VM_AUTH_TOKEN
        remoteRef:
          key: mcp-servers/vm-server
          property: auth_token
```

### Observability (mandatory, not optional polish)

Every server generated or hand-built for <org> ships with the corporate OTel Helper wired in from the first commit — not added later "if it turns out to matter". Follow `telemetry-standard` as the authoritative source for the lib API and environment behavior; the two things specific to MCP servers on top of that baseline:

```python
# server.py — production entrypoint
from otel_helper import setup_telemetry

def main():
    setup_telemetry()  # <org> OTel Helper — traces, metrics, logs
    # ... server startup
```

- **Wrap every `tools/call` handler in a span** named after the tool (`mcp.tool.query_metrics`), with the tool name, a truncated/redacted view of the arguments (never raw secrets — see Security Checklist), and success/failure as span attributes. This is what makes the eval-driven tool-call-efficiency criteria from "Evaluating Server Quality" above debuggable after the fact: a failing eval case plus a trace showing which tool call actually went sideways is worth far more than the final text response alone.
- **Log structurally through the OTel Helper's logger, not `print()`** — doubly true for stdio transport, where a stray `print()` corrupts the JSON-RPC stream on stdout (see Common Pitfalls below). Route all diagnostic output to the helper's logging integration, which already ships to stderr/OTLP correctly.

Per `telemetry-standard`: the lib handles `SERVICE_NAME`, `ENVIRONMENT`, endpoint resolution, and all instrumentations — don't hand-roll a parallel OTel SDK setup.

---

## Combining with Autonomous Agents

Pattern: autonomous agent (cron/webhook-triggered) uses MCP server as its tool source.

```
CronWorkflow → Agent Container → MCP Client → MCP Server (tools)
                                                    ↓
                                              VictoriaMetrics / ArgoCD / AWS
```

The agent doesn't hardcode API calls — it discovers capabilities via MCP. This decouples agent logic from backend specifics.

> See `agent-platform-design` skill for the 5 execution patterns (cron, webhook, Slack, multi-agent, CI-triggered).

---

## Security Checklist

- [ ] **Input validation**: validate ALL tool arguments against schema before execution
- [ ] **No secret leakage**: never return AWS ARNs, connection strings, or tokens in tool responses
- [ ] **Least privilege IRSA**: scope IAM role to exactly what tools need (not `*`)
- [ ] **Rate limiting** (HTTP transport): prevent abuse via token bucket or API gateway
- [ ] **Prompt injection mitigation**: sanitize user-provided strings before embedding in prompts
- [ ] **Read-only by default**: tools that modify state require explicit `"dangerous": true` in schema
- [ ] **Audit logging**: log every `tools/call` invocation with arguments (via OTel spans)
- [ ] **TLS** (HTTP transport): mandatory in PRD/HML/BTC (Istio Ambient handles pod-to-pod)

---

## Common Pitfalls

| Pitfall | Impact | Fix |
|---------|--------|-----|
| Schema mismatch (server changes, client cached) | Client sends wrong params → errors | Version your server, use capability negotiation |
| Sync handler in async server | Blocks event loop, timeouts | Always `async def` for tool handlers |
| Large response (>100KB) | Client truncates silently | Paginate or summarize; return URIs to full data |
| Missing `required` in inputSchema | Client omits params → runtime error | Always declare `required` array |
| OAuth state not persisted (HTTP) | Auth fails on server restart | Store OAuth state in Redis/DynamoDB |
| stdio server writes to stdout accidentally | Corrupts JSON-RPC stream | Use stderr for logging, never `print()` |
| Trusting a cached SDK method name as permanent (e.g. an old tutorial's `server.tool()`) | Deprecated call works today, breaks silently on next major bump | WebFetch the live SDK README before implementing — see "Verify Against Live Docs" above |

---

## Anti-patterns

- ❌ Exposing raw database queries as tools (SQL injection risk)
- ❌ Tools that return secrets/credentials in plaintext
- ❌ Single monolithic server heading past ~15-20 tools without a deliberate reason (split by domain, or collapse thin wrappers into workflow tools — see Scope Discipline above)
- ❌ Hardcoded endpoints (use env vars: `VM_ENDPOINT`, `LOKI_ENDPOINT`)
- ❌ No input validation ("the client will send correct data")
- ❌ `print()` in stdio servers (corrupts transport)
- ❌ Blocking I/O in async handlers (`requests.get` instead of `httpx.AsyncClient`)
- ❌ Skipping OTel instrumentation ("it's just a tool server")
- ❌ Running as root in container (use `USER 65534`)
- ❌ Single-arch image (breaks Graviton scheduling)
- ❌ Missing mandatory tags on K8s deployment (breaks FinOps + OTel enrichment)
- ❌ Vendor lock-in (building for one specific client instead of MCP standard)
- ❌ Shipping a tool without `readOnlyHint`/`destructiveHint`/`idempotentHint`/`openWorldHint` set (see Tool Annotations checklist above)
- ❌ Declaring a server "done" after it passes MCP Inspector poking, with no QA-pair evaluation proving an LLM can actually use it to answer real questions (see Evaluating Server Quality)
- ❌ API keys/tokens as literal `env.value` in Helm values or manifests instead of an `ExternalSecret` (see Credentials and Secrets)

---

## References

| Resource | URL |
|----------|-----|
| MCP Specification | https://spec.modelcontextprotocol.io |
| MCP Documentation | https://modelcontextprotocol.io/docs |
| Python SDK | https://github.com/modelcontextprotocol/python-sdk |
| TypeScript SDK | https://github.com/modelcontextprotocol/typescript-sdk |
| MCP Inspector | https://github.com/modelcontextprotocol/inspector |
| JSON-RPC 2.0 | https://www.jsonrpc.org/specification |

### Related <org> skills

- `agent-platform-design` — autonomous agent execution patterns
- `python-fastapi-patterns` — if wrapping MCP HTTP transport in FastAPI
- `python-grpc-aio` — async patterns applicable to MCP handlers
- `telemetry-standard` — OTel instrumentation for MCP servers
- `helm-chart-app` — deploying MCP server to EKS
- `cosign-image-signing` — mandatory image signing
- `dependency-track-integration` — SBOM for MCP server dependencies
- `skill-eval-harness` — the eval harness used in "Evaluating Server Quality" above
- `external-secrets-aws-sm` — the ExternalSecret pattern used in "Credentials and Secrets" above
