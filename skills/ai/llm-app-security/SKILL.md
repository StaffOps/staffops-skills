---
name: llm-app-security
description: "Isolate tenants, moderate output, and rate-limit LLM apps."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [ai, llm, application-security, multi-tenant, rate-limiting, output-moderation, abuse-prevention]
    category: ai
    related_skills: [ai-agent-security, prompt-injection-defense, llm-caching, llm-cost-optimization, agent-observability, ai-security-hardening]
---
# LLM Application Security

The traditional-appsec surface of a customer- or multi-tenant-facing LLM
*application* -- a chatbot, a Q&A product, an API that wraps a model call --
which may hold no agentic tool access at all. This is deliberately **not**
`ai-agent-security` (the threat model for an agent that already holds tool,
file, or network capability, and what bounds the damage once it acts) and
deliberately **not** `prompt-injection-defense` (the specific mechanism of
an instruction smuggled inside content the model reads, and the layered
defenses against it). Both of those skills matter for the same application
if it happens to have tool access or reads untrusted content -- but this
skill's job starts one level up: tenant data isolation, the request-size and
encoding checks that have nothing to do with injection, output content
moderation as a policy/brand-safety concern rather than a security
detection, and abuse of the service itself (scraping, automation) by an
otherwise-authenticated caller. Read the two sibling skills first if the
system in question is agentic or processes untrusted third-party content --
this skill assumes those concerns are handled elsewhere and covers what is
left over.

## When to Use

Reach for this skill when designing, reviewing, or hardening an
LLM-serving application that:

- Serves more than one customer or tenant from shared infrastructure (a
  shared vector store, a shared fine-tuned model, a shared cache, or a
  shared conversation-history store)
- Exposes an API or UI where end users submit free-text input and see the
  model's output rendered back to them
- Charges per seat, per tenant, or per API key, and therefore has a
  concrete stake in one caller not extracting disproportionate value
- Has a content policy, brand-safety bar, or PII-handling obligation that
  applies to what the model is allowed to say back, independent of whether
  the input was adversarial
- Is being reviewed for launch and the checklist so far has covered
  authentication and authorization but not tenant data boundaries,
  output review, or abuse detection

Do not reach for this skill to reason about tool-permission scoping (that
is `ai-agent-security`) or about detecting instructions smuggled in
retrieved/fetched content (that is `prompt-injection-defense`). If the
answer to "does this app have tool access beyond the model call itself" is
yes, read that skill's exposure checklist too -- the two threat models
compose, they do not substitute for each other.

## 1. Multi-Tenant Isolation

The isolation question for an LLM app is not "can Tenant A authenticate as
Tenant B" (ordinary authz) -- it is "can Tenant A's data end up *inside a
response served to* Tenant B" through a shared component that was never
designed with a tenant boundary in mind. Three concrete places this leaks:

