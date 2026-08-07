---
name: ai-agent-security
description: "Use when designing or auditing the security posture of an AI agent — tool permission scoping, blast-radius tiering, exfiltration prevention, credential isolation, and human-in-the-loop gates for high-risk actions."
---
# AI Agent Security

## When to use

- Designing a new agent's permission surface (which tools, what scope)
- Auditing an existing agent for over-permissioned tools
- Implementing human-in-the-loop (HITL) gates for destructive actions
- Preventing credential leakage through agent tool calls
- Scoping subagent/delegated-agent permissions (supervisor pattern)
- Reviewing whether an agent can be tricked into exfiltrating data

## When NOT to use

- Defending against prompt injection in input content (use `prompt-injection-defense`)
- Securing MCP transport/auth specifically (use `mcp-server-security`)
- Coding agent file/shell permissions specifically (use `ai-coding-agent-guardrails`)
- Red-teaming an agent adversarially (use `ai-red-teaming`)

## Steps

1. **Enumerate every tool and classify blast radius**:
   ```yaml
   # agent-security-audit.yaml
   agent: ops-assistant
   tools:
     - name: kubectl_get
       blast_radius: none
       justification: "Read-only, no state change"
     - name: kubectl_apply
       blast_radius: high
       justification: "Mutates cluster state, potentially irreversible"
       gate: human_approval
     - name: file_read
       blast_radius: low
       justification: "No mutation, but may expose secrets"
       mitigations: ["secret-path-blocklist"]
     - name: shell_exec
       blast_radius: critical
       justification: "Unbounded — union of all shell commands"
       gate: command_allowlist + human_approval
   ```

2. **Implement least-privilege tool grants**:
   ```json
   // agent-config.json — only grant what's needed
   {
     "tools": {
       "allowed": ["kubectl_get", "kubectl_describe", "get_logs", "query_prometheus"],
       "gated": {
         "kubectl_apply": {"requires": "human_approval", "timeout_sec": 300},
         "shell_exec": {"requires": "allowlist_match", "allowlist": ["grep", "cat", "jq"]}
       },
       "denied": ["kubectl_delete", "aws_iam_*", "git_push_force"]
     }
   }
   ```

3. **Isolate credentials from agent context**:
   ```python
   # NEVER pass credentials through agent context
   # ❌ WRONG
   agent.run("Deploy using AWS_SECRET_ACCESS_KEY=AKIA...")

   # ✅ RIGHT — tool has IRSA/ambient credentials, agent never sees them
   @tool(name="deploy_service")
   def deploy(service_name: str, version: str):
       # Function has IRSA via pod service account
       # Agent only provides service_name + version
       boto3.client("ecs").update_service(...)
   ```

4. **Prevent data exfiltration** — block outbound paths:
   ```python
   # Pre-tool-use hook that blocks exfiltration
   EXFIL_PATTERNS = [
       r"curl\s+.*\s+https?://(?!internal\.)",  # External HTTP
       r"wget\s+",
       r"nc\s+-",  # netcat
       r"base64.*\|\s*curl",  # Encode + send
   ]

   def pre_tool_hook(tool_name: str, args: dict) -> bool:
       if tool_name == "shell_exec":
           cmd = args.get("command", "")
           for pattern in EXFIL_PATTERNS:
               if re.search(pattern, cmd):
                   log.warning(f"Blocked potential exfil: {cmd[:100]}")
                   return False  # Block execution
       return True
   ```

5. **Implement HITL gates** for high-blast-radius actions:
   ```python
   async def execute_with_gate(tool_name: str, args: dict, blast_radius: str):
       if blast_radius in ("high", "critical"):
           approval = await request_human_approval(
               action=f"{tool_name}({json.dumps(args)[:200]})",
               blast_radius=blast_radius,
               timeout=timedelta(minutes=5)
           )
           if not approval.granted:
               return {"error": "Action denied by operator", "reason": approval.reason}

       return await execute_tool(tool_name, args)
   ```

6. **Scope subagent permissions** (delegation):
   ```yaml
   # Supervisor grants SUBSET of its own permissions to subagents
   supervisor:
     tools: [kubectl_get, kubectl_apply, shell_exec, file_read, file_write]
   subagents:
     researcher:
       tools: [kubectl_get, file_read]  # Read-only subset
       max_steps: 5
     implementer:
       tools: [file_read, file_write]   # No shell, no kubectl
       allowed_paths: ["src/", "tests/"]
   ```

7. **Audit and alert** on agent actions:
   ```yaml
   # VMRule for suspicious agent behavior
   groups:
     - name: agent-security
       rules:
         - alert: AgentDeniedActionSpike
           expr: rate(agent_tool_denied_total[5m]) > 3
           labels: { severity: warning }
         - alert: AgentAccessedSecretPath
           expr: agent_file_read_total{path=~"/etc/secrets/.*|.*\\.env"} > 0
           labels: { severity: critical }
   ```

## Decision tree

```
IF designing new agent:
  → Enumerate ALL tools it could call
  → For each tool:
    IF blast_radius == none/low:  → Allow by default
    IF blast_radius == medium:    → Allow with audit logging
    IF blast_radius == high:      → Gate behind human approval
    IF blast_radius == critical:  → Deny unless exceptional justification
  → Implement credential isolation (step 3)
  → Add exfiltration prevention (step 4)
IF auditing existing agent:
  → List actual tool usage from traces (agent-observability)
  → Identify over-permissions (granted but unused = remove)
  → Check: can agent access secrets directly? → Fix isolation
  → Check: can agent call external URLs? → Add allowlist
IF agent delegates to subagents:
  → Each subagent gets SUBSET of parent permissions
  → Never inherit full tool set automatically
```

## Anti-patterns

- ❌ Granting `shell_exec` without a command allowlist (== granting everything)
- ❌ Passing credentials through the agent's context window
- ❌ Same permission set for all subagents regardless of task
- ❌ No audit trail of what the agent actually invoked
- ❌ HITL gate that times out silently (should fail-closed, not open)
- ❌ Blocklist approach ("deny these 5 commands") instead of allowlist
- ❌ Trusting tool return values without output-size bounds
- ❌ Agent with network access + file read = exfiltration path

## Related skills

- `ai-coding-agent-guardrails` — this skill applied to coding agents specifically
- `mcp-server-security` — transport + authz for MCP tool servers
- `prompt-injection-defense` — preventing injection from triggering tool abuse
- `ai-red-teaming` — testing whether these controls actually hold
