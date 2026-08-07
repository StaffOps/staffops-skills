---
name: llm-cost-optimization
description: "Use when reducing LLM API spend — model tier selection per task, token budget management, prompt compression, batch API usage for async workloads, and the self-hosting crossover decision for high-volume inference."
---
# LLM Cost Optimization

## When to use

- LLM API cost is a visible line item without a reduction plan
- Team defaults to the most capable model for every call regardless of task complexity
- Evaluating self-hosted open-weight models vs API for a workload
- Async workload could use batch APIs (50% cheaper, higher latency)
- Need to attribute LLM cost per team/feature/agent

## When NOT to use

- Implementing caching specifically (use `llm-caching`)
- Adding cost metrics to traces (use `agent-observability`)
- Running quality evals to validate cheaper models (use `agent-evals`)
- Security concerns about data leaving the org (use `ai-security-hardening`)

## Steps

1. **Model tiering** — match model capability to task complexity:
   ```yaml
   # model-routing.yaml
   tiers:
     cheap:  # $0.25-0.80/MTok input
       models: [claude-3-5-haiku-20241022, gpt-4o-mini]
       use_for: [classification, extraction, summarization, routing, yes/no]
       max_tokens: 1000
     standard:  # $3/MTok input
       models: [claude-sonnet-4-20250514, gpt-4o]
       use_for: [generation, analysis, multi-step reasoning, code review]
       max_tokens: 4096
     premium:  # $15/MTok input
       models: [claude-opus-4-20250514, o1-pro]
       use_for: [complex architecture decisions, novel research, critical safety]
       max_tokens: 8192
       require_justification: true  # Log why premium was needed
   ```

   ```python
   # Router implementation
   MODEL_TIER_MAP = {
       "classify": "cheap",
       "extract": "cheap",
       "summarize": "cheap",
       "generate": "standard",
       "analyze": "standard",
       "architect": "premium",
   }

   def select_model(task_type: str) -> str:
       tier = MODEL_TIER_MAP.get(task_type, "standard")
       return TIER_CONFIGS[tier]["models"][0]  # Primary model in tier
   ```

2. **Prompt compression** — reduce input tokens without losing quality:
   ```python
   # Before: 2000 tokens
   VERBOSE_PROMPT = """
   You are an expert DevOps engineer with deep knowledge of Kubernetes,
   AWS, and observability systems. Your role is to analyze infrastructure
   issues and provide detailed, actionable recommendations...
   [500 more words of context]
   """

   # After: 400 tokens (same quality for most tasks)
   COMPRESSED_PROMPT = """
   Role: DevOps engineer. Analyze K8s/AWS/observability issues.
   Format: 1) Root cause 2) Fix 3) Prevention.
   Be concise. Use kubectl/AWS CLI examples.
   """

   # Measure: run both through agent-evals to confirm no quality drop
   ```

3. **Batch API for async workloads** (50% cost reduction):
   ```python
   # Anthropic Message Batches API
   import anthropic

   client = anthropic.Anthropic()

   # Create batch (async, cheaper)
   batch = client.messages.batches.create(
       requests=[
           {
               "custom_id": f"ticket-{i}",
               "params": {
                   "model": "claude-sonnet-4-20250514",
                   "max_tokens": 1024,
                   "messages": [{"role": "user", "content": ticket_text}]
               }
           }
           for i, ticket_text in enumerate(tickets)
       ]
   )

   # Poll for results (completes within 24h, usually <1h)
   while batch.processing_status != "ended":
       await asyncio.sleep(60)
       batch = client.messages.batches.retrieve(batch.id)

   # Process results
   for result in client.messages.batches.results(batch.id):
       process_ticket_result(result.custom_id, result.result.message)
   ```

4. **Token budget per agent/team**:
   ```python
   # Daily/monthly budgets with alerting
   BUDGETS = {
       "ops-agent": {"daily_usd": 50, "monthly_usd": 1000},
       "code-review": {"daily_usd": 100, "monthly_usd": 2500},
       "research": {"daily_usd": 20, "monthly_usd": 500},
   }

   async def check_budget(agent_name: str, estimated_cost: float) -> bool:
       today = date.today().isoformat()
       key = f"budget:{agent_name}:{today}"
       current = float(await redis.get(key) or 0)

       budget = BUDGETS[agent_name]
       if current + estimated_cost > budget["daily_usd"]:
           alert(f"Agent {agent_name} hit daily budget: ${current:.2f}/{budget['daily_usd']}")
           return False  # Block call

       await redis.incrbyfloat(key, estimated_cost)
       await redis.expire(key, 86400)
       return True
   ```