**Shared vector store / RAG index.** If tenants share one vector index
without a per-tenant scope on every read and write, a similarity search run
for Tenant B's query can return Tenant A's chunks -- there is no implicit
boundary in the index itself, embeddings from different tenants sit in the
same vector space unless something enforces a filter. Concretely, every
`upsert` and every `query` needs a tenant identifier applied consistently:
a dedicated namespace per tenant (where the vector database supports
namespaces natively), or, failing that, a mandatory metadata filter
(`tenant_id == X`) applied on every retrieval call with no code path that
skips it. The failure mode to design against specifically is a *new* query
path added later (an admin debug tool, an analytics job, a "search across
everything" feature) that queries the shared index directly and forgets the
filter -- treat the tenant filter as a property of the query client, not
something each call site has to remember to add.

**Tenant-scoped cache keys.** `llm-caching` in this catalog defines the
exact-match cache key as a hash over `model_id_with_version, messages,
temperature, top_p, top_k, max_tokens, tool_definitions, system_prompt` --
that composition is correct for a single-tenant service, but in a
multi-tenant app it is missing a dimension: if two tenants happen to send
byte-identical prompts (a common onboarding question, a shared template),
an exact-match cache keyed without a tenant identifier serves Tenant A's
cached response, generated against Tenant A's context, to Tenant B. Add
`tenant_id` as an explicit component of every cache key in a multi-tenant
app -- exact-match and semantic alike -- even when the prompt text is
otherwise identical across tenants. The same applies to conversation-history
storage: a session store keyed only by `session_id` with no tenant check on
read is one off-by-one session-ID collision (or one predictable ID) away
from returning another tenant's conversation history as if it were the
current one. Store the tenant identifier alongside the session and verify
it on every read, not only at session creation.

**The shared system prompt as a data-leak vector.** A system prompt that is
templated per tenant (injecting the tenant's name, tier, entitlements, or a
tenant-specific policy snippet into a base template) is itself tenant data,
and a bug in how that template is assembled -- a caching layer that treats
the *rendered* system prompt as reusable across tenants, a build step that
bakes one tenant's example data into what was meant to be a generic
template, a debug log that captures one tenant's fully rendered prompt and
replays it as a fixture for another -- leaks Tenant A's configuration or
example data into Tenant B's session. Treat a per-tenant system prompt as
sensitive, tenant-scoped data with the same handling discipline as the
RAG index and the cache: never cache the rendered prompt across tenants,
and audit any example/fixture data checked into tests or docs for whether
it was actually copied from a real tenant's live configuration.

## 2. Input Validation -- The Traditional Appsec Surface, Not Injection

This section is explicitly not about detecting an instruction smuggled in
the input -- `prompt-injection-defense` owns that. This is the input
handling any HTTP-facing service needs regardless of what sits behind it:

**Request size limits.** A single oversized input is a resource-exhaustion
vector independent of anything the model does with it: a multi-megabyte
payload consumes memory and CPU in whatever pre-processing runs before the
model call (tokenization, chunking, logging), and a sufficiently large
context window request measurably increases per-call latency and cost
before any content-based check even runs. Enforce a maximum request body
size and a maximum token count at the edge (gateway or application layer)
before the payload reaches tokenization -- this is standard DoS-prevention
sizing, not a content-inspection step, and it belongs in front of every
other check in this section because an oversized payload can make those
checks themselves expensive to run.

**Rate limiting per API key and per tenant.** Distinct from the abuse
detection in section 4 (which looks for a *pattern* across many requests),
this is the baseline throughput cap every API needs: a fixed requests-per-
second and concurrent-connection ceiling per credential, enforced at the
gateway, returning a standard rate-limit response rather than queuing or
degrading service for every other caller. This is the same discipline any
API applies to any expensive backend call -- the LLM call being in the
middle does not change the shape of the control, only how expensive
exceeding it turns out to be. If the model behind this app is self-hosted
rather than a third-party API, layer this flat per-caller cap with
`ai-security-hardening`'s inference-server-specific limiting (a cost-scoped
token-bucket keyed to estimated request cost, plus serving-framework
concurrency/queue-depth caps) -- they compose rather than substitute: this
one bounds throughput per caller regardless of backend, that one bounds
what a single request can do to a shared GPU-batched serving pool.

**Output-encoding for input that gets echoed back.** If the application
displays the user's own input back to them anywhere in the UI -- a chat
transcript showing "you asked: <input>", a ticket confirmation quoting the
submitted text, a log viewer rendering stored prompts -- the LLM call in
the middle of that round-trip does not remove the need for ordinary
output-encoding discipline. Text that a user submitted, that never passed
through the model at all, can still contain `<script>` or event-handler
HTML if the rendering layer treats it as trusted markup instead of escaping
it. This is unrelated to what the model does with the input; it is the same
XSS-prevention rule that applies to any user-generated content rendered in
a browser, and it is easy to skip specifically in an LLM app because
attention gets focused on "what will the model do with this text" and the
more mundane "what will the browser do with this text" gets missed.

## 3. Output Controls -- Content Policy, Not Injection Detection

`prompt-injection-defense`'s Layer 3 output validation is about parsing a
model's proposed *action* into a strict, structured shape before a
privileged tool call executes on it -- a security control against a
manipulated instruction. This section is a different concern entirely:
filtering the model's *generated text* for content-policy, brand-safety,
and PII-in-output reasons before it reaches an end user, in an application
that may take no privileged action at all -- it just returns text.

