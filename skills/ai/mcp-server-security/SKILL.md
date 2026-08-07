---
name: mcp-server-security
description: "Use when securing MCP (Model Context Protocol) servers — transport encryption, tool-level authorization, input validation on tool arguments, output sanitization to prevent injection back into calling agent, rate limiting, and audit logging of all tool invocations."
---
# MCP Server Security

## When to use

- Deploying an MCP server that exposes tools to AI agents
- Implementing authorization (which agents/users can call which tools)
- Preventing tool-output injection (malicious data in tool results re-entering agent context)
- Adding rate limiting and abuse prevention to MCP tool endpoints
- Auditing tool invocations for security forensics
- Reviewing an existing MCP server's security posture

## When NOT to use

- General MCP server development (use `mcp-server-development`)
- Agent-level permission scoping (use `ai-agent-security`)
- Prompt injection from non-tool sources (use `prompt-injection-defense`)
- Infrastructure hardening (use `ai-security-hardening`)

## Steps

1. **Transport security** — encrypt all MCP traffic:
   ```python
   # For HTTP/SSE transport — enforce TLS
   # mcp_server.py
   import ssl
   from mcp.server import Server
   from mcp.server.sse import SseServerTransport

   app = Server("secure-tools")

   # In production: terminate TLS at Istio/ingress level
   # For direct exposure (dev/testing):
   ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
   ssl_context.load_cert_chain("/etc/tls/server.crt", "/etc/tls/server.key")

   # For stdio transport (local): inherently secure (no network)
   # But: validate that stdin/stdout isn't being redirected to a network socket
   ```

2. **Tool-level authorization** — not all callers get all tools:
   ```python
   from functools import wraps
   from mcp.server import Server
   from mcp.types import TextContent

   app = Server("secure-tools")

   # Authorization matrix
   TOOL_PERMISSIONS = {
       "query_metrics": ["read-only", "analyst", "admin"],
       "kubectl_get": ["read-only", "operator", "admin"],
       "kubectl_apply": ["operator", "admin"],
       "delete_resource": ["admin"],
   }

   def authorized(tool_name: str):
       """Decorator that checks caller's role against tool permissions."""
       def decorator(func):
           @wraps(func)
           async def wrapper(*args, **kwargs):
               # Extract caller identity from request context
               caller_role = get_caller_role()  # From auth token/header
               allowed_roles = TOOL_PERMISSIONS.get(tool_name, [])

               if caller_role not in allowed_roles:
                   return [TextContent(
                       type="text",
                       text=f"DENIED: Role '{caller_role}' cannot invoke '{tool_name}'"
                   )]

               return await func(*args, **kwargs)
           return wrapper
       return decorator

   @app.tool()
   @authorized("kubectl_apply")
   async def kubectl_apply(manifest: str) -> list[TextContent]:
       # Only reachable if caller has operator/admin role
       ...
   ```