5. **Self-hosting crossover analysis**:
   ```python
   # When does self-hosting become cheaper than API?
   def hosting_crossover(
       monthly_api_cost: float,
       gpu_instance_cost_per_hour: float = 3.50,  # p3.2xlarge or g5.xlarge
       setup_engineering_hours: float = 40,
       engineer_hourly_rate: float = 100,
   ) -> dict:
       monthly_infra = gpu_instance_cost_per_hour * 24 * 30  # $2,520/month
       setup_cost = setup_engineering_hours * engineer_hourly_rate  # $4,000 one-time
       monthly_ops = 10 * engineer_hourly_rate  # ~10h/month maintenance

       total_hosted_monthly = monthly_infra + monthly_ops  # ~$3,520/month
       breakeven_months = setup_cost / max(monthly_api_cost - total_hosted_monthly, 1)

       return {
           "api_monthly": monthly_api_cost,
           "self_host_monthly": total_hosted_monthly,
           "setup_cost": setup_cost,
           "saves_money": monthly_api_cost > total_hosted_monthly,
           "breakeven_months": breakeven_months if monthly_api_cost > total_hosted_monthly else "never",
           "recommendation": "self-host" if monthly_api_cost > total_hosted_monthly * 1.5 else "keep API"
       }

   # Rule of thumb: self-host when API spend > $5k/month sustained
   # Below $5k/month: API wins on ops simplicity
   ```

6. **Context window optimization** — avoid paying for wasted tokens:
   ```python
   # Trim conversation history to keep only relevant context
   def optimize_context(messages: list, max_tokens: int = 50_000) -> list:
       current_tokens = count_tokens(messages)
       if current_tokens <= max_tokens:
           return messages

       # Keep system prompt + last N messages + key context
       system = [m for m in messages if m["role"] == "system"]
       recent = messages[-6:]  # Last 3 turns

       # Summarize everything in between
       middle = messages[len(system):-6]
       if middle:
           summary = quick_summarize(middle, model="claude-3-5-haiku-20241022")
           middle = [{"role": "assistant", "content": f"[Context: {summary}]"}]

       return system + middle + recent
   ```

## Decision tree

```
IF task is classification/extraction/routing:
  → Use cheap tier (Haiku/4o-mini) — 5-10x cheaper, same quality for simple tasks
IF workload is async (no user waiting):
  → Use Batch API (50% discount) — same model, half the price
IF same queries repeat frequently (>20% hit rate):
  → Add caching (see llm-caching) — effectively free after first call
IF monthly API spend > $5k and growing:
  → Evaluate self-hosting (step 5) — but only if ops capacity exists
IF context windows are large (>50k tokens/call):
  → Optimize context (step 6) — summarize old turns
IF need cost attribution per team:
  → Implement budget tracking (step 4) + agent-observability
IF quality drops when using cheaper model:
  → Run agent-evals side-by-side: cheap vs standard
  → If quality difference <5%, keep cheap
  → If quality difference >10%, keep standard for that task
```

## Anti-patterns

- ❌ Same model for everything ("Opus for classification" = 20x overpaying)
- ❌ No cost attribution (can't reduce what you can't measure)
- ❌ Self-hosting for <$2k/month API spend (ops overhead exceeds savings)
- ❌ Cutting context aggressively without measuring quality impact
- ❌ No budget limits (single runaway agent = surprise $10k bill)
- ❌ Optimizing before measuring (premature — know WHERE cost is first)
- ❌ Batch API for user-facing interactive features (latency unacceptable)

## Related skills

- `llm-caching` — specific caching strategies
- `agent-observability` — cost metrics emission and dashboards
- `agent-evals` — validating cheaper models maintain quality
- `ai-pipeline-orchestration` — choosing models per pipeline step
