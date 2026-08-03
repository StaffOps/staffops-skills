---
name: ai-pipeline-orchestration
description: "Run RAG index refresh and batch inference on Argo Workflows."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [ai, pipeline, orchestration, argo-workflows, rag, batch-inference, embeddings]
    category: ai
    related_skills: [argo-workflows-metrics, helm-chart-cronworkflow, llm-cost-optimization, agent-observability, llmops-platform-engineering]
---
# AI Pipeline Orchestration

How to structure multi-step AI/ML data pipelines -- RAG index refresh,
embedding generation, and batch LLM inference -- as Argo Workflows and
CronWorkflows on top of this catalog's existing GitOps stack, rather than
introducing a second, parallel orchestrator. It covers the DAG shape for a
safe index refresh (staging write, quality gate, blue-green swap), retry and
idempotency for batch inference against rate-limited LLM APIs, and how to
wire per-step LLM telemetry into signals that already exist. It deliberately
does not cover general Argo Workflows controller setup/troubleshooting, the
eval/promotion gate for shipping a pipeline change, or vector-store
operational mechanics -- each is either owned by an existing skill or, for
the two that are not, called out honestly as a gap below rather than
invented here.

## When to Use

Use when designing or debugging a scheduled pipeline that touches an LLM or
a vector store: a periodic RAG document ingestion/re-embedding job, a batch
inference job that scores or transforms a queue of inputs through a model,
or periodic fine-tuning data preparation. Not for one-off scripts run by
hand, and not for the request/response path of a live-serving agent or API
-- that is a synchronous call, not an orchestrated pipeline.

## This Org's Orchestration Engine Is Argo Workflows, Not a Python DAG Runner

This catalog has no Prefect, Airflow, or Dagster footprint anywhere --
`skills/apm-metrics/argo-workflows-metrics/SKILL.md` documents a deployed
Argo Workflows controller (Helm chart `argo/argo-workflows` v1.0.13,
appVersion v4.0.5, 2 replicas with leader election), and
`skills/infrastructure/helm-chart-cronworkflow/SKILL.md` documents the
corporate `cronworkflow/` Helm chart (version `0.5.0`) that every scheduled
batch job in this org already goes through, complete with mandatory
CostCenter/CostScope/CostProject labels, IRSA-based ServiceAccounts,
ExternalSecrets integration, and a `retryStrategy.limit` per step. An
AI-specific pipeline is not a special case that justifies a second
orchestration stack -- it is a CronWorkflow whose steps happen to call an
embedding model or an LLM API instead of a database or a REST endpoint.

Where a step needs more logic than a shell one-liner (chunking, embedding,
LLM calls, checkpoint bookkeeping), that logic lives in the step's container
image -- a Python or Go binary invoked as a Workflow step -- not in a
separate Prefect/Airflow/Dagster deployment running alongside Argo. Two
orchestration engines mean two schedulers, two sets of retry semantics, two
places drift can hide, and a GitOps story (`helmfile-applicationset`,
ArgoCD sync) that only covers one of them.

If your org genuinely does run a Python-native orchestrator for AI-specific
pipelines, that would show up in this catalog as a skill under
`skills/development/` or `skills/infrastructure/` -- none exists as of this
writing. Ground pipeline design in Argo Workflows/CronWorkflow until that
changes.

## RAG Index Refresh as a DAG

A periodic RAG refresh is not one step -- treat a partial failure mid-run as
the default case to design for, not an edge case, because it is the thing
that corrupts a live index if the pipeline mutates that index in place.

```
detect-changes -> chunk-and-embed -> write-to-staging-index -> quality-check -> swap-live
```

