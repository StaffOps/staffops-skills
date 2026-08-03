---
name: llmops-platform-engineering
description: "Gate LLM prompt/model promotion with evals and rollback."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [ai, llmops, ci-cd, progressive-delivery, prompt-versioning, rollback, governance]
    category: ai
    related_skills: [agent-evals, ai-red-teaming, llm-caching, ai-agent-security, argocd-patterns, argo-rollouts-metrics, helm-chart-app, pipeline-template-apps, gitops-environment-onboard, model-registry-governance]
---
# LLMOps Platform Engineering

CI/CD and progressive-delivery patterns for shipping a change to a prompt,
a model version, or an agent's tool set, built entirely on this catalog's
existing ArgoCD/Argo Rollouts pipeline rather than a bespoke deployment
mechanism for "AI stuff." It covers what promotion, the eval gate, rollback,
and approval mean specifically for an LLM change, and where each of those
already has a real primitive in this catalog to reuse. It deliberately does
not cover general CI/CD pipeline setup, general GitOps service onboarding,
or model training/registry mechanics -- see "What This Skill Deliberately
Does Not Cover" below for where each of those actually lives.

## When to Use

- Promoting a prompt, model version, or tool-set change through
  dev -> staging -> prod, or canary-by-traffic-percentage within an
  environment
- Deciding how an eval suite becomes an actual pipeline gate instead of a
  step someone might forget to run before merging
- Planning what a rollback of a prompt/model change needs beyond reverting
  a Git commit
- Deciding who has to approve a prompt or tool-set change before it reaches
  production, and how that approval is mechanically enforced rather than
  just agreed to in a PR description

## What This Skill Deliberately Does Not Cover

- **General CI/CD pipeline setup** -- stage layout, image tagging, dual-arch
  builds, cosign signing -- is `pipeline-template-apps`'s job. This skill
  only adds the LLM-specific stage (the eval gate) on top of that existing
  stage list.
- **General GitOps service onboarding** -- registering a service in an
  ApplicationSet, creating its `*-environments/` directory, wiring
  ExternalSecrets and IRSA -- is `gitops-environment-onboard`'s 4-step
  workflow. A service that already went through that workflow is the
  prerequisite for everything below; this skill does not repeat it.
- **Model training and registry mechanics** -- how a trained model artifact
  is versioned, stored, and tracked for lineage -- is `model-registry-governance`'s
  job, a separate concern from promoting a version that already exists and
  is ready to serve. This skill starts at "a specific prompt or model
  version is ready to move from one environment to the next"; that skill
  covers what the registry entry for that version must already record
  before this skill's promotion flow is allowed to reference it.

## 1. A prompt/model/tool-set change is a deployable artifact -- promotion reuses the existing Rollout, not a parallel mechanism

`helm-chart-app` already treats `deploymentType: Rollout` with
`strategy: Canary` as the default for API services, and `argocd-patterns`'
Git-directory-generator pattern already treats a commit to a service's
`*-environments/` directory as the trigger for an ArgoCD sync followed by a
canary progression -- `gitops-environment-onboard` documents exactly this
flow for a container image tag update (`yq -i '.image.tag = ...'`, commit,
push, ArgoCD detects and syncs). Nothing about that mechanism cares whether
the new revision changes the container image or changes a prompt template
ID, a model version string, or a tool-set flag baked into the same pod spec
as an env var or ConfigMap key -- either one changes the pod template hash
and the Rollout controller treats it as a new revision to canary through
the same weighted steps, observable via `argo-rollouts-metrics`'
`rollout_info` gauge (`weight` label) and `rollout_phase`
(`Progressing`/`Healthy`/`Degraded`/`Paused`).

Concretely, "promotion" for an LLM change is the same three-tier flow this
catalog already uses for anything else:

- **dev -> hml -> prd** is the same three separate `*-environments/`
  directories `gitops-environment-onboard` already structures per service
  (`dev/<service>/values.yaml`, `prd/<service>/values.yaml`, and a `btc/`
  directory only for batch workloads) -- the value that changes per
  promotion is the pinned prompt/model identifier, not the mechanism
  moving it forward.
