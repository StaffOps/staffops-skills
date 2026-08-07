---
name: ai-pipeline-orchestration
description: "Use when designing multi-step LLM pipelines — chaining prompts, routing between models, implementing fallback/retry, managing context windows across steps, and orchestrating async fan-out/fan-in patterns for agent workflows."
---
# AI Pipeline Orchestration

## When to use

- Designing a multi-step LLM pipeline (classify → route → generate → validate)
- Implementing model fallback (expensive model fails → cheaper model retries)
- Managing context window limits across chained calls
- Building async fan-out/fan-in for parallel agent subtasks
- Deciding between orchestration frameworks vs custom code

## When NOT to use

- Single-shot prompt with no chaining (just call the API)
- Evaluating pipeline quality (use `agent-evals`)
- Cost optimization of individual calls (use `llm-cost-optimization`)
- Observability of pipeline runs (use `agent-observability`)

## Steps

1. **Design the pipeline DAG** — identify steps and dependencies:
   ```yaml
   # pipeline-definition.yaml
   pipeline: ticket-resolution
   steps:
     - id: classify
       model: claude-haiku
       input: "{ticket_text}"
       output: category, severity, confidence
     - id: route
       type: conditional
       condition: "classify.confidence > 0.8"
       true_branch: auto_resolve
       false_branch: human_escalate
     - id: auto_resolve
       model: claude-sonnet
       input: "{ticket_text}\nCategory: {classify.category}"
       output: resolution_text
     - id: validate
       model: claude-haiku
       input: "Does this resolution address the ticket? Ticket: {ticket_text}\nResolution: {auto_resolve.resolution_text}"
       output: is_valid (bool)
   ```

2. **Implement with lightweight orchestration** (no heavy framework needed for <10 steps):
   ```python
   # pipeline.py — simple, observable, testable
   from dataclasses import dataclass
   from opentelemetry import trace

   tracer = trace.get_tracer("pipeline.ticket")

   @dataclass
   class PipelineContext:
       ticket_text: str
       category: str = ""
       severity: str = ""
       confidence: float = 0.0
       resolution: str = ""

   async def run_pipeline(ticket_text: str) -> PipelineContext:
       ctx = PipelineContext(ticket_text=ticket_text)

       with tracer.start_as_current_span("pipeline.ticket-resolution"):
           # Step 1: Classify (cheap model)
           with tracer.start_as_current_span("step.classify"):
               result = await call_llm(
                   model="claude-3-5-haiku-20241022",
                   messages=[{"role": "user", "content": CLASSIFY_PROMPT.format(ticket=ticket_text)}],
                   response_format=ClassifyResponse
               )
               ctx.category = result.category
               ctx.confidence = result.confidence

           # Step 2: Route
           if ctx.confidence < 0.8:
               return ctx  # Escalate to human

           # Step 3: Resolve (expensive model)
           with tracer.start_as_current_span("step.resolve"):
               ctx.resolution = await call_llm_with_fallback(
                   primary="claude-sonnet-4-20250514",
                   fallback="claude-3-5-haiku-20241022",
                   messages=[{"role": "user", "content": RESOLVE_PROMPT.format(ctx=ctx)}]
               )

           return ctx
   ```

3. **Implement model fallback with retry**:
   ```python
   import asyncio
   from tenacity import retry, stop_after_attempt, wait_exponential

   MODEL_FALLBACK_CHAIN = [
       {"model": "claude-sonnet-4-20250514", "max_tokens": 4096},
       {"model": "claude-3-5-haiku-20241022", "max_tokens": 4096},
       {"model": "gpt-4o-mini", "max_tokens": 4096},  # Cross-provider fallback
   ]

   async def call_llm_with_fallback(messages: list, chain=MODEL_FALLBACK_CHAIN):
       for i, config in enumerate(chain):
           try:
               return await call_llm(messages=messages, **config)
           except (RateLimitError, ServiceUnavailableError) as e:
               if i == len(chain) - 1:
                   raise  # Last resort exhausted
               await asyncio.sleep(2 ** i)  # Exponential backoff
           except ContextLengthExceeded:
               # Truncate context and retry same model
               messages = truncate_context(messages, config["max_tokens"] * 0.8)
               return await call_llm(messages=messages, **config)
   ```

4. **Fan-out/fan-in for parallel subtasks**:
   ```python
   async def parallel_research(topics: list[str]) -> list[str]:
       """Fan-out to N parallel LLM calls, fan-in results."""
       with tracer.start_as_current_span("pipeline.fan-out", attributes={"fan_width": len(topics)}):
           tasks = [
               call_llm(
                   model="claude-3-5-haiku-20241022",  # Cheap model for parallel work
                   messages=[{"role": "user", "content": f"Research: {topic}"}]
               )
               for topic in topics
           ]
           results = await asyncio.gather(*tasks, return_exceptions=True)

           # Handle partial failures
           successes = [r for r in results if not isinstance(r, Exception)]
           failures = [r for r in results if isinstance(r, Exception)]

           if failures:
               log.warning(f"{len(failures)}/{len(results)} parallel tasks failed")

           return successes
   ```

5. **Manage context window across steps** — summarize between steps:
   ```python
   MAX_CONTEXT_TOKENS = 100_000  # Model-specific

   def prepare_context_for_next_step(history: list[dict], budget_fraction=0.7) -> list[dict]:
       """Keep context within budget by summarizing older steps."""
       token_count = count_tokens(history)
       budget = int(MAX_CONTEXT_TOKENS * budget_fraction)

       if token_count <= budget:
           return history

       # Summarize everything except the latest 2 messages
       to_summarize = history[:-2]
       summary = call_llm_sync(
           model="claude-3-5-haiku-20241022",
           messages=[{"role": "user", "content": f"Summarize concisely:\n{json.dumps(to_summarize)}"}]
       )
       return [{"role": "assistant", "content": f"[Previous context summary]: {summary}"}] + history[-2:]
   ```

## Decision tree

```
IF pipeline has ≤3 steps with linear dependency:
  → Simple async/await chain (no framework needed)
IF pipeline has conditional routing (classify → branch):
  → if/elif in code, traced per-branch
IF pipeline has parallel independent subtasks:
  → asyncio.gather() with timeout + partial failure handling
IF pipeline steps might fail independently:
  → Add fallback chain per step (step 3)
IF total context exceeds model window across steps:
  → Add summarization between steps (step 5)
IF pipeline will run >1000x/day:
  → Consider cheaper models for classification/routing steps
  → Add caching for repeated inputs (see llm-caching)
IF orchestration has >10 steps with complex dependencies:
  → Consider a framework (LangGraph, Prefect) — but only then
```

## Anti-patterns

- ❌ Using an orchestration framework for a 3-step linear pipeline (overengineering)
- ❌ Same expensive model for every step (classification doesn't need Sonnet)
- ❌ No fallback — single model failure kills the entire pipeline
- ❌ Passing full context between all steps (token waste, window overflow)
- ❌ No timeout on individual steps (one slow call blocks everything)
- ❌ Swallowing errors in fan-out silently (partial results look complete)
- ❌ No tracing per step (debugging failures is blind)

## Related skills

- `llm-cost-optimization` — choosing models per step to minimize cost
- `llm-caching` — caching repeated classification/routing calls
- `agent-observability` — tracing pipeline execution
- `agent-evals` — measuring end-to-end pipeline quality