| Step | What it does | Failure mode it must not create |
|---|---|---|
| `detect-changes` | Diff current source documents against the last successful run's manifest (by hash, not mtime) | A missed diff silently drops a changed document from the refresh |
| `chunk-and-embed` | Chunk changed documents and generate embeddings | A crash partway through must not leave the *serving* index half-updated -- see staging, below |
| `write-to-staging-index` | Upsert chunks into a staging collection/index, never the one currently serving traffic | Writing directly to the live index means a crash here is visible to production reads immediately |
| `quality-check` | Run a small, fast regression check against the staging index (a fixed query set with expected top-k results, or a retrieval-quality score) before it goes live | Skipping this turns "a bad embedding batch" into "the production answer source" with no gate that caught it |
| `swap-live` | Flip a pointer/alias from the old live index to the staging one that just passed the quality check | Runs *only* if `quality-check` succeeded -- this is the blue-green swap, not an in-place mutation |

This is a **blue-green index swap**, not an in-place mutation, for the same
reason blue-green matters for any other serving artifact: the currently-live
index keeps serving unaffected traffic for the entire duration of the
refresh, and a failure anywhere before `swap-live` simply means the refresh
didn't complete -- it never means degraded or corrupted answers for whatever
is currently live.

Expressed against the `cronworkflow` chart's existing step model (the
sequential `steps` list with a `when` expression gating each step on the
previous step's status, shown in `helm-chart-cronworkflow`'s multi-step
example), the gate looks like:

```yaml
steps:
  - name: chunk-and-embed
    container:
      image: harbor.<org-domain>/<org>-images/rag-embed:a1b2c3d
      command: ["python", "/app/embed.py", "--target", "staging"]
      resources:
        requests: { cpu: 1000m, memory: 2Gi }
        limits: { cpu: 1000m, memory: 2Gi }

  - name: quality-check
    when: "{{steps.chunk-and-embed.status}} == Succeeded"
    container:
      image: harbor.<org-domain>/<org>-images/rag-quality-check:a1b2c3d
      command: ["python", "/app/check_staging_index.py"]
      resources:
        requests: { cpu: 250m, memory: 512Mi }
        limits: { cpu: 250m, memory: 512Mi }

  - name: swap-live
    when: "{{steps.quality-check.status}} == Succeeded"
    container:
      image: harbor.<org-domain>/<org>-images/rag-index-swap:a1b2c3d
      command: ["python", "/app/swap_alias.py"]
      resources:
        requests: { cpu: 100m, memory: 128Mi }
        limits: { cpu: 100m, memory: 128Mi }
```

`retryStrategy.limit` at the chart level retries a failed step from scratch
-- that is enough for a transient failure inside `chunk-and-embed` (a
timeout calling the embedding model), but it is not idempotency by itself.
Make `chunk-and-embed` itself resumable: key each write to the staging
index by document hash so a retried run upserts instead of duplicating, and
checkpoint which documents have already been embedded (a manifest file
alongside the chart's `ephemeralStorage` PVC, or a `processed` flag in the
staging store) so a retry after partial completion skips finished work
instead of re-embedding the whole batch and re-billing every token.

## Batch Inference Job Orchestration

A scheduled batch inference job -- pull a batch of inputs, call a model,
write results -- has the same shape as any other CronWorkflow step, with
two things that make LLM batch calls different from a typical batch job:
rate limits and idempotency across partial failure.

**Rate-limited batch APIs need backoff, not a fixed retry count.** The
`Batching` section of `llm-cost-optimization` covers *when* to use a
provider's batch API (non-interactive workloads, roughly half the per-token
price, results measured in hours not seconds) -- that's a cost decision,
not an orchestration one. Once you're on that path, the orchestration
concern is that batch submission and polling calls can still be
rate-limited: back off with jitter on a 429, honor a `Retry-After` header
when the provider sends one, and cap total retries so a persistent outage
fails the step instead of looping until `activeDeadlineSeconds` kills it
mid-poll.

