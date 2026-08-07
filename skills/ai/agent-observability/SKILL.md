---
name: agent-observability
description: "Use when instrumenting LLM agent calls with OTel spans for token counts, cost tracking, tool-call structure, and sensitive-content redaction — the delta between normal service tracing and tracing an agentic loop."
---
# Agent Observability

## When to use

- Adding tracing/metrics to a service that calls an LLM API or runs an agentic loop
- Tracking per-call cost, token usage, and latency across model providers
- Building dashboards for agent tool-call patterns and failure rates
- Detecting token budget exhaustion or runaway loops in production
- Correlating agent decisions with downstream actions (file writes, API calls)

## When NOT to use

- Setting up OTel Collector pipelines from scratch (use `otel-collector-multi-cluster`)
- Writing TraceQL/LogQL queries (use `tempo-traceql-patterns` / `loki-logql-patterns`)
- General service instrumentation without LLM calls (use `dotnet-otel-patterns` / `python-otel-patterns`)
- Cost optimization decisions (use `llm-cost-optimization`)

## Steps

1. **Define semantic conventions for LLM spans** (OpenTelemetry GenAI semconv):
   ```python
   # Python — instrument an LLM call
   from opentelemetry import trace
   from opentelemetry.semconv.ai import SpanAttributes  # or manual keys

   tracer = trace.get_tracer("agent.llm")

   def call_llm(messages, model="claude-sonnet-4-20250514"):
       with tracer.start_as_current_span("llm.chat", kind=trace.SpanKind.CLIENT) as span:
           span.set_attribute("gen_ai.system", "anthropic")
           span.set_attribute("gen_ai.request.model", model)
           span.set_attribute("gen_ai.request.max_tokens", 4096)

           response = client.messages.create(model=model, messages=messages, max_tokens=4096)

           span.set_attribute("gen_ai.response.model", response.model)
           span.set_attribute("gen_ai.usage.input_tokens", response.usage.input_tokens)
           span.set_attribute("gen_ai.usage.output_tokens", response.usage.output_tokens)
           span.set_attribute("gen_ai.usage.total_tokens",
               response.usage.input_tokens + response.usage.output_tokens)

           # Cost calculation
           cost = calculate_cost(model, response.usage)
           span.set_attribute("gen_ai.usage.cost_usd", cost)

           return response
   ```

2. **Instrument tool calls within an agent loop**:
   ```python
   def agent_loop(task: str):
       with tracer.start_as_current_span("agent.run") as agent_span:
           agent_span.set_attribute("agent.task", task[:200])  # Truncate
           agent_span.set_attribute("agent.max_steps", 10)
           step = 0

           while not done and step < 10:
               step += 1
               with tracer.start_as_current_span(f"agent.step.{step}") as step_span:
                   response = call_llm(messages)

                   if response.stop_reason == "tool_use":
                       for tool_call in response.content:
                           if tool_call.type == "tool_use":
                               with tracer.start_as_current_span("agent.tool_call") as tool_span:
                                   tool_span.set_attribute("agent.tool.name", tool_call.name)
                                   tool_span.set_attribute("agent.tool.input_size",
                                       len(json.dumps(tool_call.input)))
                                   result = execute_tool(tool_call)
                                   tool_span.set_attribute("agent.tool.success",
                                       not result.is_error)

           agent_span.set_attribute("agent.steps_taken", step)
           agent_span.set_attribute("agent.completed", done)
   ```

3. **Emit cost metrics** (Prometheus/VictoriaMetrics):
   ```python
   from opentelemetry import metrics

   meter = metrics.get_meter("agent.cost")
   token_counter = meter.create_counter("gen_ai.tokens.total",
       description="Total tokens consumed", unit="tokens")
   cost_counter = meter.create_counter("gen_ai.cost.total",
       description="Total LLM spend", unit="usd")
   step_histogram = meter.create_histogram("agent.steps_per_run",
       description="Steps per agent invocation")

   # After each call:
   token_counter.add(total_tokens, {"model": model, "agent": agent_name})
   cost_counter.add(cost_usd, {"model": model, "agent": agent_name})
   ```

4. **Redact sensitive content** — NEVER log full prompts/completions in production:
   ```python
   # OTel processor that strips prompt content
   # In collector config:
   processors:
     attributes/redact-prompts:
       actions:
         - key: gen_ai.prompt
           action: delete
         - key: gen_ai.completion
           action: delete
   ```

   For debug environments, log to a separate, short-retention Loki stream:
   ```python
   if os.getenv("ENVIRONMENT") in ("LOCAL", "DEV"):
       span.set_attribute("gen_ai.prompt", json.dumps(messages)[:10000])
   ```

5. **Build alerting** on agent health:
   ```yaml
   # VMRule
   groups:
     - name: agent-health
       rules:
         - alert: AgentCostSpike
           expr: |
             sum(rate(gen_ai_cost_total[5m])) by (agent) > 0.10
           for: 5m
           labels: { severity: warning }
           annotations:
             summary: "Agent {{ $labels.agent }} spending >$0.10/min"

         - alert: AgentStuckLoop
           expr: |
             histogram_quantile(0.99, rate(agent_steps_per_run_bucket[15m])) > 9
           for: 10m
           labels: { severity: critical }
           annotations:
             summary: "Agent {{ $labels.agent }} hitting max steps consistently"
   ```

6. **Dashboard essentials** (Grafana):
   - Token usage by model/agent (stacked timeseries)
   - Cost per agent per day (stat + trend)
   - Tool call success rate (by tool name)
   - Steps-per-run distribution (histogram)
   - P99 agent latency (end-to-end)

## Decision tree

```
IF instrumenting a new LLM-calling service:
  → Add span attributes from step 1 + cost metrics from step 3
  IF service runs an agentic loop (multi-step):
    → Add step/tool instrumentation from step 2
  IF production deployment:
    → Enable prompt redaction (step 4)
    → Set up cost alerts (step 5)
  ELIF dev/local:
    → Log full prompts for debugging
ELIF adding observability to existing agent:
  → Check what spans already exist (tracer name, attributes)
  → Add ONLY the missing GenAI attributes, don't duplicate spans
```

## Anti-patterns

- ❌ Logging full prompts/completions in production (PII leak, storage explosion)
- ❌ No cost attribution per agent/model (impossible to optimize what you can't measure)
- ❌ Treating agent traces like HTTP traces (missing token/cost/step semantics)
- ❌ One giant span for the entire agent run (no visibility into per-step behavior)
- ❌ Hardcoded cost-per-token without updating when pricing changes
- ❌ Alerting only on errors, not on cost or step-count anomalies

## Related skills

- `llm-cost-optimization` — act on the cost data this skill emits
- `llm-caching` — reduce tokens measured here via caching
- `rag-observability-evals` — specialized retrieval-quality metrics
- `otel-collector-multi-cluster` — collector pipeline setup
- `python-otel-patterns` / `dotnet-otel-patterns` — base instrumentation
