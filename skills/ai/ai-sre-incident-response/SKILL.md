---
name: ai-sre-incident-response
description: "Detect and mitigate LLM quality, cost, safety incidents."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [ai, sre, incident-response, llm, quality-regression, cost-spike, safety-regression]
    category: ai
    related_skills: [incident-response-runbook, post-mortem-templates, agent-observability, agent-evals, ai-red-teaming, ai-agent-security, llmops-platform-engineering, ai-pipeline-orchestration, llm-cost-optimization, rag-observability-evals]
---
# AI SRE Incident Response

What is genuinely different about running an incident for an LLM-based
system, on top of `incident-response-runbook`'s existing roles, comms
cadence, and detect -> triage -> mitigate -> recover -> follow-up phases,
which this skill does not repeat and assumes run unchanged. It covers four
LLM-specific incident classes, why two of them often produce no clean
alert at all, how each maps onto the real SEV1-4 scale instead of a
parallel AI-specific one, three mitigations narrower and faster than a
full rollback, and how an LLM root cause slots into the existing
post-mortem cause taxonomy.

## When to Use

Use once an LLM-based service is suspected of being the incident, after
`incident-response-runbook`'s Phase 1 (Detect) and Phase 2 (Triage) are
already under way -- to classify which of the four incident classes below
applies, decide severity, and pick a mitigation. Reach for it specifically
when:

- The provider API or self-hosted endpoint is returning errors or timing
  out (briefly covered below, but this is an ordinary outage -- see
  `incident-response-runbook` for the actual playbook).
- The service is returning `200`s with normal latency, and the problem is
  that the *content* of the answers is wrong, off, or has quietly gotten
  worse -- no HTTP-status or error-rate panel will show this.
- Token/inference spend is climbing faster than traffic would explain.
- An agent did something it should not have been able to do -- called a
  tool it shouldn't have reached for, or a red-team-style bypass showed up
  in production instead of in a pre-launch test.

## The Four LLM Incident Classes

### (a) Hard outage

The provider API or self-hosted endpoint is down, timing out, or erroring
at volume. This is a normal availability incident with an unusually
well-known root cause (a dependency is unreachable) -- `incident-response-runbook`
already covers detection, roles, comms, and the mitigation table (rollback,
scale up, feature-flag off, restart, redirect traffic, hotfix, failover to
DR) without modification. Nothing about "it's an LLM" changes that
playbook; do not re-derive it here.

### (b) Quality degradation -- the genuinely novel class