**Idempotency means a rerun after partial failure does not double-process
completed items.** `retryStrategy.limit` restarts the whole step; without
application-level bookkeeping, a step that submitted a batch, processed
half the returned results, then crashed writing to the output store will --
on retry -- resubmit the entire batch and reprocess every already-completed
item, doubling both cost and (if writes aren't idempotent themselves)
duplicate output rows. Make the write side upsert-by-input-id rather than
append, and persist a manifest of completed input IDs the step checks
before resubmitting anything, the same checkpoint discipline as the RAG
refresh's document-hash bookkeeping above.

## Observability: Wire the Existing Signals Together

Don't invent a parallel telemetry story for these pipelines -- a CronWorkflow
step's container is still a normal workload, and two existing skills
already cover the two altitudes that matter here without needing to be
re-described:

- **Per-call LLM signal** (what one embedding call or one batch item cost,
  in tokens and dollars) is `agent-observability`'s job: the
  `agent_llm_tokens_total` and `agent_llm_cost_dollars_total` counters it
  defines apply exactly as-is to an embedding call inside `chunk-and-embed`
  or an LLM call inside a batch-inference step -- there is nothing
  pipeline-specific to add to that convention.
- **Orchestration-level health** (is the schedule actually firing, is a
  step failing, is the controller falling behind) is
  `argo-workflows-metrics`'s job: `argo_workflows_cronworkflows_triggered_total`
  confirms the refresh or batch job actually fired on schedule,
  `argo_workflows_gauge{phase="Failed"}` and `argo_workflows_pods_gauge{phase="Failed"}`
  surface a failing step, and `argo_workflows_queue_depth_gauge` shows
  whether the controller itself is keeping up if many pipelines run on
  overlapping schedules.

The thing that actually connects them: those per-step LLM cost/token
metrics only get enriched with the right cost attribution if the
CronWorkflow carries the mandatory `costCenter`/`costScope`/`costProject`
labels `helm-chart-cronworkflow` requires -- without them, the OTel
Collector's `k8sattributesprocessor` does not enrich telemetry for the
step's pods, and a perfectly-emitted `agent_llm_cost_dollars_total` series
still can't be attributed to the right team's budget.

## What This Does Not Cover

- **General Argo Workflows controller setup, workqueue tuning, or
  CronWorkflow triggering failures** -- that's `argo-workflows-metrics`
  (controller telemetry and troubleshooting) and `helm-chart-cronworkflow`
  (chart configuration, concurrency policy, IRSA, ExternalSecrets). This
  skill assumes both already exist and work; it only adds the AI-pipeline
  shape on top.
- **The eval/promotion gate for deciding a pipeline change is safe to
  ship** -- a new chunking strategy, a new embedding model, a changed
  quality-check threshold. That is `llmops-platform-engineering`'s job: the
  `quality-check` step referenced above is a narrow, pipeline-internal
  regression check, not a substitute for that broader CI/CD promotion
  methodology. Do not treat this skill as covering it.
- **Vector-store operational mechanics** -- index type selection, sharding,
  replication, backup/restore, or capacity planning for whatever store
  backs the staging/live indexes above. This catalog has no
  vector-database-ops skill of any kind; that gap is stated plainly here
  rather than papered over with invented guidance.

## Anti-patterns

- Standing up Prefect, Airflow, or Dagster for "AI pipelines" when Argo
  Workflows/CronWorkflow already exists, is GitOps-integrated, and already
  runs every other scheduled job in this org -- a second orchestration
  engine doubles the operational surface for no capability this one lacks.
- Mutating a live-serving vector index in place during a refresh instead of
  writing to a staging index and swapping only after a quality check
  passes -- a crash mid-refresh then corrupts production retrieval instead
  of simply failing to complete.
- Treating `retryStrategy.limit` alone as idempotency -- a retried step
  that re-embeds already-processed documents or resubmits an already-run
  batch wastes cost and, without upsert semantics on the write side, can
  duplicate index or output entries.
- Backing off a rate-limited batch API with a fixed retry count and no
  exponential backoff or jitter, turning a transient 429 into a longer
  self-inflicted outage.
- Skipping the quality-check step before `swap-live` because the refresh
  "usually works" -- the gate exists specifically for the run that doesn't.
- Missing `costCenter`/`costScope`/`costProject` labels on the
  CronWorkflow -- OTel enrichment silently fails and per-pipeline LLM cost
  becomes unattributable even though the metric itself is emitted correctly.
- Fabricating vector-database operational guidance or a promotion-gate
  skill this catalog doesn't have, instead of stating the gap honestly.