- **Canary-by-traffic-percentage** within an environment is the Rollout's
  own weighted steps acting on the pod running the new prompt/model
  config -- the same primitive `helm-chart-app`'s `strategy: Canary`
  already provides for a code deploy, not a separate A/B-testing layer
  built outside the GitOps pipeline.

If the prompt/model version is baked into the image at build time (the
image is rebuilt on every prompt change), promoting it is literally the
image-tag-update deploy stage `pipeline-template-apps` already documents.
If it is an external value decoupled from the image (a prompt template ID
or model version string read from an env var or ConfigMap at startup),
commit that value to the environments repo the same way -- it still changes
the pod template hash, so the Rollout still canaries it through the normal
steps. Do not build a second, LLM-specific traffic-splitting layer for this;
the mesh and the Rollout controller already do percentage-based routing for
any workload in this environment.

## 2. The eval gate as the actual promotion criterion -- a CI job, not a step someone might skip

`agent-evals` and its underlying `skill-eval-harness` own the methodology
(golden datasets, the five-weighted-dimension rubric, the paired
baseline/candidate release gate); this skill's only addition is the
CI-wiring angle: turning that gate into a pipeline stage a merge cannot get
past, rather than a check a human is trusted to run before opening the MR.
`skill-eval-harness`'s own `score` subcommand already returns exit code `0`
when the release gate passes (no `blocker: true` row, `correctness` and
`safety` each within 0.1 of baseline, weighted score strictly higher) and
`1` otherwise -- that exit code *is* the gate, with no extra glue script
needed to interpret pass/fail. Add it as a job inside the existing `test`
stage from the stage list `pipeline-template-apps` already defines
(`release_notes -> pre-build -> build -> test -> review -> deploy ->
rollback`) -- it runs alongside, not instead of, whatever unit/integration
tests already live there:

```yaml
eval-gate:
  stage: test
  script:
    - python3 skills/workflows/skill-eval-harness/scripts/eval_harness.py score
        evals/results/scores.jsonl
  rules:
    - if: $CI_COMMIT_BRANCH =~ /^(homologation|production)$/
```

A non-passing gate fails the job the same way a failing unit test does --
the merge cannot reach the `deploy` stage, the same enforcement
`pipeline-template-apps` already relies on for its `pre-build` security
scans (gitleaks, trivy) being unskippable rather than a checklist item.

For a change that touches safety-relevant behavior -- expanding the tools
an agent can call, changing a system-level instruction, or swapping the
underlying model -- also run `ai-red-teaming`'s attack catalog through the
same harness as a required stage before promotion continues, not only the
quality suite. `ai-red-teaming` already treats a single successful bypass
as a blocking finding rather than noise to average into a score, which is
exactly the posture a safety-relevant change needs and a quality-only eval
gate does not provide on its own. Which changes actually require this
second stage is the same blast-radius question governance answers in
section 4 below -- treat it as the gate corresponding to the higher tier,
not a suite that runs on every change regardless of what it touches.

## 3. Rollback for an LLM change -- the Git revert plus two things a code rollback does not need

