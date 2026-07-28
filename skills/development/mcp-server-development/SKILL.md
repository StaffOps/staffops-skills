---
name: mcp-server-development
description: "Build MCP servers with tools, resources and prompts."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [mcp, server, development]
    category: development
    related_skills: [metrics-server-metrics]
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

server.tool(
  "query_metrics",
  "Query VictoriaMetrics with MetricsQL",
  { query: z.string(), step: z.string().default("1m") },
  async ({ query, step }) => {
    const result = await doVmQuery(query, step);
    return { content: [{ type: "text", text: result }] };
  }
);

const transport = new StdioServerTransport();
await server.connect(transport);
```

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

Build multi-arch (per `multi-arch-builds` steering):
```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t <harbor-registry>/<harbor-project>/mcp-vm-server:${SHA} --push .
```

Sign with cosign (per `cosign-signing-mandatory` steering):
```bash
cosign sign --key cosign.key --new-bundle-format=false ${IMAGE}@${DIGEST} -y
```

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

### OTel instrumentation

```python
# server.py — production entrypoint
from otel_helper import setup_telemetry

def main():
    setup_telemetry()  # <org> OTel Helper — traces, metrics, logs
    # ... server startup
```

Per `<org>-telemetry-standard`: the lib handles `SERVICE_NAME`, `ENVIRONMENT`, endpoint resolution, all instrumentations.

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

---

## Anti-patterns

- ❌ Exposing raw database queries as tools (SQL injection risk)
- ❌ Tools that return secrets/credentials in plaintext
- ❌ Single monolithic server with 50+ tools (split by domain)
- ❌ Hardcoded endpoints (use env vars: `VM_ENDPOINT`, `LOKI_ENDPOINT`)
- ❌ No input validation ("the client will send correct data")
- ❌ `print()` in stdio servers (corrupts transport)
- ❌ Blocking I/O in async handlers (`requests.get` instead of `httpx.AsyncClient`)
- ❌ Skipping OTel instrumentation ("it's just a tool server")
- ❌ Running as root in container (use `USER 65534`)
- ❌ Single-arch image (breaks Graviton scheduling)
- ❌ Missing mandatory tags on K8s deployment (breaks FinOps + OTel enrichment)
- ❌ Vendor lock-in (building for one specific client instead of MCP standard)

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
- `<org>-telemetry-standard` — OTel instrumentation for MCP servers
- `helm-chart-app` — deploying MCP server to EKS
- `cosign-image-signing` — mandatory image signing
- `dependency-track-integration` — SBOM for MCP server dependencies
