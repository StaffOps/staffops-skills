---
name: llm-caching
description: Choose exact, semantic, or provider-side LLM caching.
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [ai, llm, caching, cost, latency, semantic-cache, prompt-caching]
    category: ai
    related_skills: [agent-platform-design, backing-services-metrics, llm-cost-optimization]
---
# LLM Caching

Three caching layers specific to LLM calls -- exact-match, semantic, and
provider-side prompt caching -- and the correctness risks each one carries
that a normal API/data cache does not. It deliberately does not re-teach
general Redis operations, eviction policy, or memory sizing; for that, see
`backing-services-metrics`'s Redis section (hit ratio, eviction rate, memory
saturation formulas). This skill is about which of the three layers to use,
how to key each one so it does not silently serve a wrong answer, and when
to skip caching for a request entirely.

## When to Use

Use when an LLM-calling service is spending money or latency on requests
that are identical or near-identical to ones it already answered:

- Repeated or paraphrased user queries (support bots, FAQ-style assistants)
- A stable long system prompt or retrieved context that many calls share
- High request volume where the same tool-calling agent re-derives the same
  decision from the same input repeatedly
- Cost or p99 latency budgets are under pressure and duplicate work is
  suspected as a driver

Do not reach for this skill for the rest of the cost/latency picture --
model selection, batching, prompt compression, and token-budget
enforcement are separate levers with their own failure modes. This skill
covers the caching lever only.

## Layer 1: Exact-Match Caching

Key the response on a hash of everything that can change what the model
returns, not just the prompt text. An LLM cache key differs from an
ordinary API cache key because "the same request" for an LLM includes every
sampling parameter that affects the output, not just the endpoint and body:

```
key = hash(model_id_with_version, messages, temperature, top_p, top_k,
           max_tokens, tool_definitions, system_prompt)
```

Two requests with identical prompt text but `temperature=0.0` vs
`temperature=0.7` are not the same request -- they have different intended
output distributions, and serving the deterministic-run cache entry for the
high-temperature call silently removes the variability the caller asked
for. The same applies to `tool_definitions`: a prompt that means one thing
when the model has a `refund_customer` tool available and something
different once that tool is removed is not a cache hit on the tool-less
version.

One honest caveat: `temperature=0` is a request for the *most likely*
completion, not a guarantee of bit-identical output across calls on most
providers (batching, hardware nondeterminism, and provider-side updates all
leak through). Caching at `temperature=0` is a policy choice -- "close
enough to deterministic that reuse is fine" -- not a proof that the live
call would have returned the exact cached bytes this time. State that
assumption explicitly rather than treating the cache entry as ground truth.

This is the cheapest layer and the one to build first, but it only pays off
for requests that recur byte-for-byte. A support bot answering the same
onboarding question worded five different ways gets zero hit-rate benefit
here -- that gap is what Layer 2 exists to close.

## Layer 2: Semantic Caching

Key the response on embedding-similarity to a previously answered prompt
instead of exact text match, so a paraphrase ("How do I reset my password?"
vs "I forgot my password, how do I get back in?") can hit the cache. This
closes the real gap in Layer 1, but it introduces a correctness risk exact
match does not have: the cached response was generated for a *different*,
merely similar, prompt, and "similar enough" is a judgment call encoded in
a single similarity threshold.

That threshold is a direct trade, not a knob to tune purely for hit rate:

| Threshold | Effect |
| --- | --- |
| Too loose (e.g. 0.75) | More hits, but subtly different questions get the wrong cached answer -- the failure is silent, since nothing errors, the response is just factually wrong for this specific prompt |
| Too tight (e.g. 0.97) | Correctness is safe, but hit rate collapses toward exact-match levels, undercutting the reason to run a semantic layer at all |

There is no threshold that is simply "correct" -- it depends on how costly a
wrong-but-plausible-sounding answer is for the use case. A threshold
tolerable for "explain this general concept" is not tolerable for "what are
the terms of my contract," because the second class of question has a
single correct answer and a confident wrong one is worse than a cache miss.
Always filter by model name (and model version -- see Invalidation below)
inside the similarity search, never across models: two models can answer
the same paraphrase differently, and merging their cache entries hides that.

Treat semantic cache hit rate and a correctness/complaint signal (thumbs
down, escalation rate, manual review sampling) as a paired metric, not hit
rate alone. A rising hit rate with no correctness monitoring is exactly how
a too-loose threshold goes unnoticed until a user complains.

## Layer 3: Provider-Side Prompt Caching

Several providers cache a shared prompt *prefix* server-side (Anthropic's
`cache_control: {"type": "ephemeral"}` blocks, OpenAI's automatic caching
for prefixes at or above roughly 1,024 tokens) so a long system prompt or
retrieved context shared across calls is billed and computed once instead
of on every request. This needs no cache infrastructure of your own and no
correctness risk beyond the provider's own guarantees -- there is nothing
to key, tune a threshold on, or invalidate manually within the provider's
cache lifetime.

