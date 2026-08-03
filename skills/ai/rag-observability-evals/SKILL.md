---
name: rag-observability-evals
description: "Measure RAG retrieval quality and answer groundedness."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [ai, rag, retrieval, groundedness, hallucination, eval, faithfulness]
    category: ai
    related_skills: [agent-evals, skill-eval-harness, agent-observability, ai-pipeline-orchestration]
---
# RAG Observability and Evals

Quality measurement specific to retrieval-augmented generation: whether the
retrieved chunks were the right ones, and whether the generated answer's
claims actually trace back to them. This is a narrower, harder-to-measure
surface than general agent correctness -- `agent-evals` covers whether an
agent's overall response is right; this skill covers the retrieval step
underneath it, where "right" splits into "found the right context" and
"only said what the context supports," and either can fail while the other
looks fine. It deliberately does not cover vector-database operational
mechanics, general agent quality eval, or embedding-model selection -- see
"What This Skill Deliberately Does Not Cover" below.

## When to Use

- Shipping a change to a RAG pipeline's retriever, chunking strategy, top-k,
  reranker, or prompt template, where "did retrieval quality or groundedness
  regress" cannot be answered by reading the diff or eyeballing a few
  outputs.
- A RAG system has produced a confident-sounding wrong answer at least once,
  and the question is which stage failed: retrieval found nothing useful, or
  retrieval found something useful and generation still went off it.
- Building a regression suite for a RAG-backed skill or agent capability and
  needing cases that specifically exercise retrieval and groundedness, not
  just the final-answer-correctness cases `agent-evals` already covers.
- Not for evaluating whether an agent's tool-calling loop or overall task
  completion is correct when no retrieval step is involved -- that is
  `agent-evals`'s general case, and forcing it through a RAG-specific lens
  adds nothing.

## Retrieval Quality: Precision and Recall Against a Labeled Relevant Set

The textbook version of retrieval quality is precision/recall (or
rank-aware variants like MRR) computed against a labeled relevant-set: for
query Q, someone has already decided which chunks in the index are actually
relevant, and you measure how many of those the retriever surfaced in its
top-k. "Relevant" here means the same thing `agent-evals` means by a golden
dataset's expected behavior -- not a synthetic edge case engineered to be
hard, but a judgment representative of how the corpus is actually queried.
Building that labeled set is the same sourcing problem `agent-evals` already
solves for golden datasets, and it does not need re-deriving here: sample
real queries and redact them the same way, or hand-author cases for the
scenario shapes `agent-evals` names (the ordinary case, the frequent-but-
boring case, a specific regression that already happened once). Reuse that
guidance rather than inventing a parallel one for RAG.

**The honest complication**: most teams evaluating a RAG system do not have
a hand-labeled relevant-set, and building one for every corpus change is
expensive enough that it rarely stays current. When there is no labeled
relevant-set, the practical fallback is an indirect proxy rather than true
recall: **did the final answer's grounding citations point back to a chunk
that was actually retrieved**. This does not measure whether retrieval found
everything relevant -- it only measures whether generation used what it was
given honestly -- but it is cheap to compute from data the pipeline already
produces (the retrieved chunk IDs and whatever citation markers the
generation step emits), and it catches a real, common failure: retrieval
did its job, generation cited a chunk that was never in the retrieved set
(a fabricated citation, not a grounded one). Be explicit in any report about
which measurement you are using -- a citation-grounding proxy is not a
substitute for recall@k against real relevance judgments, and reporting one
as if it were the other overstates confidence in retrieval quality
specifically.

## Groundedness and Faithfulness: Does Each Claim Trace to a Retrieved Chunk

Groundedness (also called faithfulness) asks a different question from
retrieval quality: given the context that *was* retrieved, does the
generated answer only say things that context supports, or does it add
claims the model supplied from its own training data instead? A retriever
can do a perfect job and generation can still hallucinate on top of good
context -- these are independent failure surfaces and a regression in one
does not imply a regression in the other.

A concrete, checkable version of groundedness -- imperfect, but better than
an unstructured "does this look right" read -- is a **claim-by-claim
entailment check**: split the answer into individual claims (roughly, one
per sentence), and for each claim ask whether at least one retrieved chunk
supports it. A claim with no supporting chunk is either an outright
hallucination or an inference the model made beyond what it was actually
given -- both are groundedness failures even if the inference happens to be
correct, because "happened to guess right" is not what grounded generation
is supposed to guarantee. The check can be as simple as: for each sentence
in the answer, does at least one retrieved chunk contain the fact or a
paraphrase of it. It gets more rigorous (and more expensive) as an
LLM-as-judge entailment classification per claim, but the sentence-level
manual version is a real starting point, not a strawman -- it is usually
enough to catch the failure that matters, which is an answer confidently
stating something no retrieved chunk said at all.

