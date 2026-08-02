---
name: agent-observability
description: "Emit spans, tokens, and cost signals for LLM agent turns."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [ai, agent, observability, otel, tracing, cost, llm]
    category: ai
    related_skills: [mcp-server-development, agent-platform-design, otel-collector-multi-cluster, dotnet-otel-patterns, python-otel-patterns, session-handoff, llm-cost-optimization]
---
# Agent Observability

What to add to an LLM-agent invocation's telemetry that a normal HTTP or gRPC
span does not already carry: token counts, per-call dollar cost, tool-call
structure, and the sensitive-content handling that prompts and completions
need but ordinary request bodies usually don't. This skill assumes OTel
Collector, exporters, and the Tempo/Loki/VictoriaMetrics backends are already
running — it does not cover setting any of that up. It is exclusively about
the delta between instrumenting a normal service call and instrumenting one
LLM-agent turn on top of infrastructure that already exists.

## When to Use

Use when adding traces, metrics, or logs to a service that calls an LLM API
directly or runs an agentic loop (tool-calling, multi-step reasoning) — not
when setting up OTel Collector pipelines, choosing exporters, or writing
TraceQL/LogQL queries against data that's already flowing. Reach for this
specifically when:

- Designing what to put on the span around an LLM API call
- Deciding how to represent a multi-step agent loop as one trace instead of
  many disconnected spans
- Emitting cost as a metric so it can be aggregated and alerted on
- Handling a prompt or completion that might contain PII, secrets, or
  proprietary data in a trace, log, or metric

## What This Skill Deliberately Does Not Cover

This catalog already has deep OTel coverage; don't re-derive it here:

- **OTel Collector topology, receivers, processors, exporters** — see
  `otel-collector-multi-cluster` for the agent → gateway → OTLP chain and
  why tail sampling belongs at the gateway.
- **Cross-signal correlation in Grafana** (exemplars, `tracesToLogsV2`,
  service graph) — see `grafana-cross-signal-correlation`.
- **Root-span mechanics for background workers** (`StartRootActivity` in
  .NET, `start_root_span` in Python) — covered in `dotnet-otel-patterns` and
  `python-otel-patterns`. This skill reuses that pattern rather than
  reinventing it (see below) instead of re-explaining `Activity.Current`
  semantics.
- **Querying traces once they land in Tempo** — see `tempo-traceql-patterns`.
- **What to DO with cost visibility once you have it** (model tiering,
  caching, batching, picking a cheaper model for a subtask) — that is
  `llm-cost-optimization`'s job, a separate optimization concern from
  emitting the signal, which is all this skill covers.
- **Building the MCP server or agent harness itself** — see
  `mcp-server-development` (which already documents wrapping every
  `tools/call` handler in a span named after the tool, with truncated
  arguments and success/failure attributes) and `agent-platform-design`
  (which defines the org's baseline `agent_executions_total` /
  `agent_execution_duration_seconds` / `agent_errors_total` /
  `agent_llm_tokens_total` metrics). This skill extends that baseline with
  the LLM-call-specific detail those two skills don't go into.

## Span Attributes for an LLM Call

A normal HTTP client span has method, route, status code. A span wrapping an
LLM API call needs enough to answer "what did this cost, and did it work"
without opening a trace-viewer plugin. At minimum, put these on the span:

| Attribute | Why it's not on a normal HTTP span |
|-----------|-------------------------------------|
| Model name and version | Cost and latency both depend on which model served the request — a normal HTTP span's target host doesn't tell you this |
| Prompt (input) token count | The billing unit for the request; not derivable from payload size |
| Completion (output) token count | Same — and priced differently from input tokens |
| Computed cost for this call | See "Cost as a First-Class Metric" below — put it here too, as a span attribute, so a single slow/expensive trace is diagnosable without cross-referencing a separate metric |
| Retry count | Distinguishes "the provider was flaky" from "the call is slow" |
| Cache hit (if the app has a prompt/response cache) | Explains a suspiciously fast, suspiciously cheap span |
| Truncated or redacted view of the prompt and completion | See "Sensitive Data" below — never the raw full content by default |

