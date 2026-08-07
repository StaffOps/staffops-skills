---
name: llm-caching
description: "Use when reducing LLM API costs and latency through semantic caching, prompt caching (provider-native), response memoization, and embedding-based cache lookup — choosing the right caching strategy per use case."
---
# LLM Caching

## When to use

- Repeated similar queries hitting the same LLM (FAQ, classification, routing)
- High-latency LLM calls where cached responses improve UX
- Cost reduction on workloads with predictable/repeated patterns
- Provider-native prompt caching (Anthropic, OpenAI) for long system prompts
- Embedding-based semantic deduplication for RAG queries

## When NOT to use

- Every query is unique with no repetition (caching adds overhead, no benefit)
- Responses must always be fresh (real-time data, live system state)
- Small system prompts (<1000 tokens — provider caching savings negligible)
- Security-sensitive outputs that shouldn't be stored

## Steps

1. **Provider-native prompt caching** (cheapest, zero infrastructure):
   ```python
   # Anthropic — automatic for repeated system prompts >1024 tokens
   # Mark long, reusable content with cache_control
   response = client.messages.create(
       model="claude-sonnet-4-20250514",
       system=[
           {
               "type": "text",
               "text": LONG_SYSTEM_PROMPT,  # >1024 tokens
               "cache_control": {"type": "ephemeral"}  # Cache this block
           }
       ],
       messages=[{"role": "user", "content": user_query}]
   )
   # Result: subsequent calls with same system prompt = 90% cheaper on cached tokens
   # Cache TTL: 5 minutes (Anthropic), auto-managed
   ```

   ```python
   # OpenAI — automatic prefix caching (no configuration needed)
   # Any shared prefix >1024 tokens is cached server-side at 50% discount
   # Just ensure system/few-shot messages are IDENTICAL across calls
   ```

2. **Exact-match response cache** (Redis, for deterministic queries):
   ```python
   import hashlib, json
   from redis import Redis

   redis = Redis.from_url(os.environ["REDIS_URL"])
   CACHE_TTL = 3600  # 1 hour

   def cached_llm_call(messages: list, model: str, **kwargs) -> str:
       # Deterministic cache key from input
       cache_key = f"llm:{model}:" + hashlib.sha256(
           json.dumps(messages, sort_keys=True).encode()
       ).hexdigest()

       # Check cache
       cached = redis.get(cache_key)
       if cached:
           return cached.decode()

       # Call LLM
       response = call_llm(messages=messages, model=model, **kwargs)
       result = response.content[0].text

       # Store with TTL
       redis.setex(cache_key, CACHE_TTL, result)
       return result
   ```

3. **Semantic cache** (for near-duplicate queries):
   ```python
   import numpy as np
   from openai import OpenAI

   # Embed the query, find nearest cached query above threshold
   SIMILARITY_THRESHOLD = 0.95  # Tune per use case (0.95 = very similar only)

   async def semantic_cache_lookup(query: str) -> str | None:
       query_embedding = get_embedding(query)

       # Search vector store for similar past queries
       results = await vector_db.search(
           collection="llm_cache",
           vector=query_embedding,
           limit=1,
           score_threshold=SIMILARITY_THRESHOLD
       )

       if results and results[0].score >= SIMILARITY_THRESHOLD:
           return results[0].metadata["response"]
       return None

   async def semantic_cached_call(query: str, messages: list, model: str) -> str:
       # Try semantic cache first
       cached = await semantic_cache_lookup(query)
       if cached:
           return cached

       # Call LLM
       response = await call_llm(messages=messages, model=model)
       result = response.content[0].text

       # Store in semantic cache
       embedding = get_embedding(query)
       await vector_db.upsert(
           collection="llm_cache",
           id=str(uuid4()),
           vector=embedding,
           metadata={"query": query, "response": result, "model": model}
       )
       return result
   ```

4. **Classification/routing cache** (highest hit rate):
   ```python
   # For classification tasks, cache is nearly always beneficial
   # because the same input text often maps to the same category

   CLASSIFICATION_CACHE_TTL = 86400  # 24h — categories don't change often

   async def cached_classify(text: str) -> str:
       # Normalize input (lowercase, strip whitespace, remove punctuation)
       normalized = normalize_text(text)
       cache_key = f"classify:{hashlib.md5(normalized.encode()).hexdigest()}"

       cached = await redis.get(cache_key)
       if cached:
           return cached.decode()

       category = await classify_with_llm(text)
       await redis.setex(cache_key, CLASSIFICATION_CACHE_TTL, category)
       return category
   ```

5. **Cache invalidation strategy**:
   ```python
   # Invalidation triggers:
   # 1. TTL-based (automatic, simplest)
   # 2. Model change (new model = flush all)
   # 3. Prompt change (system prompt updated = flush relevant)
   # 4. Manual (admin detected stale/wrong cache entry)

   async def invalidate_cache(reason: str, pattern: str = None):
       if pattern:
           keys = await redis.keys(f"llm:{pattern}*")
           if keys:
               await redis.delete(*keys)
               log.info(f"Invalidated {len(keys)} cache entries", reason=reason)
       else:
           await redis.flushdb()
           log.warning("Full cache flush", reason=reason)

   # On model change:
   # invalidate_cache(reason="model_upgrade", pattern="claude-sonnet-4-20250514")
   ```

6. **Monitor cache effectiveness**:
   ```python
   from opentelemetry import metrics

   meter = metrics.get_meter("llm.cache")
   cache_hits = meter.create_counter("llm_cache_hits_total")
   cache_misses = meter.create_counter("llm_cache_misses_total")
   cache_savings = meter.create_counter("llm_cache_savings_usd")

   # Track per cache type
   cache_hits.add(1, {"cache_type": "exact", "model": model})
   cache_savings.add(estimated_cost, {"cache_type": "semantic", "model": model})
   ```

## Decision tree

```
IF queries repeat exactly (FAQ, classification, routing):
  → Exact-match Redis cache (step 2) — cheapest, fastest, highest hit rate
IF queries are similar but not identical (search, QA):
  → Semantic cache (step 3) — tune threshold carefully
IF system prompt is >1024 tokens and reused across calls:
  → Provider-native caching (step 1) — zero effort, automatic savings
IF responses must be personalized per user:
  → Cache ONLY the non-personalized parts (classification, retrieval)
  → Skip caching the final generation step
IF cache is stale/wrong and causing issues:
  → TTL too long? Shorten
  → Semantic threshold too low? (returning wrong cached answers) → Raise to 0.97+
  → Model changed? → Flush relevant keys
```

## Anti-patterns

- ❌ Caching with temperature >0 and expecting consistent results (non-deterministic)
- ❌ Semantic cache with threshold <0.90 (returns wrong answers for different queries)
- ❌ No TTL on cache entries (stale forever)
- ❌ Caching personalized responses (user A sees user B's answer)
- ❌ No cache invalidation on model/prompt change (serving outdated responses)
- ❌ Caching before measuring repetition rate (add cache where hit rate >20%)
- ❌ Large embedding model for cache lookup (lookup cost > LLM cost savings)

## Related skills

- `llm-cost-optimization` — broader cost reduction strategies
- `agent-observability` — tracking cache hit/miss metrics
- `rag-observability-evals` — caching in RAG pipelines
- `ai-pipeline-orchestration` — where to place cache in a multi-step pipeline
