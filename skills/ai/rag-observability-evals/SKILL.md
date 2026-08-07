---
name: rag-observability-evals
description: "Use when measuring RAG pipeline quality — retrieval precision/recall, answer groundedness (faithfulness to retrieved context), chunk relevance scoring, detecting hallucination beyond retrieved context, and monitoring retrieval drift in production."
---
# RAG Observability and Evals

## When to use

- Shipping a change to chunking strategy, top-k, reranker, or embedding model
- Detecting whether retrieved chunks are relevant to the query
- Measuring if generated answers are grounded in (faithful to) retrieved context
- Monitoring retrieval quality drift in production over time
- Debugging "wrong answer" reports in RAG-powered features

## When NOT to use

- General agent quality eval without retrieval component (use `agent-evals`)
- Cost or latency optimization (use `llm-cost-optimization` / `agent-observability`)
- Vector DB operational issues (infrastructure, not quality)
- Prompt injection through RAG chunks (use `prompt-injection-defense`)

## Steps

1. **Instrument the retrieval step** — capture what was retrieved and scored:
   ```python
   from opentelemetry import trace

   tracer = trace.get_tracer("rag.pipeline")

   async def retrieve_with_telemetry(query: str, top_k: int = 5) -> list[dict]:
       with tracer.start_as_current_span("rag.retrieve") as span:
           span.set_attribute("rag.query", query[:200])
           span.set_attribute("rag.top_k", top_k)

           # Embed query
           query_embedding = await embed(query)
           span.set_attribute("rag.embedding_model", "text-embedding-3-small")

           # Search vector store
           results = await vector_db.search(
               vector=query_embedding, limit=top_k, include_scores=True
           )

           span.set_attribute("rag.chunks_retrieved", len(results))
           span.set_attribute("rag.top_score", results[0].score if results else 0)
           span.set_attribute("rag.min_score", results[-1].score if results else 0)
           span.set_attribute("rag.chunk_sources",
               json.dumps([r.metadata.get("source") for r in results]))

           return results
   ```

2. **Measure retrieval quality** (precision + recall on golden set):
   ```python
   # evals/rag_retrieval_eval.py
   import yaml

   def evaluate_retrieval(golden_cases: list[dict], retriever) -> dict:
       """
       golden_cases format:
         - query: "How to configure KEDA ScaledObject?"
           relevant_doc_ids: ["keda-docs-001", "keda-docs-003"]
       """
       precisions, recalls = [], []

       for case in golden_cases:
           results = retriever(case["query"], top_k=5)
           retrieved_ids = {r.metadata["doc_id"] for r in results}
           relevant_ids = set(case["relevant_doc_ids"])

           # Precision: of what we retrieved, how much was relevant?
           precision = len(retrieved_ids & relevant_ids) / len(retrieved_ids) if retrieved_ids else 0
           # Recall: of what was relevant, how much did we retrieve?
           recall = len(retrieved_ids & relevant_ids) / len(relevant_ids) if relevant_ids else 0

           precisions.append(precision)
           recalls.append(recall)

       return {
           "precision_avg": sum(precisions) / len(precisions),
           "recall_avg": sum(recalls) / len(recalls),
           "precision_p50": sorted(precisions)[len(precisions)//2],
           "recall_p50": sorted(recalls)[len(recalls)//2],
       }
   ```

3. **Measure groundedness/faithfulness** (LLM-as-judge):
   ```python
   GROUNDEDNESS_PROMPT = """Given:
   - A question
   - Retrieved context (source documents)
   - A generated answer

   Rate the answer's GROUNDEDNESS: how much of the answer is supported by the context?
   A claim is grounded if the context contains evidence for it.
   A claim is ungrounded if it goes beyond what the context states.

   Question: {question}

   Context:
   {context}

   Answer: {answer}

   Return JSON:
   {{
     "grounded_claims": ["claim that IS supported by context", ...],
     "ungrounded_claims": ["claim that is NOT in context (hallucination)", ...],
     "groundedness_score": 0.0-1.0
   }}"""

   async def evaluate_groundedness(question: str, context: str, answer: str) -> float:
       result = await call_llm(
           model="claude-3-5-haiku-20241022",  # Cheap model for judging
           messages=[{"role": "user", "content": GROUNDEDNESS_PROMPT.format(
               question=question, context=context, answer=answer
           )}]
       )
       parsed = json.loads(result)
       return parsed["groundedness_score"]
   ```