There is an emerging OTel semantic-conventions namespace for generative-AI
telemetry (`gen_ai.*` — request/response model, token usage). Treat it as
**experimental and still moving**: check this catalog's local OTel docs
cache (`local-docs` steering, `EXTERNAL-DOCS/opentelemetry.io`) for the
current field names before hardcoding them, the same way `mcp-server-development`
tells you to verify SDK behavior against live docs rather than cached
knowledge. If the semconv names in the cached docs are still marked
experimental or don't match your OTel Collector/SDK version, extending the
org's own existing convention (`agent_llm_tokens_total` from
`agent-platform-design`, labeled `agent_name`/`model`/`direction`) is the
safer default — it's already deployed, already has a dashboard, and won't
break when the semconv namespace stabilizes under a different name.

### Tool calls as child spans or span events

A tool call made mid-turn is either its own child span (preferred when the
tool call has meaningful duration or can itself fail independently — an API
call, a database query, a shell command) or a span event on the parent LLM
span (acceptable for something instantaneous, like a lookup against an
in-memory cache). Either way, record on it: the tool name, a truncated view
of the arguments, whether it hit a cache, and success/failure. This is the
same shape `mcp-server-development` already prescribes for MCP `tools/call`
handlers (span named `mcp.tool.<name>`, redacted arguments, success/failure
attribute) — reuse that pattern for tool calls the agent makes directly,
not just ones routed through an MCP server.

## Representing the Agentic Loop as One Trace

A single user request to an agent can trigger several LLM calls and tool
calls in a loop before it produces a final answer. Left uninstrumented,
each of those becomes an unrelated span with no shared trace ID — you can
see that five LLM calls happened in some time window, but not that they
were all one causal chain answering one user request.

The fix is standard OTel parent/child semantics, not agent-specific jargon:

1. **Start one root span per incoming turn** — the whole loop (however many
   LLM calls and tool calls it takes) is one root span, e.g. `agent.turn`.
   This is the same root-per-work-item pattern `dotnet-otel-patterns` and
   `python-otel-patterns` document for workers (`StartRootActivity` /
   `start_root_span`, used there for `queue.consume` per message) — apply
   it at the granularity of one user turn, not one LLM call.
2. **Every LLM call and tool call within that turn nests as an ordinary
   child span** via the ambient span context. Unlike the worker case, you
   do *not* need to null out `Activity.Current` between iterations of the
   loop — the whole point here is that the loop's iterations *should*
   share a parent, because they're one causal unit of work. Only clear the
   parent when starting the *next* turn (the next independent user
   request), exactly as the worker pattern clears it between independent
   queue messages.
3. **The loop's own control flow is visible on the root span**, not
   reconstructed after the fact — record the number of LLM calls made,
   the number of tool calls made, and the reason the loop stopped
   (`max_iterations_reached`, `final_answer`, `error`) as attributes on
   `agent.turn`.

The result in Tempo is one trace per user turn with a clean waterfall: root
span, LLM call, tool call, LLM call, tool call, LLM call — all nested,
queryable with `tempo-traceql-patterns` like any other multi-hop trace.

## Cost as a First-Class Metric

A normal service amortizes cost — nobody tracks the dollar cost of a single
HTTP request in real time. An LLM call is different: cost is computable
per-invocation, right now, from `(prompt_tokens × input_price) +
(completion_tokens × output_price)` for the model that served it. That
makes it worth emitting as a proper metric, not just a number buried in a
log line — a log line can't be aggregated, alerted on, or graphed next to
your other cost metrics the way a Counter can.

**Emit it as a Counter, mirroring the org's existing token metric.**
`agent-platform-design` already defines `agent_llm_tokens_total` (Counter,
labels `agent_name`/`model`/`direction`). Extend that convention with a
companion cost metric rather than inventing an unrelated shape:

```
agent_llm_cost_dollars_total{agent_name="...", model="..."} — Counter
```

Compute the cost at the same call site that reads `usage.input_tokens` /
`usage.output_tokens` off the API response, using the model's published
per-token price, and increment both counters together. This gives you:
cost per agent, cost per model, cost over time — aggregable in
VictoriaMetrics exactly like any other cost metric, and alertable with the
same VMAlert rules this catalog already uses for other cost thresholds.