The common pattern is a moderation pass inserted between generation and
delivery: either a lightweight classifier (a toxicity/content-policy model
run against the output) or a second LLM call ("does this response violate
policy X, Y, Z -- answer yes/no with reason") gating whether the raw
generation is returned as-is, redacted, or replaced with a fallback
message. Be honest about what this costs, and size it against the actual
risk rather than adding it reflexively: a second-pass classifier adds a
fixed, usually small latency and cost increment; a second full LLM call
roughly doubles both the latency and the token cost of the turn, in the
same shape `llm-cost-optimization`'s model-selection framing scores as a
"low-medium stakes, high volume" workload -- a bulk-classification task, not a
compose-quality one, so the cheapest model tier that clears the accuracy
bar for the specific policy being checked is usually sufficient here, not
the same tier used for the primary generation.

PII-in-output deserves a separate mention from generic content moderation:
a RAG-backed app that retrieves real customer records as context can
regurgitate a name, email, or account number verbatim in a response to a
*different* user who has no business seeing that record, even with zero
adversarial input on anyone's part -- the retrieval step surfaced data the
generation step then repeated. This is a retrieval-scoping problem as much
as an output-filtering one: the fix belongs partly in section 1 (does the
retrieval query respect the requesting user's own access scope, not just
their tenant) and partly here (does anything downstream of retrieval
recognize and redact PII patterns before the response leaves the service),
and treating it as solved by output filtering alone misses the retrieval
half of the bug.

## 4. Abuse Prevention

An authenticated, rate-limited-within-normal-bounds caller can still be
extracting disproportionate value or degrading the service for others in
ways that per-request rate limits (section 2) do not catch, because each
individual request looks legitimate. What distinguishes abuse from normal
usage is the *pattern* across many requests, not any single one:

- **Query rate sustained well above the human-plausible ceiling** for the
  product surface in question -- a chat UI answering one message every few
  seconds around the clock is a different signal than the same rate on an
  API key with no UI in front of it at all, so the threshold has to be set
  per surface, not as one global number.
- **Query diversity/entropy as a scraping signal.** A caller issuing many
  small, systematically varied queries against a proprietary knowledge base
  (walking through a term list, an ID range, or an alphabet-by-alphabet
  sweep) looks like abuse even at a request rate that would pass a normal
  rate limit -- the tell is in the *shape* of the query sequence, not its
  speed. Tracking the entropy of the query stream per caller (are
  successive queries near-duplicates of each other, or do they look like a
  systematic sweep of the underlying corpus) catches an extraction pattern
  that a flat requests-per-second cap does not.
- **Cost-per-user outlier detection.** Track per-caller spend (tokens x
  price, the same `agent_llm_cost_dollars_total` metric `agent-observability`
  defines and `llm-cost-optimization`'s budget section assumes is already
  instrumented) as a distribution across the whole caller population, and
  flag outliers relative to that distribution rather than only against a
  fixed absolute cap -- a caller running 20x
  the median spend of comparable accounts is a signal worth a look even if
  it is still under whatever hard budget ceiling is configured, because the
  hard ceiling is a backstop against runaway cost, not a definition of
  normal usage.

The response to a detected abuse pattern does not have to be an immediate
hard block -- a step-up challenge, a tightened rate limit specifically for
that caller, or a flag for manual review are all proportionate first
responses, reserving an outright ban for a pattern that repeats after a
lighter intervention.

## Anti-patterns

- Building this skill's controls into an agentic system and assuming they
  cover tool-abuse or exfiltration risk -- they do not; that threat model
  is `ai-agent-security`'s, and an app with tool access needs both skills,
  not one instead of the other.
- Treating a request-size limit or a rate limiter as a substitute for
  prompt-injection detection, or vice versa -- they defend against
  unrelated failure modes and neither one covers the other's gap.
- A shared vector index or cache queried without a tenant filter applied
  at the client level, relying on every future call site to remember to
  add one -- the first debug tool or analytics job that queries directly
  is the leak.
- Caching an exact-match or semantic response keyed on prompt content alone
  in a multi-tenant app, omitting `tenant_id` from the key, so two tenants
  with an identical prompt receive each other's cached response.
- Treating a per-tenant rendered system prompt as safe to cache or log
  across tenants because "it's just a template" -- the rendered instance
  is tenant data the moment tenant-specific values are substituted into it.
- Skipping output-encoding on user input that gets echoed back in a UI on
  the reasoning that "it went through the LLM, so it's been processed" --
  the model call does not sanitize markup, and input that bypasses the
  model entirely (a stored, later-rendered field) is not processed at all.
- Running full content moderation as a second complete LLM call at the
  primary model's quality tier without checking whether a cheaper
  classifier or smaller model clears the accuracy bar for that specific
  policy check, silently doubling cost and latency for no quality gain.
- Relying on output PII filtering alone to catch a RAG pipeline that
  retrieved a record the current user should never have seen -- the bug is
  in retrieval scope, and output filtering only catches the shapes of PII
  it was built to recognize.
- Setting a single global rate limit and calling abuse prevention done --
  a scraping pattern (high query diversity, low per-request cost) and a
  cost-outlier pattern (low rate, high per-call cost) both slip under a
  rate-only threshold that was tuned for neither.
- Reaching for an outright ban as the first response to a detected abuse
  signal instead of a proportionate step-up (tighter limit, manual review
  flag), turning a false-positive detection into an unnecessary customer
  outage.