The API is up, returning `200`s, latency is normal -- and the responses
are subtly worse: a silent model version change on the provider's side, a
prompt-template regression that shipped without a quality gate catching
it, or a RAG index that has gone stale relative to its source of truth
(`rag-observability-evals`'s failure mode 2). This is the incident class
with no HTTP-status signal at all, because "the service is technically
healthy" and "the service is doing its job" are two different claims for
an LLM in a way they mostly are not for a normal API. See "Detection"
below for how (and how imperfectly) this gets noticed.

### (c) Cost spike

A runaway agentic loop, a prompt-injection-induced tool-calling storm, or
a plain traffic surge multiplied by an expensive model tier. Detectable
in principle via `agent-observability`'s `agent_llm_cost_dollars_total`
counter (a Counter labeled `agent_name`/`model`, extending
`agent-platform-design`'s `agent_llm_tokens_total` convention) --
assuming that metric is actually wired up and someone is watching it or
alerting on it.

### (d) Safety regression

A red-team-caught-in-prod bypass: the agent reached for a tool, a scope,
or an unsafe output it should have been prevented from producing. This is
`ai-red-teaming`'s and `ai-agent-security`'s territory realized in
production instead of in a pre-launch test -- see "Mitigation" and the
severity table below for what that means once it's live traffic rather
than a controlled adversarial run.

## Detection: (b) and (d) Rarely Fire an Alert

An outage or a cost spike are the easy cases -- `up == 0` or a cost
counter crossing a threshold is unambiguous. Quality degradation and
safety regression are not: "the LLM started being wrong" and "the LLM
started doing something unsafe" usually have no clean automated signal,
and pretending one exists is worse than admitting it doesn't. Partial
signals that do exist, roughly most-trustworthy first:

- **A continuously-run eval suite regressing.** If `agent-evals`'s
  golden-dataset suite (`skill-eval-harness`'s five-weighted-dimension
  score, or a new `blocker: true` row) runs on a schedule against
  production or canary traffic -- not only as `llmops-platform-engineering`'s
  pre-merge CI gate -- a drop in score is the closest thing this incident
  class gets to a real alert. Most teams only run it pre-merge, which
  catches a regression that shipped through the pipeline but misses one
  that appears later: a provider-side model update, or an index going
  stale between scheduled refreshes.
- **A groundedness/retrieval-quality gauge in production**, if the team
  built one per `rag-observability-evals`'s "Emitting RAG Quality as
  Telemetry" section. Absence of this signal firing is not evidence the
  regression didn't happen -- most teams have not built it.
- **A spike in user-reported "this answer is wrong" feedback**, if that
  channel exists at all. Treat it as corroborating, not conclusive, on its
  own -- a spike can just as easily mean a bug in the feedback widget.
- **A spike in a specific tool being called far more than its baseline
  rate.** Useful for both (b) and (d): for quality, it can mean the agent
  is looping or reaching for the wrong tool because retrieved context or a
  prompt changed underneath it; for safety, it is exactly the pattern
  `ai-agent-security` names -- "an agent with a capability will eventually
  use it" -- and a sudden spike in a destructive-tier tool's call rate
  deserves the same scrutiny as a fired guardrail alert, even where no
  alert is actually configured for it.
- **A human noticing something felt off.** Name this as a legitimate
  detection path, not a process failure -- `incident-response-runbook`'s
  "team observation" detection source already covers exactly this. A
  senior engineer or support agent reading a handful of transcripts and
  noticing a pattern is a common, real way these incidents get found.
  Declare the incident on that basis; do not wait for a metric to confirm
  what a human already saw repeatedly.

## Severity Mapping onto the Real SEV1-4 Scale

Reuse `incident-response-runbook`'s severity definitions and decision tree
exactly as written -- do not invent a parallel AI-specific severity
scheme. The only wrinkle for an LLM incident is that "customer-visible
impact" is not always an HTTP status; it can be a wrong answer, a policy
violation, or spend nobody signed off on.

| Class | Default severity | Concrete criteria |
|---|---|---|
| (a) Outage | SEV1 or SEV2, unmodified | `incident-response-runbook`'s decision tree applies as-is: customers unable to use the service -> SEV1; degraded but functional (e.g. a fallback model is serving) -> SEV2. |
| (b) Quality degradation | SEV1 through SEV3, driven by what the wrong answer costs, not by any status code | **SEV1** if degraded/wrong answers are reaching customers at volume and could plausibly cause financial, safety, or compliance harm (a support agent confidently misinforming customers; a code-gen agent shipping wrong fixes at scale) -- this is SEV1's "revenue impact, data loss risk" bar, just triggered by content instead of downtime. **SEV2** if bounded -- one route, low traffic, a known workaround (revert the last prompt/model change) stops it -- matching SEV2's "degraded service, partial impact." **SEV3** if internal-only (an internal tool, a low-traffic eval-only route) with no customer visibility. |
| (c) Cost spike | SEV3 by default; SEV2 on financial materiality alone, SEV1 only if a hard stop causes an outage | **SEV3** matches its bar exactly: internal impact, workaround exists (apply a cap), no customer visibility. **Escalate to SEV2** if the burn rate represents material unbudgeted financial exposure worth paging a lead over even absent customer impact -- any responder can upgrade severity per `incident-response-runbook`'s escalation rule, no approval needed. **Escalate to SEV1** only if a budget-exhaustion hard stop trips and that stop itself takes down customer-facing traffic -- at that point it *is* class (a), a customer-facing outage, not a cost incident anymore. |
| (d) Safety regression | SEV1 by default whenever it reached live traffic | Treat any confirmed bypass that reached a real, non-test session as SEV1 minimum -- it fits SEV1's own "data loss risk"/compliance-risk criterion, and mirrors `ai-red-teaming`'s scoring posture that a single successful bypass is a finding, not something to average down. Only the IC downgrades, with justification (unchanged rule) -- e.g. the bypass was contained by a blast-radius gate (`ai-agent-security`) before it could act, so no actual harm occurred. A bypass caught by a red-team regression run or an eval gate *before* it reaches production traffic is not an incident at all -- it is a routed red-team finding per `ai-red-teaming`'s routing table, handled as an ordinary fix, not paged. |

## Mitigation: Reach for the Narrowest Thing Before a Full Rollback

`incident-response-runbook`'s Phase 3 table already orders mitigations by
speed and (mostly inversely) risk: rollback, scale up, feature-flag off,
restart pods, redirect traffic, hotfix, failover to DR. Three LLM-specific
options sit ahead of a full application rollback in that same ordering,
because each targets exactly the layer that broke instead of the whole
deployment.

### 1. Roll back the prompt/model version specifically

Per `llmops-platform-engineering`, a prompt or model version is a
deployable artifact riding the existing ArgoCD/Argo Rollouts pipeline, so
"roll back the prompt" is the same Git-revert-plus-sync mechanism as any
other rollback -- but it needs two things a code rollback does not:

- **Cache invalidation keyed by version.** If the version being rolled
  back *from* produced actively wrong output (not merely a stylistic
  regression), purge its cache entries rather than letting them expire on
  the normal TTL -- `llmops-platform-engineering` cites `llm-caching`'s
  version-keyed cache convention (`model_id_with_version`) as exactly what
  makes this a targeted purge instead of a full cache flush.
- **In-flight sessions pinned to the old version.** A multi-turn
  conversation that started under the bad version can otherwise have its
  next turn silently land on whatever version is now current post-rollback,
  producing a persona shift or a contradiction mid-conversation. If the
  serving path pins a session to the version that served its first turn,
  a rollback for *new* sessions doesn't destabilize sessions already in
  flight.

### 2. Disable the specific tool, not the whole agent

If the quality or safety problem traces to one tool -- a tool call
looping, a tool returning bad data, a bypass exercising one specific
capability -- disable that tool's grant rather than taking the whole
agent offline. This is `ai-agent-security`'s blast-radius framing applied
under incident pressure: a tool sits at some blast-radius tier already
(none/reversible through irreversible), and pulling the one tool at the
tier the incident implicates is a narrower, faster action than a full
service restart or rollback, with a correspondingly smaller blast radius
of its own.

### 3. Fall back to the previous-known-good RAG index

If the root cause is class (b) via a stale or bad index refresh, the fix
is not a code or prompt rollback at all -- it's flipping the same
pointer/alias `ai-pipeline-orchestration`'s blue-green index-swap pattern
already uses (`detect-changes -> chunk-and-embed -> write-to-staging-index
-> quality-check -> swap-live`) back to the previous live index. Because
the prior index was never mutated in place, this is a pointer flip, not a
data restore -- one of the fastest options in this whole list.

### Cost incidents: the budget gate, not a rollback

A cost spike's mitigation is rarely a rollback at all -- it's tripping the
hard stop `llm-cost-optimization`'s budget section describes: a
per-request or per-session cost ceiling checked *before* the call goes
out, and a rolling-window spend threshold that halts or falls back to a
cheaper path once crossed. If that gate exists, "mitigate" means confirming
it fired and possibly lowering the threshold further; if it doesn't exist,
the incident's own mitigation is standing one up under pressure -- a
dashboard or a post-hoc Slack alert is not a control, per that skill,
because it only tells you what already happened.

## Post-Mortem: Slotting LLM Root Causes into the Existing Taxonomy

`post-mortem-templates`'s fishbone categories -- Code, Config, Infra,
Deploy, Capacity, Dependency -- have no "AI" bucket, and should not get
one; a seventh category fragments this catalog's post-mortem process for
no benefit. The three LLM-specific root causes this skill's incident
classes tend to produce all map onto categories that already exist:

| LLM root cause | Existing category | Why |
|---|---|---|
| Model provider silently changed underlying behavior | **Dependency** | Same shape as "Third-party API timeout" or "AWS service degradation" already listed under Dependency -- an upstream service changed behavior outside this org's control or notice. |
| Prompt-template regression shipped without an adequate eval gate | **Deploy** | Per `llmops-platform-engineering` section 1, a prompt is a deployable artifact riding the same Rollout as any other change -- a prompt regression that reached prod is "Bad rollout (no canary)" or a missing/weak eval gate, already listed under Deployment. |
| RAG index went stale relative to its source of truth | **Dependency** (usually), or **Deploy** if the root cause was the refresh job itself failing to run | Treat the index as an upstream data dependency the serving path relies on when the source-of-truth data changed and the refresh didn't catch up in time; treat it as Deployment specifically when the failure was the `ai-pipeline-orchestration` refresh pipeline itself (a broken CronWorkflow schedule, a quality-check that should have blocked `swap-live` and didn't). |

Fill in the rest of the template unchanged -- Timeline, Impact (including
SLO burn if one is tracked), 5 Whys, Action Items with owners and Jira
tickets. The only adaptation is which existing category the 5 Whys lands
on; everything else about `post-mortem-templates`'s process (blameless
language, review meeting, action-item tracking) applies without
modification.

