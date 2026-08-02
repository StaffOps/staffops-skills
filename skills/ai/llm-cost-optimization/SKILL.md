---
name: llm-cost-optimization
description: "Cut LLM API spend via model choice, tokens, and batching."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [llm, cost, finops, model-selection, tokens, batching, self-hosting]
    category: ai
    related_skills: [cost-explorer, skill-eval-harness, agent-evals, llm-caching, agent-observability]
---

# LLM Cost Optimization

Decision framework for reducing LLM API/inference spend: model tier selection,
prompt and context-length auditing, batching for async workloads, and the
self-hosting-vs-API crossover. It deliberately does not re-derive prompt
caching mechanics (`llm-caching`), model-quality evaluation methodology
(`agent-evals`), or cost-metric emission/dashboarding (`agent-observability`)
— those are each a sibling skill's job, cross-referenced at the point each
one matters below rather than re-described here.

## When to Use

Use when a team is defaulting to the most capable model for every call, when
LLM API cost has become a visible line item without an attribution or
reduction plan, when someone proposes self-hosting an open-weight model
"to save money," or when a workload could plausibly move off the synchronous
API path (batch, async pipelines). Not for choosing *which* model to build a
new feature on for capability reasons alone — that decision also involves
correctness, latency, and API surface, which belong to a build-time
evaluation, not a cost skill.

## Model selection: the single biggest lever

Within a single provider's model family, adjacent tiers typically differ by
5-15x in per-token price, and the gap between the cheapest and most capable
model in the lineup (especially once you account for a frontier model running
at a high "thinking" or reasoning-effort setting, which multiplies token
consumption on top of the per-token price gap) commonly reaches 50-100x for
the same task. No other lever in this skill moves the bill by that much.

The mistake this catalog sees most often is not "using an expensive model" —
it is using the expensive-model default for every call site without ever
testing whether a cheaper one is *sufficient* for that specific call site.
Model choice should be a per-task decision, not a codebase-wide constant.

### Decision framework: which axis is this task on?

| Task shape | Volume | Stakes | Default toward |
|---|---|---|---|
| Classification, extraction, routing, tagging | High (thousands+/day) | Low-medium — errors are cheap to catch downstream | Smallest/cheapest tier that clears the accuracy bar |
| Summarization, templated generation, simple Q&A | Medium | Low-medium | Mid tier; test the cheap tier before assuming you need mid |
| Multi-step reasoning, code generation, agentic tool use | Low-medium | Medium-high | Mid-to-top tier; reasoning/effort settings matter more than raw model choice here |
| Legal, financial, security, or irreversible-action judgment | Low | High — a wrong answer is expensive or dangerous | Top tier, and budget for a second (verification) pass regardless of per-token cost |

The two axes that matter are **volume** (how much does a per-token delta cost
multiply into?) and **stakes** (how expensive is one wrong answer?). High
volume amplifies a small per-token saving into a large absolute one; high
stakes amplifies the cost of the model being wrong. A task that is both
high-volume and low-stakes (e.g. "does this support ticket mention billing")
is the highest-leverage place to test a cheaper model — the per-call savings
compounds across volume, and an occasional misclassification is cheap to
catch downstream (a human review queue, a fallback rule).

### Prove it, don't guess it

"This task is simple enough for the cheap model" is a hypothesis, not a
decision. The only way to know whether a smaller model is sufficient for a
*specific* task is to run the same set of representative cases through both
models and compare quality against a rubric — `agent-evals` is built exactly
for this: a golden-dataset regression suite, run through `skill-eval-harness`'s
paired baseline/candidate methodology (`scripts/eval_harness.py plan` / `run`
/ `score`), judged blind against a real rubric, with a release gate the
cheaper model has to clear before it's trusted. Downgrading a model based on
"it looked fine in a couple of manual tries" is how a cost optimization
becomes a production quality regression that nobody notices until a customer
does.

## Prompt and context-length cost

Token count is the direct cost driver, and it is controllable independent of
model choice. Before reaching for a cheaper model or self-hosting, audit
where tokens are actually going — it is common to find 30-50% of a call's
input tokens are avoidable bloat.

### What drives token bloat

- **Unnecessarily long system prompts.** A system prompt accumulates
  instructions over a project's life and rarely gets pruned. Every
  instruction that no longer applies, every caveat added to fix a bug that
  was later fixed a different way, every "just in case" clause — all of it
  is billed on every single call, forever, regardless of whether the current
  request needs it.
