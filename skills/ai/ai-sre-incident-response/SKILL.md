---
name: ai-sre-incident-response
description: "Use when an AI/LLM system is involved in a production incident — agent runaway loops, cost spikes, model degradation, hallucination-caused bad actions, or cascading failures from AI tool calls affecting infrastructure."
---
# AI SRE Incident Response

## When to use

- AI agent is stuck in a loop consuming tokens/cost
- LLM API outage cascading to dependent services
- Agent made a bad decision that mutated production state
- Cost spike alert from AI systems (>10x normal spend rate)
- Model degradation causing increased error rates downstream
- Agent hallucinated and executed destructive action

## When NOT to use

- General K8s incident response without AI involvement (use `incident-response-runbook`)
- Designing agent permissions proactively (use `ai-agent-security`)
- Optimizing normal cost (use `llm-cost-optimization`)
- Evaluating model quality non-urgently (use `agent-evals`)

## Steps

1. **Immediate triage** — classify the AI incident type:
   ```
   SYMPTOM → TYPE → IMMEDIATE ACTION
   ─────────────────────────────────────────
   Token/cost spike      → Runaway loop      → Kill agent process/pod
   5xx from LLM API      → Provider outage   → Activate fallback/circuit breaker
   Bad state mutation    → Hallucination      → Rollback action + freeze agent
   Slow responses       → Model degradation  → Route to backup model
   Data leak suspected  → Exfiltration       → Revoke agent credentials NOW
   ```

2. **Kill switch — stop the bleeding**:
   ```bash
   # Option A: Kill agent pod
   kubectl scale deployment/ai-agent --replicas=0 -n ai-services

   # Option B: Disable via feature flag (if instrumented)
   curl -X POST http://feature-flags.internal/api/flags/ai-agent-enabled \
     -d '{"enabled": false}'

   # Option C: Rate limit to zero (preserve pod for forensics)
   kubectl patch configmap ai-agent-config -n ai-services \
     --type merge -p '{"data":{"MAX_REQUESTS_PER_MINUTE":"0"}}'

   # Option D: Revoke API key (nuclear — affects all using that key)
   aws secretsmanager put-secret-value \
     --secret-id ai-platform/anthropic \
     --secret-string '{"api_key":"REVOKED_INCIDENT_$(date +%s)"}'
   ```

3. **Assess blast radius** of agent actions during incident:
   ```bash
   # Check what the agent DID (from audit logs)
   # Loki query for agent actions in the last hour
   {namespace="ai-services", app="ai-agent"} |= "tool_call"
     | json | tool_name != ""
     | line_format "{{.timestamp}} {{.tool_name}} {{.tool_input}}"

   # Check for state mutations
   kubectl get events -n production --sort-by='.lastTimestamp' \
     | grep -E "Applied|Deleted|Scaled|Patched"

   # Check git for unauthorized commits
   git log --since="1 hour ago" --author="ai-bot" --all
   ```

4. **Rollback bad actions** — undo what the agent did:
   ```bash
   # If agent applied a bad manifest:
   kubectl rollout undo deployment/<affected> -n production

   # If agent committed bad code:
   git revert <commit-hash> --no-edit && git push

   # If agent sent bad data to external system:
   # → Manual intervention required, document in incident timeline

   # If agent created resources:
   kubectl get all -n production -l "created-by=ai-agent" \
     --sort-by='.metadata.creationTimestamp'
   # Review and delete if inappropriate
   ```

5. **Root cause analysis** specific to AI incidents:
   ```yaml
   # ai-incident-rca-template.yaml
   incident_id: AI-INC-001
   timeline:
     - time: "14:00"
       event: "Agent received ambiguous user request"
     - time: "14:01"
       event: "Agent misinterpreted 'clean up staging' as 'delete staging namespace'"
     - time: "14:01"
       event: "kubectl_delete tool called on ns/staging"
     - time: "14:02"
       event: "Alert fired: namespace deleted"
     - time: "14:03"
       event: "Human killed agent, namespace restored from ArgoCD"

   root_cause: |
     Agent had kubectl_delete in its tool set without HITL gate.
     Ambiguous instruction + no confirmation step = destructive action.

   corrective_actions:
     - action: "Remove kubectl_delete from agent tools entirely"
       owner: platform-team
       deadline: immediate
     - action: "Add HITL gate for ALL mutating kubectl operations"
       owner: platform-team
       deadline: 1 day
     - action: "Add this case to red-team probe suite"
       owner: security
       deadline: 1 week
   ```

6. **Post-incident hardening** — prevent recurrence:
   ```python
   # Add circuit breaker for cost
   class AgentCircuitBreaker:
       def __init__(self, max_cost_per_minute: float = 1.0, max_steps: int = 20):
           self.cost_window: list[tuple[float, float]] = []  # (timestamp, cost)
           self.step_count = 0
           self.max_cost_per_minute = max_cost_per_minute
           self.max_steps = max_steps

       def check(self, cost: float) -> bool:
           now = time.time()
           self.cost_window.append((now, cost))
           self.cost_window = [(t, c) for t, c in self.cost_window if now - t < 60]
           self.step_count += 1

           total_cost = sum(c for _, c in self.cost_window)
           if total_cost > self.max_cost_per_minute:
               raise AgentKillSwitch(f"Cost exceeded: ${total_cost:.2f}/min")
           if self.step_count > self.max_steps:
               raise AgentKillSwitch(f"Max steps exceeded: {self.step_count}")
           return True
   ```

## Decision tree

```
IF cost spike (>10x normal rate):
  → Is agent in a loop? (check step count in traces)
    YES → Kill pod immediately, investigate after
    NO  → Might be legitimate burst; check if user-triggered
  → After stopping: calculate total extra spend, report to FinOps

IF LLM API outage (5xx, timeout):
  → Is circuit breaker active?
    YES → Verify fallback model is serving
    NO  → Activate circuit breaker manually, route to fallback
  → Is there retry storm? (agents retrying against dead API)
    YES → Kill retry loops, implement exponential backoff

IF agent mutated production state incorrectly:
  → Freeze agent (scale to 0)
  → Identify ALL actions taken (audit log)
  → Rollback each mutation
  → RCA: WHY did agent take wrong action?
    → Prompt ambiguity? → Improve prompt + add confirmation
    → Tool too powerful? → Remove or gate the tool
    → Injection attack? → Engage security (prompt-injection-defense)

IF data exfiltration suspected:
  → Revoke ALL agent credentials immediately
  → Check: what data did agent access? (file_read logs)
  → Check: what external calls did agent make? (network logs)
  → If confirmed: security incident, escalate per IR runbook
```

## Anti-patterns

- ❌ No kill switch (agent has no way to be stopped quickly)
- ❌ No cost circuit breaker (runaway agent discovered via monthly bill)
- ❌ Treating AI incidents like normal software bugs (different failure modes)
- ❌ No audit trail of agent actions (can't assess blast radius)
- ❌ Restarting agent without fixing root cause ("it'll probably be fine now")
- ❌ No maximum step limit (infinite loops possible)
- ❌ Same permissions after incident (close the door that was exploited)

## Related skills

- `ai-agent-security` — preventing incidents via proper scoping
- `agent-observability` — signals that trigger incident detection
- `ai-red-teaming` — proactive discovery before incidents happen
- `incident-response-runbook` — general incident response framework
- `llm-cost-optimization` — cost guardrails that prevent spikes
