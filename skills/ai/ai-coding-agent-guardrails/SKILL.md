---
name: ai-coding-agent-guardrails
description: "Use when scoping file, shell, and git permissions for coding agents (Claude Code, Cursor, Copilot, Codex) — deciding which actions auto-apply vs require human review, preventing secret leakage from repo reads, and configuring subagent permission inheritance."
---
# AI Coding Agent Guardrails

## When to use

- Configuring a new coding agent for a repo or team for the first time
- Deciding which actions auto-apply vs wait for human diff review
- Agent has read access to repos with `.env`, keys, or inline secrets
- Wiring supervisor/subagent workflow where subagent shouldn't inherit full perms
- Reviewing agent permission config before running unattended or in CI

## When NOT to use

- General agent threat model (use `ai-agent-security`)
- MCP transport/authorization (use `mcp-server-security`)
- Prompt injection from file content (use `prompt-injection-defense`)
- Red-teaming the agent adversarially (use `ai-red-teaming`)

## Steps

1. **Classify the coding agent's tool surface by blast radius**:

   | Tool | Blast radius | Gate |
   |------|-------------|------|
   | File read | None (but secrets risk) | Secret-path blocklist |
   | File write/edit | Low-Medium | Auto for src/, gated for config/ |
   | Shell (read-only: grep, cat, ls) | None | Allow |
   | Shell (build: docker, pytest) | Low | Allow with audit |
   | Shell (destructive: rm -rf, dd) | Critical | Block |
   | Git (status, diff, log) | None | Allow |
   | Git (commit, push) | Medium | Human approval |
   | Git (force-push, reset --hard) | Irreversible | Hard block |

2. **Configure secret-path blocklist** (prevent reading credentials):
   ```json
   // .kiro/settings/agent-guardrails.json
   {
     "file_read": {
       "blocked_patterns": [
         "**/.env",
         "**/.env.*",
         "**/secrets/**",
         "**/*credentials*",
         "**/*.pem",
         "**/*.key",
         "**/id_rsa*",
         "**/.aws/credentials"
       ],
       "blocked_content_patterns": [
         "AKIA[0-9A-Z]{16}",
         "-----BEGIN (RSA |EC )?PRIVATE KEY-----"
       ]
     }
   }
   ```

3. **Configure shell command policy**:
   ```json
   {
     "shell_exec": {
       "allowlist": [
         "grep", "cat", "head", "tail", "wc", "find", "ls",
         "docker run", "docker build", "docker compose",
         "pytest", "go test", "dotnet test",
         "git status", "git diff", "git log", "git branch"
       ],
       "blocklist": [
         "rm -rf", "dd ", "mkfs", "chmod 777",
         "curl .*| ?sh", "wget .*| ?bash",
         "git push --force", "git reset --hard",
         "git clean -f", "git branch -D"
       ],
       "require_approval": [
         "git commit", "git push",
         "kubectl apply", "kubectl delete",
         "helm install", "helm upgrade"
       ]
     }
   }
   ```

4. **Implement PreToolUse hook** (Claude Code / Kiro style):
   ```json
   // .claude/settings.json or .kiro/agents/coding.json hooks
   {
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "shell_exec",
           "script": "scripts/guardrails-check.sh",
           "action": "block_on_failure"
         }
       ]
     }
   }
   ```

   ```bash
   #!/bin/bash
   # scripts/guardrails-check.sh
   COMMAND="$1"
   BLOCKLIST=("rm -rf" "git push --force" "git reset --hard" "dd " "chmod 777")
   for pattern in "${BLOCKLIST[@]}"; do
     if echo "$COMMAND" | grep -qE "$pattern"; then
       echo "BLOCKED: $pattern matched in: $COMMAND" >&2
       exit 1
     fi
   done
   exit 0
   ```

5. **Scope subagent permissions** (supervisor delegates less):
   ```json
   {
     "subagent_defaults": {
       "researcher": {
         "tools": ["file_read", "grep", "glob"],
         "denied": ["file_write", "shell_exec", "git_*"]
       },
       "implementer": {
         "tools": ["file_read", "file_write", "shell_exec"],
         "file_write_paths": ["src/**", "tests/**"],
         "shell_allowlist": ["pytest", "docker run"]
       },
       "reviewer": {
         "tools": ["file_read", "git_diff"],
         "denied": ["file_write", "shell_exec"]
       }
     }
   }
   ```

6. **CI mode restrictions** (unattended runs are stricter):
   ```json
   {
     "ci_mode": {
       "human_approval": "disabled",
       "shell_exec": "allowlist_only",
       "file_write_paths": ["src/**", "tests/**", "docs/**"],
       "git_operations": "none",
       "max_steps": 20,
       "timeout_minutes": 15
     }
   }
   ```

## Decision tree

```
IF new coding agent setup:
  → Apply default blocklist (step 3)
  → Add secret-path blocklist (step 2)
  → Decide: interactive (human available) or CI (unattended)?
    IF interactive:
      → Gate git commit/push behind approval
      → Allow file write freely (human reviews diff)
    IF CI/unattended:
      → Restrict file_write to specific paths
      → No git operations
      → Hard timeout + max steps

IF agent reads a secret accidentally:
  → Rotate the exposed secret immediately
  → Add the path to blocklist
  → Audit: did the agent send the value anywhere? (check spans)

IF delegating to subagent:
  → Never inherit parent's full tool set
  → Assign minimum tools for the subtask
  → Always add max_steps limit
```

## Anti-patterns

- ❌ Granting `shell_exec` with no allowlist/blocklist ("it needs to run tests" → allowlist test commands specifically)
- ❌ Secret files readable by default (agent reads `.env` → secret in context → exfiltrable)
- ❌ No distinction between interactive and CI mode (CI = no human backstop)
- ❌ Subagent inherits all parent tools by default
- ❌ Blocklist-only approach without allowlist (new dangerous commands not covered)
- ❌ Agent allowed to `git push` without diffing first
- ❌ No timeout or step limit (runaway agent burns tokens + makes mess)

## Related skills

- `ai-agent-security` — general agent security framework (this is the coding-specific instance)
- `mcp-server-security` — if coding agent calls MCP tools (linter-as-service, deploy tool)
- `prompt-injection-defense` — file content carrying injected instructions
- `ai-red-teaming` — testing these guardrails adversarially