- **Redundant few-shot examples.** Five examples where three would produce
  the same accuracy is a straightforward multiplier on every call. Few-shot
  count is a variable to sweep during evaluation, not a number to set once
  and forget.
- **Untruncated conversation history.** Resending the full turn-by-turn
  history on every request in a multi-turn session means cost grows
  quadratically with conversation length even though each individual message
  is cheap. Summarizing or dropping stale turns keeps the per-request cost
  roughly flat.
- **Verbose tool-result payloads fed back into context.** A tool call that
  returns a full API response, a full file, or a full query result set and
  passes all of it back into the model's context re-bills that payload on
  every subsequent turn of the same conversation, whether or not the model
  needs most of it. Paginating, summarizing, or extracting only the relevant
  fields before the result re-enters context is one of the highest-leverage,
  least-discussed cost fixes — it is common for tool-result bloat to
  dominate a long agentic session's token bill more than the system prompt
  or the model's own output.

### How to audit it

1. **Count tokens per component, not just per request.** Break the assembled
   prompt into system prompt, few-shot block, conversation history, and
   tool-result payloads, and count each separately. A flat "this request
   used N input tokens" number tells you the total but not where to cut.
2. **Compare before/after on the same representative request** whenever you
   trim a component, rather than assuming a trim is free of quality impact —
   a shortened system prompt or a dropped few-shot example can silently
   regress accuracy on edge cases the removed content was covering.
3. **Remember output tokens are typically priced several times higher than
   input tokens** on every major provider. A verbose model response costs
   more per token than a verbose prompt — capping generation length (an
   explicit output-length instruction, or a hard token ceiling) is as
   real a lever as trimming the input side, and is usually the cheaper one
   to fix because it doesn't touch prompt correctness.

## Caching

Prompt caching (reusing a previously-processed prefix at a fraction of the
input-token price on a cache hit) is one of the largest cost levers available
and is entirely orthogonal to model choice — it applies at whatever tier you
pick. `llm-caching` covers breakpoint placement, cache-key composition, TTL
selection, and invalidation pitfalls in depth; only the cost shape is
repeated here since it's the number that drives the model-selection and
batching tradeoffs in this skill. Cache writes typically cost more than a
normal input token (roughly 1.25-2x, depending on TTL) while cache reads cost
a fraction of it (roughly 0.1x) — so caching only pays for itself once a shared
prefix is reused across two or more requests, and the payoff scales with how
often that prefix repeats (a long-lived system prompt or tool-definition
block reused across thousands of calls is the ideal candidate; a prompt that
differs from the first token on every request never benefits).

## Batching

For non-interactive workloads — bulk classification, offline extraction,
overnight report generation, dataset labeling — most providers offer a batch
API at a meaningfully lower price than the equivalent real-time call (commonly
around half price). The tradeoff is latency: batch jobs typically complete
within an hour but the SLA is measured in hours, not seconds, and results are
retrieved by polling rather than returned inline.

Batching is a straightforward win exactly when a workload has **no human
waiting synchronously on the response**. It is the wrong tool the moment a
user, an interactive agent loop, or a downstream system with its own latency
budget is blocked on the result — forcing an interactive path onto the batch
API to save money produces a product that feels broken, not a cost win.
Batching and model-tier selection compound: a high-volume, low-stakes,
non-interactive classification job is the single best candidate in this
skill for stacking a cheaper model *and* the batch discount on the same
workload.

## Self-hosting vs. API pricing

At sufficient volume, self-hosting an open-weight model on owned or rented
GPU infrastructure can undercut a provider's per-token price — but "sufficient
volume" is doing a lot of work in that sentence, and the crossover point is
usually further out than teams expect once the full cost is counted honestly.

The comparison that actually matters is:

```
(monthly token volume x per-token API price)
        vs.
(GPU instance cost, on-demand or reserved)
  + (ops engineering time: serving stack setup and tuning,
     autoscaling for load, model weight updates and re-validation,
     monitoring and on-call for a service you now operate)
```

The GPU instance line item is usually the smaller half of that equation once
a team has actually run a self-hosted inference stack in production — a
serving framework needs load-based autoscaling to avoid paying for idle GPUs
around the clock, model updates require a re-validation pass against your own
eval set (see the model-selection section above — the same evidence
discipline applies to "is the open-weight model still good enough" as to
"is the cheap API model good enough"), and someone now owns on-call for an
inference service that previously was somebody else's uptime problem. Teams
that only compare API $/token against GPU $/hour and skip the ops-burden term
consistently underestimate the true crossover volume.