3. **Input validation** — sanitize tool arguments:
   ```python
   from pydantic import BaseModel, validator
   import re

   class KubectlGetArgs(BaseModel):
       resource_type: str
       namespace: str
       name: str = ""

       @validator("resource_type")
       def valid_resource(cls, v):
           ALLOWED = ["pods", "services", "deployments", "configmaps", "events"]
           if v not in ALLOWED:
               raise ValueError(f"Resource '{v}' not in allowlist: {ALLOWED}")
           return v

       @validator("namespace")
       def valid_namespace(cls, v):
           if not re.match(r'^[a-z0-9-]{1,63}$', v):
               raise ValueError(f"Invalid namespace: {v}")
           # Block sensitive namespaces
           BLOCKED = ["kube-system", "istio-system", "cert-manager"]
           if v in BLOCKED:
               raise ValueError(f"Access to namespace '{v}' is restricted")
           return v

       @validator("name")
       def no_injection(cls, v):
           # Block shell metacharacters in resource names
           if re.search(r'[;&|`$(){}]', v):
               raise ValueError("Invalid characters in resource name")
           return v

   @app.tool()
   async def kubectl_get(resource_type: str, namespace: str, name: str = ""):
       args = KubectlGetArgs(resource_type=resource_type, namespace=namespace, name=name)
       # Safe to execute — validated
       ...
   ```

4. **Output sanitization** — prevent injection via tool results:
   ```python
   def sanitize_tool_output(output: str, max_length: int = 10_000) -> str:
       """Prevent tool output from carrying injected instructions back to agent."""
       # Truncate to prevent context stuffing
       if len(output) > max_length:
           output = output[:max_length] + f"\n[TRUNCATED: {len(output)} chars total]"

       # Strip common injection patterns from data
       INJECTION_MARKERS = [
           r'(?i)\b(ignore|forget|disregard)\s+(all\s+)?(previous|above|prior)\s+(instructions?|rules?|context)',
           r'(?i)\bsystem\s*:\s*',
           r'(?i)\byou\s+are\s+now\b',
           r'(?i)\bnew\s+instruction\b',
       ]

       for pattern in INJECTION_MARKERS:
           if re.search(pattern, output):
               # Don't remove — flag it so the agent knows
               output = f"[WARNING: Output may contain injection attempt]\n{output}"
               break

       return output

   # Apply to ALL tool responses before returning to agent
   @app.tool()
   async def query_database(sql: str) -> list[TextContent]:
       result = await db.execute(sql)
       safe_output = sanitize_tool_output(str(result))
       return [TextContent(type="text", text=safe_output)]
   ```

5. **Rate limiting per caller**:
   ```python
   from collections import defaultdict
   from time import time

   class ToolRateLimiter:
       def __init__(self, max_calls_per_minute: int = 30):
           self.calls: dict[str, list[float]] = defaultdict(list)
           self.limit = max_calls_per_minute

       def check(self, caller_id: str, tool_name: str) -> bool:
           key = f"{caller_id}:{tool_name}"
           now = time()
           # Clean old entries
           self.calls[key] = [t for t in self.calls[key] if now - t < 60]
           if len(self.calls[key]) >= self.limit:
               return False
           self.calls[key].append(now)
           return True

   rate_limiter = ToolRateLimiter(max_calls_per_minute=30)

   # In tool dispatch:
   if not rate_limiter.check(caller_id, tool_name):
       return error_response("Rate limit exceeded")
   ```

6. **Audit logging** — every tool invocation recorded:
   ```python
   import structlog

   audit = structlog.get_logger("mcp.audit")

   async def audited_dispatch(tool_name: str, args: dict, caller: str):
       request_id = str(uuid4())
       audit.info("tool_invoked",
           request_id=request_id, tool=tool_name,
           caller=caller, args_keys=list(args.keys()),
           args_size=len(json.dumps(args)))

       try:
           result = await execute_tool(tool_name, args)
           audit.info("tool_completed",
               request_id=request_id, tool=tool_name,
               success=True, output_size=len(str(result)))
           return result
       except Exception as e:
           audit.error("tool_failed",
               request_id=request_id, tool=tool_name,
               error=str(e)[:200])
           raise
   ```

## Decision tree

```
IF MCP server exposed over network (HTTP/SSE):
  → TLS mandatory (step 1)
  → Authentication required (token/mTLS)
  → Rate limiting (step 5)
IF MCP server has destructive tools (write/delete/exec):
  → Authorization per tool (step 2)
  → Input validation (step 3)
  → Audit logging (step 6)
IF tool reads external/untrusted data (DB, API, files):
  → Output sanitization (step 4)
  → Truncation to prevent context stuffing
IF MCP server runs in multi-tenant environment:
  → Caller isolation (each caller sees only their data)
  → Per-caller rate limits
IF debugging an injection that came through a tool result:
  → Check output sanitization (step 4)
  → Add injection markers to detection
  → Consider: should the tool return raw data at all?
```

## Anti-patterns

- ❌ All tools available to all callers (no authorization matrix)
- ❌ Tool arguments passed directly to shell/SQL without validation
- ❌ Raw tool output re-enters agent context without sanitization
- ❌ No rate limiting (one agent can DoS the MCP server)
- ❌ No audit trail (can't investigate after an incident)
- ❌ Stdio transport assumed "secure" when redirected over network
- ❌ Secret values in tool responses (agent logs them, leaks them)

## Related skills

- `mcp-server-development` — building MCP servers (protocol, SDK)
- `ai-agent-security` — agent-side tool permission scoping
- `prompt-injection-defense` — injection arriving through tool outputs
- `ai-red-teaming` — testing MCP security adversarially