**Keep the label set as low-cardinality as every other metric in this
catalog.** `agent_name` and `model` are both bounded (a handful of agents,
a handful of models) — that's fine. A `user_id`, `session_id`, or
`conversation_id` label is not: per `vm-cardinality-management` and this
catalog's general cardinality rules, that turns one cost metric into
thousands of time series and defeats the 2000-series-per-metric OTel SDK
default. If you need cost broken down by user or conversation, that
breakdown belongs in a **trace attribute** (on the `agent.turn` root span)
or a **log line**, not a metric label — traces and logs have different
retention and query characteristics that tolerate high cardinality; metrics
do not.

**What to do with the cost signal once you have it — model tiering, caching,
batching cheaper subtasks to a smaller model — is a separate concern from
emitting it.** This skill stops at "the number exists and is queryable."

## Sensitive Data in Agent Telemetry

Prompts and completions carry PII, secrets, and proprietary business data
far more often than a typical service's request/response body does — a
user pastes a customer record into a chat prompt, an agent's tool result
includes a database row, a system prompt embeds an internal API key for
context. This is a materially different risk profile from normal APM, and
needs explicit handling rather than the default "just log the payload"
instinct.

**Default to redact-or-truncate; require an explicit opt-in flag for full
capture.** In normal operation, span attributes and log fields carrying
prompt/completion content should be truncated (first/last N characters, or
a hash) unless a debug flag is explicitly set for that session or that
deployment. This mirrors `session-handoff`'s redaction discipline for
operational artifacts — that skill's redaction table (credentials by name
not value, PII as an anonymized label, raw payloads as a truncated excerpt
plus a pointer to the full capture) is the same shape to apply here:

| What | Default behavior | Under explicit debug opt-in |
|------|-------------------|------------------------------|
| Prompt / completion text | Truncated to first/last ~200 chars, or a content hash | Full text, logged — never as a metric label |
| Tool call arguments | Truncated, per `mcp-server-development`'s guidance for `tools/call` spans | Full arguments |
| Detected secrets/tokens in content | Never captured, even under debug — strip before truncation | Same — debug mode does not override secret stripping |

**Never put prompt/completion content in a metric label or tag.** This is
the one rule that doesn't have a debug-mode exception. Metrics have
different retention, access, and cardinality characteristics than logs or
traces — a metric label is effectively permanent and broadly queryable in
a way a single trace or log line is not. If content needs to be visible for
debugging, it goes in a span attribute or a log field, gated by the debug
flag above, never in a label.

**Use this catalog's placeholder vocabulary and no organization-specific
data when writing example prompts, logs, or fixtures for this
instrumentation** — see the repository's `CONTRIBUTING.md` for the
`<org>` / `<org-domain>` / `<ACCOUNT_ID>` conventions. The same discipline
that keeps real hostnames and account IDs out of this catalog's skills
applies to any sample payload you write while building or documenting agent
telemetry.

## Anti-patterns

- Setting up a parallel OTel SDK configuration for "AI stuff" instead of
  reusing the app's existing OTel Collector pipeline (`otel-collector-multi-cluster`)
  — an LLM call is still an outbound call from an already-instrumented
  service, not a reason to bypass the Collector.
- Logging the full raw prompt and completion by default "just in case" —
  redact/truncate by default, opt in to full capture explicitly.
- Putting `user_id`, `session_id`, or prompt content on a cost or token
  metric label — high-cardinality data belongs in traces or logs, not
  metric labels (see `vm-cardinality-management`).
- Computing cost once at the end of a session instead of per-call — you
  lose the ability to see which specific call in a multi-step loop was
  expensive, and can't alert on a runaway single call before the session
  ends.
- Leaving every LLM call and tool call in an agentic loop as an
  unconnected, unparented span — if you can't see one trace per user turn
  in Tempo, the loop isn't actually instrumented as one causal chain, it's
  just several spans that happen to be near each other in time.
- Treating the tool-call span the same as the MCP `tools/call` span
  documented in `mcp-server-development` when the tool isn't routed
  through an MCP server — the pattern (name, redacted args, success/failure)
  is worth reusing, but don't assume MCP-specific attributes apply to a
  directly-invoked tool.
- Reinventing a token/cost metric name and label set from scratch instead
  of extending the `agent_llm_tokens_total` convention `agent-platform-design`
  already established — a second, differently-shaped metric for the same
  concept fragments dashboards and alerts.