This catalog does not yet have a dedicated GPU-hosting skill (no serving-
framework choice, no autoscaling-for-inference guidance, no GPU instance
family selection) — do not fabricate that guidance here. Once self-hosting is
underway, `ec2-rightsizing-patterns` covers the general EC2 utilization and
Compute Optimizer methodology for right-sizing whatever instance family you
land on, but it predates GPU-specific workload guidance and should be read as
"the general instance-sizing discipline," not "GPU inference sizing advice."

## Budget and alerting: the decision framework

Getting cost visibility in the first place — emitting per-request token usage
and the `agent_llm_cost_dollars_total` counter as a metric, wiring it into a
dashboard — is `agent-observability`'s job, not this skill's; this section
assumes that visibility already exists and covers what to *do* with it.

The recurring failure mode is a budget that exists only as a dashboard panel
or a Slack alert that fires after the money is already spent. A cost control
that only tells you what already happened is not a control — a real budget
cap has to be a hard gate that refuses to proceed *before* the spend, not a
notification after it.

`skill-eval-harness` (in this catalog's `workflows/` category) is a concrete,
grounded precedent for exactly this pattern, even though it was built for a
different problem (comparing skill versions, not routing LLM traffic).
Its `--budget-usd` flag is **required on both `plan` and `run`, with no
default** — omitting it is a hard `argparse` error, never a silent fallback
ceiling — and its preflight check multiplies the count of not-yet-completed
work items by a per-call cost estimate and refuses to invoke anything, even
once, if the projected total exceeds the budget. Separately, `run` also
tracks actual reported cost per call in-loop and stops when the remaining
budget hits zero, as a second check layered on top of the preflight one. The
transferable principle for LLM cost control generally: estimate spend
*before* the first call goes out, refuse to start if the estimate is over
budget, and keep a second, in-loop check tracking real spend as a backstop —
a single after-the-fact "you're over budget" alert catches the overrun only
once it has already happened.

Applied to production LLM traffic rather than an eval run, the same shape
looks like: a per-request or per-session cost ceiling checked before the call
is made (not after), a hard stop or fallback path when a rolling window's
spend crosses a threshold, and an explicit owner who is paged — not a
dashboard nobody is watching.

## Anti-patterns

- **Defaulting every call site to the most capable model** without testing
  whether a cheaper tier clears the accuracy bar for that specific task.
- **Switching to a cheaper model based on a handful of manual tries** instead
  of a paired evaluation against representative cases — this is exactly the
  "switching on vibes" this skill exists to prevent.
- **Measuring token cost only at the total-request level** and never breaking
  it down by system prompt, few-shot block, history, and tool-result payload
  — you cannot cut what you haven't located.
- **Growing conversation history unboundedly** in a multi-turn session
  instead of summarizing or dropping stale turns, turning a linear workload
  into a quadratic cost curve.
- **Feeding full, unfiltered tool-result payloads back into context** on
  every turn of an agentic loop instead of paginating or extracting only the
  fields the model actually needs.
- **Forcing an interactive workload onto the batch API** to chase the price
  discount, producing a broken user-facing latency profile.
- **Comparing self-hosting cost using only GPU $/hour against API $/token**
  and omitting the ops-engineering cost of running an inference service
  (autoscaling, model updates, on-call).
- **Treating a cost dashboard or a post-hoc Slack alert as a budget control**
  instead of a preflight gate that refuses to spend past a threshold before
  the call goes out.
- **Inventing caching mechanics, GPU-hosting specifics, or eval-harness
  details this catalog doesn't have yet** instead of stating plainly that the
  supporting skill isn't written — a fabricated cross-reference is worse than
  an honest gap.

## Reference

- `cost-explorer` — the AWS-side cost analysis and budget-alert patterns
  (Cost Explorer queries, AWS Budgets thresholds) this skill's budget
  discipline generalizes from
- `skill-eval-harness` — the concrete paired-evaluation and hard-budget-gate
  precedent cited above (`workflows/skill-eval-harness`)
- `ec2-rightsizing-patterns` — general EC2 utilization and Compute Optimizer
  methodology, relevant once self-hosting is underway (not GPU-specific)
- `agent-evals` — the golden-dataset methodology behind "prove it, don't
  guess it" for a proposed model downgrade
- `llm-caching` — prompt-caching mechanics (breakpoint placement, cache-key
  composition, TTL, invalidation) behind the cost shape cited above
- `agent-observability` — where the cost/usage metrics this skill's budget
  section assumes already exist actually get emitted