## Anti-patterns

- Inventing a parallel AI-specific severity scale instead of mapping onto
  `incident-response-runbook`'s real SEV1-4 -- two severity systems for
  the same organization means responders have to remember which one
  applies to which incident, exactly when they have the least time to.
- Treating "there's no alert for quality/safety regressions" as an excuse
  not to look for them -- name the partial signals that exist, and accept
  that a human noticing something felt off is a legitimate detection path,
  not a process gap to be embarrassed about.
- Reaching for a full application rollback before checking whether the
  narrower fix (prompt/model version rollback, disabling one tool, an
  index pointer flip) actually addresses the root cause -- all three are
  faster and smaller in blast radius than a full rollback when the
  incident is scoped to one layer.
- Rolling back a prompt/model version and stopping there, without checking
  whether a version-keyed cache still holds actively-wrong entries, or
  whether an in-flight session is still pinned to the version being
  rolled back from.
- Adding a seventh "AI" category to the post-mortem cause taxonomy instead
  of mapping a model-provider change, a prompt regression, or an index
  staleness issue onto the existing Dependency/Deployment categories.
- Treating a cost spike caught and stopped by a budget gate before it
  became customer-visible as automatically SEV3 regardless of the dollar
  amount involved -- a large enough burn rate is worth escalating on
  financial materiality alone, the same way any responder can upgrade
  severity for any other incident class.
- Paging on a bypass that a red-team regression run or a pre-promotion
  eval gate already caught before it reached production traffic -- that
  is a routed finding handled as an ordinary fix (`ai-red-teaming`'s
  routing table), not a live incident.
- Downgrading a confirmed-live safety bypass below SEV1 without the IC's
  explicit justification -- the same rule that already applies to any
  other severity downgrade in `incident-response-runbook`.