The Git-and-ArgoCD half of a rollback is identical to any other GitOps
rollback: revert the environments-repo commit (or run the manual
`rollback` stage `pipeline-template-apps` already defines, pointing the
pinned prompt/model value back at the previous commit's value), ArgoCD
syncs, the Rollout reverts to the previous revision. Two things beyond that
are specific to an LLM change and do not show up in a code rollback:

**Cache invalidation keyed by version.** `llm-caching`'s cache-key
convention already includes the exact model identifier and version
(`model_id_with_version`) precisely so a model upgrade invalidates the
right entries without a manual purge -- that same convention extends to a
prompt template ID or a tool-schema version per its Invalidation section
("version the tool/function-calling schema the same way you version the
model"). Because entries are keyed by exact version, requests naturally
resume hitting the *old* version's still-valid cache entries the moment
traffic routes back to it -- nothing needs to be repopulated. What does
need explicit action: if the version being rolled back *from* produced
actively wrong output (an unsafe tool-call decision, not merely a stylistic
regression), purge its entries rather than letting them expire on their own
TTL -- a client that still references that version tag (a bug, a stale
client cache, a pinned session per below) can otherwise keep being served a
known-bad cached decision until the TTL catches up on its own schedule.
Also confirm any semantic-cache lookup (`llm-caching` Layer 2) is filtered
by model/prompt version, not just similarity, so a rollback's transition
window cannot surface a semantically-similar entry generated by the version
being rolled back from.

**In-flight conversations that started under the old version.** A
multi-turn conversation whose first turn was served by version N can have
its second turn land after a rollback or a canary promotion moved current
traffic to version N-1 or N+1. If nothing pins which version served a given
session, later turns silently switch prompt/model version mid-conversation
-- producing a persona shift, a forgotten tool result, or a contradiction
with what the model itself said two turns earlier. This is an
application-level concern, not something the Rollout's traffic weighting
can solve on its own: relying on the old ReplicaSet staying reachable until
every in-flight session finishes assumes the deployment can only serve one
version at a time. The more robust fix is to make the serving deployment
capable of selecting a prompt/model version from a request-time parameter
(store the version alongside session state at turn one, pass it on every
subsequent turn of that session) so a session started under version N keeps
using version N regardless of what the Rollout is currently promoting or
rolling back to for *new* sessions.

## 4. Governance -- blast radius decides the approval tier, and the approval gate is a real primitive already in this catalog

`ai-agent-security`'s blast-radius table (None/reversible through
Irreversible, with friction scaling per tier) is the framing to apply here
directly, not a parallel governance scheme: a prompt change that only
rewords a response sits at its Low/Medium tier (auto-progressing canary
with the quality eval gate from section 2 is enough friction); a prompt or
tool-set change that expands what tools an agent can call, changes a
system-level instruction, or swaps the underlying model sits at its
High tier -- "explicit confirmation naming the exact action, plus a stated
rollback path" -- and needs a human approval step the automated gate alone
does not provide.

The mechanical approval gate for that High tier is already documented in
this catalog, not something to invent: `argocd-patterns` explicitly
recommends manual sync (omitting the `automated` block from `syncPolicy`)
for "resources that need human verification before apply" and
"infrastructure changes with high blast radius" -- apply that same pattern
to the environments-repo entry carrying a safety-relevant prompt/tool-set
change, so `selfHeal`/auto-sync cannot promote it unattended and a human
must run `argocd app sync` after review. `argo-rollouts-metrics` confirms
`Paused` as an observable `rollout_phase` value, so the approver (and
anyone watching the rollout) can see the change sitting at a held state
rather than having to infer that a gate exists. Pair that with a
`when: manual` CI job ahead of the `deploy` stage -- the same shape
`pipeline-template-apps` already uses for its manual `rollback` stage -- so
the eval gate clearing (section 2) is necessary but not sufficient on its
own for a High-tier change: the pipeline still stops and waits for an
explicit human trigger before the manual-sync Application is told to
proceed.

## Anti-patterns

- Building a parallel traffic-splitting or version-routing layer for
  prompt/model changes instead of riding the existing Rollout canary steps
  and ArgoCD environments-repo flow this catalog already runs every other
  deploy through.
- Treating the eval suite as a checklist item a human is trusted to run
  before opening the MR, instead of a CI stage whose exit code (`score`'s
  own release-gate result) blocks the pipeline.
- Running only the quality eval gate for a change that expands tool access
  or swaps the model, skipping `ai-red-teaming`'s adversarial pass because
  the quality suite already passed.
- Treating a Git revert as a complete rollback without checking whether a
  version-keyed cache still holds actively-wrong entries from the version
  being rolled back from, or whether any in-flight session is still pinned
  to it.
- Assuming the old ReplicaSet staying up during a canary is sufficient to
  keep in-flight conversations consistent, instead of pinning the served
  version at the session/request level.
- Letting `selfHeal`/auto-sync promote a safety-relevant, tool-access-
  expanding prompt change unattended, the same mistake this catalog already
  flags for any other high-blast-radius infrastructure change.
- Applying the same governance tier (and the same approval friction) to
  every prompt change regardless of blast radius -- gating a wording-only
  tweak as heavily as a tool-access expansion just trains reviewers to
  click through the approval without reading it.