4. **Detect retrieval drift in production** — monitor quality over time:
   ```python
   from opentelemetry import metrics

   meter = metrics.get_meter("rag.quality")

   # Proxy metrics (no golden labels needed in production)
   retrieval_score_hist = meter.create_histogram("rag.retrieval.top_score",
       description="Score of highest-ranked retrieved chunk")
   answer_length_hist = meter.create_histogram("rag.answer.length",
       description="Generated answer length in tokens")
   no_results_counter = meter.create_counter("rag.retrieval.empty",
       description="Queries that returned 0 relevant chunks")

   # Track in production
   async def rag_pipeline(query: str):
       chunks = await retrieve(query, top_k=5)

       if not chunks or chunks[0].score < 0.7:
           no_results_counter.add(1, {"source": "low_relevance"})

       retrieval_score_hist.record(chunks[0].score if chunks else 0)
       # ... generate answer ...
   ```

   ```yaml
   # Alert on retrieval quality degradation
   groups:
     - name: rag-quality
       rules:
         - alert: RAGRetrievalQualityDrop
           expr: |
             histogram_quantile(0.5, rate(rag_retrieval_top_score_bucket[1h])) < 0.75
           for: 30m
           labels: { severity: warning }
           annotations:
             summary: "RAG retrieval median score dropped below 0.75"

         - alert: RAGHighEmptyRetrievals
           expr: |
             rate(rag_retrieval_empty_total[15m]) / rate(rag_queries_total[15m]) > 0.2
           for: 15m
           labels: { severity: warning }
           annotations:
             summary: ">20% of RAG queries returning no relevant results"
   ```

5. **End-to-end RAG eval suite** (combine retrieval + groundedness):
   ```yaml
   # evals/rag_golden_dataset.yaml
   cases:
     - id: rag-001
       query: "How do I configure KEDA to scale from SQS?"
       relevant_doc_ids: ["keda-sqs-001", "keda-sqs-002"]
       expected_answer_contains: ["ScaledObject", "queueLength", "awsRegion"]
       expected_answer_does_not_contain: ["HPA"]  # Should NOT suggest raw HPA

     - id: rag-002
       query: "What's the BDC tagging policy for S3 buckets?"
       relevant_doc_ids: ["tags-mandatory-001"]
       expected_answer_contains: ["CostCenter", "Environment", "CostProject"]
       groundedness_threshold: 0.9  # Must be highly grounded for policy answers
   ```

   ```python
   # evals/run_rag_eval.py
   async def run_rag_eval(cases_file: str):
       cases = yaml.safe_load(open(cases_file))["cases"]
       results = []

       for case in cases:
           # Run full pipeline
           chunks = await retrieve(case["query"], top_k=5)
           answer = await generate(case["query"], chunks)

           # Score retrieval
           retrieved_ids = {c.metadata["doc_id"] for c in chunks}
           relevant_ids = set(case["relevant_doc_ids"])
           recall = len(retrieved_ids & relevant_ids) / len(relevant_ids)

           # Score groundedness
           context_text = "\n".join(c.text for c in chunks)
           groundedness = await evaluate_groundedness(case["query"], context_text, answer)

           # Score answer content
           contains_expected = all(
               term.lower() in answer.lower()
               for term in case.get("expected_answer_contains", [])
           )

           results.append({
               "id": case["id"],
               "recall": recall,
               "groundedness": groundedness,
               "contains_expected": contains_expected,
               "pass": recall >= 0.6 and groundedness >= 0.85 and contains_expected
           })

       pass_rate = sum(r["pass"] for r in results) / len(results)
       print(f"RAG eval pass rate: {pass_rate:.0%}")
       return results
   ```

## Decision tree

```
IF changing chunking strategy or embedding model:
  → Run retrieval precision/recall eval (step 2)
  → Compare before/after on same golden dataset
IF changing prompt template or generation model:
  → Run groundedness eval (step 3)
  → Check for new hallucination patterns
IF answer quality reports from users:
  → Is it a retrieval problem? (right docs not found)
    → Check retrieval scores, adjust top-k or reranker
  → Is it a generation problem? (right docs found, wrong answer)
    → Check groundedness, adjust prompt or model
  → Is it a chunking problem? (relevant info split across chunks)
    → Review chunk boundaries, consider overlap increase
IF production monitoring shows drift (step 4):
  → Compare current scores to baseline
  → Check: was the corpus updated? (new docs with different characteristics)
  → Check: did query patterns change? (new topics not in corpus)
  → Run full eval suite to quantify degradation
```

## Anti-patterns

- ❌ Only measuring end-to-end quality (can't tell if retrieval or generation is the problem)
- ❌ No golden dataset for retrieval (can't measure precision/recall)
- ❌ Groundedness eval using the same model that generated the answer (self-grading bias)
- ❌ No production monitoring (quality degrades silently when corpus changes)
- ❌ Using high top-k (20+) hoping more context helps (often hurts — noise dilutes signal)
- ❌ Never testing what happens when retrieval returns nothing relevant
- ❌ Conflating "answer is wrong" with "retrieval failed" without diagnosing which

## Related skills

- `agent-evals` — general agent quality evaluation (non-RAG-specific)
- `agent-observability` — emitting the spans and metrics this skill reads
- `ai-pipeline-orchestration` — RAG as a pipeline with retrieval + generation steps
- `prompt-injection-defense` — defending against injection via RAG chunks