**Be honest that this is not a solved measurement.** Claim segmentation is
ambiguous (where does one claim end and the next begin), paraphrase
detection has false negatives (a chunk supports the claim but doesn't share
enough surface vocabulary for a shallow check to notice), and an LLM judge
doing the entailment check inherits its own reliability problems --
inconsistent verdicts across runs, sensitivity to how the check is prompted.
Groundedness scoring is a genuinely useful signal for catching gross
hallucination and for regression-testing a specific pipeline change; it is
not a precise, reproducible ground truth the way a unit test assertion is.
Report it with that caveat rather than as a clean percentage that implies
more certainty than the method has.

## RAG-Specific Failure Modes to Test For

Three failure shapes are worth deliberately covering in any RAG eval suite,
because each one produces a *different* symptom and needs a *different*
fix -- collapsing them into one "RAG quality" score hides which stage
actually broke:

1. **Retrieval returns nothing relevant, and the system still generates a
   confident-sounding answer instead of saying so.** This is the failure
   this skill weights most heavily, because it is the one users experience
   as "the bot lied to me" rather than "the bot didn't know" -- a low-
   confidence retrieval (low similarity scores, or a near-empty top-k) that
   still gets synthesized into a fluent, unhedged answer is worse than an
   honest "I don't have information on that in the indexed context." Test
   for this by feeding a query the corpus genuinely does not cover and
   checking whether the system abstains or hedges instead of inventing an
   answer that reads as if it came from real context.
2. **Retrieval returns stale, outdated chunks** -- the index has not
   caught up with a source-of-truth change, so the retriever confidently
   returns chunks that were correct once and are wrong now. This is an
   index-freshness problem, not a retrieval-ranking problem; no amount of
   reranking or top-k tuning fixes a chunk that is simply out of date.
   `ai-pipeline-orchestration` owns the mechanical fix -- a blue-green index
   refresh (`detect-changes -> chunk-and-embed -> write-to-staging-index ->
   quality-check -> swap-live`) that never lets a partial or bad refresh
   reach the live index -- and its own `quality-check` step is exactly where
   this skill's retrieval-quality signal plugs in: score a fixed query set
   against the staging index, using the recall/precision-against-labeled-set
   (or citation-grounding proxy) method above, before `swap-live` runs. This
   skill's job at this failure mode is narrower than the pipeline fix:
   detect that staleness happened at all -- does the retrieved chunk match
   the current source of truth, not merely what the index currently
   contains -- and feed that signal into the gate `ai-pipeline-orchestration`
   already defines, rather than re-describing the refresh mechanics here.
3. **Retrieval returns relevant-but-insufficient context, and generation
   synthesizes a plausible-but-wrong answer by filling the gap.** This is
   the subtlest of the three: the retrieved chunks are genuinely on-topic
   (a groundedness check would find real support for parts of the answer),
   but they don't contain enough to fully answer the question, and
   generation bridges the gap with an inference that sounds consistent with
   the retrieved material without actually being stated in it. A groundedness
   check catches this only if it is granular enough to flag the specific
   unsupported claim rather than approving the answer because most of it
   traces back correctly -- this is why claim-by-claim checking matters more
   than a single whole-answer verdict.

## Wiring a RAG Case Into the Eval Harness

`agent-evals` already establishes how to encode a golden-dataset case in
`skill-eval-harness`'s exact schema (`references/case-schema.md`) --
reuse that mechanism rather than building a second, RAG-specific runner. The
differentiator for a RAG case is not the file format, which is identical,
but the `criteria`: a general case's criteria check whether the final answer
is correct; a RAG case's criteria should specifically check retrieval
honesty and citation grounding, so a candidate that gets the "vibe" of the
answer right while fabricating a claim still fails.

A worked example encoding failure mode 1 above (retrieval returns nothing
relevant, system should abstain rather than hallucinate):

```json
{"id": "rag-empty-retrieval-confident-hallucination", "category": "rag-groundedness", "prompt": "Retrieved context (top-3 chunks from the API docs index, cosine similarity in parentheses):\n[Chunk 1, score 0.31] \"Billing cycles run monthly; invoices are generated on the first business day.\"\n[Chunk 2, score 0.29] \"Rate limits reset every 60 seconds per API key.\"\n[Chunk 3, score 0.27] \"Support tickets are triaged within 4 business hours.\"\n\nUser question: \"What is the maximum batch size for the /v2/bulk-import endpoint?\"\n\nAnswer the user's question using only the retrieved context above.", "risk": "high", "criteria": ["States that the retrieved context does not contain information about the /v2/bulk-import endpoint's batch size, instead of inventing a specific number.", "Does not synthesize a plausible-sounding batch size limit from general API knowledge that is not present in the retrieved chunks.", "Recommends a concrete next step (re-querying the index with different terms, checking the endpoint's own reference page, escalating) rather than a bare refusal with no path forward.", "Every claim made about the endpoint traces to one of the three retrieved chunks; since none of the three chunks address batch size, the answer says so explicitly rather than citing an unrelated chunk as if it supported the claim."]}
```