Provider-side caching alone is sufficient when what repeats across calls is
the *prefix*, not the *whole query*: a long system prompt, a RAG-retrieved
document set, or a tool-definition block shared by many different user
turns. It is not sufficient, and an app-level cache (Layer 1 or 2) is still
needed, when the *entire* request -- prefix and user-specific suffix
together -- genuinely repeats across different users or sessions. The
provider's prefix cache does not deduplicate the suffix: two different
users asking the identical full question against the identical prefix each
trigger a full (if prefix-discounted) generation, because from the
provider's point of view the requests only share a prefix, not an outcome.
An app-level cache is the only layer that can turn that into a single
computed answer served twice.

Provider prefix caches are also short-lived (Anthropic's default ephemeral
cache is on the order of minutes, extendable with an explicit beta header)
and depend on the prefix being byte-identical and stable across calls --
reordering the cached block, or splicing in even one line of per-request
content ahead of the cache boundary, invalidates it silently and the next
call pays full price with no error to signal that it happened. If cost
telemetry does not show the expected `cache_read_input_tokens` proportion,
suspect a prefix that unintentionally changed, not a broken feature.

## Cache Invalidation for LLM Caches

TTL-only invalidation (the default for a data cache) misses two staleness
sources specific to LLM caches:

**1. Model upgrades.** A cached response generated by model vN can be wrong
for vN+1 even though the prompt and every sampling parameter are unchanged
-- the model itself is a hidden input to the function being cached. Include
the exact model identifier and version in the cache key (not just the
model family name), and treat a model upgrade as a full cache invalidation
event for that model's entries, not something a TTL will eventually catch.
A response cached for `claude-x-4-6` served against a request now routed to
`claude-x-5-0` is a stale answer with no error to flag it.

**2. Tool or downstream-behavior changes.** If a cached response represents
a function-calling decision (which tool to call, with what arguments) and
the tool's underlying behavior changes -- a new required parameter, a
changed return shape, a business-logic change in what the tool does -- the
cached decision can be structurally wrong even though the prompt that
produced it hasn't changed. Version the tool/function-calling schema the
same way you version the model, and fold that version into the cache key
so a schema change invalidates the affected entries the same way a model
upgrade does. A TTL alone assumes staleness is purely time-based; here it
is deploy-based, and the cache needs a hook into the deploy event (schema
version bump -> cache key changes -> old entries become unreachable, no
manual purge required) rather than a fixed expiry guessing when that
deploy will happen.

## When Caching Is Actively Wrong

Any request whose correct answer depends on current or live state must
never be served from a semantic cache, regardless of how similar the
prompt looks to one already cached. "What's the current status of incident
INC-4471?" and "What's the current status of incident INC-4482?" can
embed as near-identical vectors -- same structure, same intent, one token
different -- and a semantic cache tuned for paraphrase tolerance will treat
them as the same question. They are not: the correct answer is different
for each, and it changes again five minutes from now for either one. This
is the semantic-caching failure mode most likely to go unnoticed, because
nothing about the response looks malformed -- it is a well-formed,
confident, entirely wrong answer to a different incident.

Recognize this class before it reaches the cache layer, not after a wrong
answer ships: any prompt whose answer depends on "now," "current," "latest,"
"today," a live system's present state, or the literal output of a tool call
made at request time should either skip caching entirely or, at most, use a
very short-TTL exact-match cache (seconds, not hours) -- never the semantic
layer, whose entire purpose is to blur the exact wording that would
otherwise distinguish "status of X" from "status of Y." When in doubt about
whether a request class is live-state-dependent, exclude it from the
semantic cache; a missed cache hit costs latency and money, a served stale
live-state answer costs trust in the answer itself.

## Cost and Latency Framing

Caching only pays off for genuinely repeated or near-repeated work -- it
does nothing for the first occurrence of a novel query, and it cannot
substitute for choosing a cheaper model, batching requests, or trimming an
oversized prompt. Treat this skill as one lever on the cost/latency
problem, not the whole toolkit: model selection, request batching, prompt
compression, and token-budget enforcement are separate concerns with their
own trade-offs, covered in `llm-cost-optimization`, not bundled into
caching logic here.

## Anti-patterns

- Hashing only the prompt text into an exact-match cache key, omitting
  temperature, top_p, tool definitions, or the model version -- a changed
  parameter or a model upgrade then silently returns a stale-for-this-call
  response
- Tuning the semantic similarity threshold purely to raise hit rate,
  without a paired correctness signal (thumbs-down rate, escalation rate,
  manual sampling) to catch when "looser" started meaning "wrong"
- Running semantic cache lookups without filtering by model name and
  version, letting two different models' answers merge into one cache
  entry
- Relying on provider-side prefix caching alone when the *entire* query
  (not just the prefix) repeats across different users -- the provider
  cache does not deduplicate the per-user suffix
- Treating TTL as the only invalidation mechanism -- a model upgrade or a
  tool/schema change makes cached entries wrong immediately, not after a
  timer expires
- Serving a semantic-cache hit for any request whose correct answer
  depends on current/live state ("status of X right now") -- similarity in
  wording is not equivalence in answer, and this failure is silent
- Assuming `temperature=0` guarantees the cached response matches what a
  fresh call would return this instant, and presenting a cache hit as
  ground truth rather than a policy choice about acceptable reuse