Note what makes this a RAG case and not a generic one: the low similarity
scores (0.31, 0.29, 0.27) in the prompt itself are the signal that retrieval
came up empty on-topic, and every `criteria` entry is about whether the
answer respects that -- not "is 500 items the right batch size," which
would be the wrong question entirely here (the point of this case is that
no retrieved chunk answers it at all).

Validated against the harness's real schema check, run from the repository
root against a single-line file containing exactly the case above:

```bash
python3 skills/workflows/skill-eval-harness/scripts/eval_harness.py validate --cases /tmp/rag-observability-evals-worked-example.jsonl
```

```
WARNING: Every case shares category 'rag-groundedness' — a single-category catalog cannot reveal category-specific regressions.
1 case(s) are valid.
```

Because this single case is already tagged `risk: "high"`, the harness's
missing-high-risk-coverage check is satisfied and does not fire here (it
does fire in `agent-evals`'s own worked example, whose illustration case is
`medium` risk) -- the category-coverage warning still fires, exactly as
expected for a single-case file: a real suite built from this pattern needs
sibling cases across more categories (one per failure mode above, at
minimum) before it earns being relied on as a release gate.

## Emitting RAG Quality as Telemetry, Not Just a Release Gate

Everything above answers "did this change make retrieval or groundedness
better or worse," a pre-merge question the eval harness settles offline. If a
team also wants continuous, per-request retrieval/groundedness signal in a
production dashboard, that becomes a metric-emission concern subject to the
exact same rules `agent-observability` already establishes for LLM-call
telemetry: keep any label set low-cardinality (a route or index name is
fine; a query, document ID, or conversation ID is not), and never put
prompt, completion, or retrieved-chunk content on a metric label -- if you
need to see which specific query scored low, that belongs in a trace
attribute or a log line, not a metric, for the same reason
`agent-observability` gives for cost and token labels. This skill does not
re-derive that guidance; it only flags that a groundedness or retrieval
gauge is subject to it the moment it leaves an offline eval run and becomes
a running counter or gauge in production.

## What This Skill Deliberately Does Not Cover

- **Vector-database operational mechanics** -- index sizing, connection
  pooling, HNSW/IVF tuning, sharding a vector store. There is no skill in
  this catalog covering that yet (confirmed by searching `skills/` for
  `vector` directly rather than assuming coverage exists); this skill treats
  the vector store as a black box that returns chunks, and evaluates what
  comes out of it, not how it is operated.
- **General agent quality evaluation** -- whether an agent's overall
  response to a task is correct, autonomous, and actionable, independent of
  whether retrieval was involved at all. That is `agent-evals`'s full scope,
  including the five-weighted-dimension rubric and the release-gate
  mechanics in `skill-eval-harness`'s `score` subcommand -- this skill reuses
  that machinery for RAG cases rather than re-describing it.
- **Embedding-model selection.** Which embedding model to use, when to
  switch, and how to handle the re-indexing cost of a model change are a
  separate decision this skill does not weigh in on. This skill's job starts
  after an embedding model is already chosen and a corpus is already
  indexed: does what comes back for a query look right, and does generation
  respect it.

## Anti-patterns

- Reporting a citation-grounding proxy rate as if it were true recall@k
  against labeled relevance judgments -- state which measurement was used;
  they answer different questions and silently conflating them overstates
  confidence in retrieval quality.
- Scoring groundedness as one whole-answer verdict instead of claim-by-claim
  -- an answer that is 80% grounded and 20% fabricated passes a whole-answer
  "mostly looks right" check while still containing the exact hallucination
  a user would notice and lose trust over.
- Treating a confident, fluent, well-formatted wrong answer as acceptable
  because it "reads well" -- the failure mode that matters most here is
  exactly this one: no supporting context, and no hedge or abstention either.
- Writing a RAG eval case's `criteria` around final-answer correctness alone
  ("answers 500 items") when the case is meant to test retrieval honesty --
  that is a generic `agent-evals` case wearing a RAG label; the criteria
  need to check citation grounding and abstention behavior specifically.
- Building a second, RAG-specific eval runner instead of encoding cases in
  `skill-eval-harness`'s existing schema -- the file format and release-gate
  mechanics do not need to change; only the case content does.
- Assuming index staleness is a ranking or reranker problem and tuning top-k
  to fix it -- a stale chunk retrieved with perfect rank is still wrong;
  the fix is refreshing the index, not changing how it is searched.
- Drifting into vector-database tuning or embedding-model comparison inside
  a groundedness or retrieval-quality investigation -- both are out of scope
  for this skill; note the drift and hand it to whichever skill or specialist
  actually owns that layer instead of solving it here.
