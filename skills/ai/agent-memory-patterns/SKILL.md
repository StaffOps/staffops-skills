---
name: agent-memory-patterns
description: "Use when designing memory and context systems for AI agents — short-term session buffers, long-term knowledge bases, episodic recall. Covers memory types (buffer, summary, vector, graph), retrieval strategies, TTL/eviction policies, knowledge base indexing, and context window management. Decision tree for which memory type fits which use case."
---
# Agent Memory Patterns

## When to use

- Designing a new AI agent that needs to remember across turns or sessions
- Choosing between memory architectures (buffer, vector, graph, hybrid)
- Implementing retrieval strategies for relevant context injection
- Setting TTL and eviction policies for memory stores
- Managing context window budget (what to keep, summarize, or drop)
- Building knowledge bases that agents can query at inference time

## When NOT to use

- Building RAG pipelines specifically (use `rag-observability-evals` for eval)
- Optimizing LLM inference cost (use `llm-cost-optimization`)
- Securing agent memory against exfiltration (use `ai-agent-security`)

---

## Decision tree: Which memory type?

```
What does the agent need to remember?
│
├── Current conversation turns (last N messages)
│   └── BUFFER MEMORY — simple, cheap, ephemeral
│
├── Key facts from a long conversation
│   └── SUMMARY MEMORY — compress, retain essence
│
├── Searchable knowledge (docs, past interactions, domain facts)
│   └── VECTOR MEMORY — embed + semantic search
│
├── Relationships between entities (services, people, dependencies)
│   └── GRAPH MEMORY — nodes + edges, traversal queries
│
├── "I did this before and it worked/failed"
│   └── EPISODIC MEMORY — timestamped episodes with outcomes
│
└── Need 2+ of the above?
    └── HYBRID — compose layers (buffer + vector is most common)
```

---

## Memory types

### 1. Buffer memory (short-term)

**What**: Last N messages or last K tokens of conversation history.
**When**: Single-session agents, chatbots, coding assistants.

```python
class BufferMemory:
    def __init__(self, max_messages: int = 50):
        self.messages: deque[Message] = deque(maxlen=max_messages)

    def add(self, msg: Message):
        self.messages.append(msg)

    def get_context(self) -> list[Message]:
        return list(self.messages)
```

| Pro | Con |
|-----|-----|
| Zero latency | Grows linearly with conversation |
| No retrieval errors | Old context falls off silently |
| Simple to implement | No cross-session persistence |

**Eviction**: FIFO (oldest messages drop). Optionally pin system messages.

### 2. Summary memory (compressed)

**What**: LLM-generated summaries of past conversation segments.
**When**: Long conversations where full history exceeds context window.

```
Every N messages (or at token threshold):
  1. Take oldest unsummarized messages
  2. Prompt: "Summarize preserving key decisions and facts"
  3. Replace raw messages with summary block
  4. Keep last M raw messages for recency
```

| Pro | Con |
|-----|-----|
| Bounded size regardless of length | Lossy — details disappear |
| Retains key decisions | Summary quality depends on LLM |
| Cheap to query (just prepend) | Summarization cost (extra LLM calls) |

**Eviction**: Summaries cascade — old summaries re-summarize into meta-summaries.

### 3. Vector memory (semantic search)

**What**: Embeddings stored in a vector DB, retrieved by semantic similarity.
**When**: Large knowledge bases, past interactions, document corpora.

```python
class VectorMemory:
    def store(self, text: str, metadata: dict):
        embedding = self.embedder.encode(text)
        self.db.upsert(id=hash(text), vector=embedding, metadata=metadata)

    def retrieve(self, query: str, top_k: int = 5) -> list[Document]:
        query_vec = self.embedder.encode(query)
        return self.db.search(query_vec, top_k=top_k)
```

**Chunking strategy**:

| Content type | Chunk size | Overlap |
|--------------|-----------|---------|
| Prose (docs, runbooks) | 500–800 tokens | 50 tokens |
| Code | Per-function or per-class | None |
| Conversations | Per-turn or per-topic-shift | 1 message |
| Structured (YAML, JSON) | Per top-level key | None |

| Pro | Con |
|-----|-----|
| Scales to millions of items | Retrieval can miss relevant content |
| Cross-session by default | Requires embedding infrastructure |
| Semantic matching | Chunk boundary issues lose context |

**Eviction**: TTL per document, or score-decay (reduce relevance over time).

### 4. Graph memory (relational)

**What**: Knowledge graph of entities and relationships.
**When**: Multi-entity domains (infra topology, org charts, dependency maps).

```
Nodes: { type: "Service", name: "payments-api", props: {...} }
Edges: { from: "payments-api", to: "redis", type: "DEPENDS_ON" }

Query: "What does payments-api depend on?"
→ Traverse outgoing DEPENDS_ON edges → redis, postgres, auth-service
```

| Pro | Con |
|-----|-----|
| Explicit relationships | Complex to maintain |
| Multi-hop reasoning | Schema design upfront |
| Deterministic retrieval | Doesn't handle fuzzy queries |

**Eviction**: Edge staleness (last-confirmed timestamp); prune after N days.

### 5. Episodic memory (experience replay)

**What**: Timestamped records of past actions + outcomes.
**When**: Agents that learn from past attempts (debugging, incident response).

```json
{
  "timestamp": "2026-08-01T14:30:00Z",
  "task": "Fix OOM in tempo-distributor",
  "actions_taken": ["checked metrics", "scaled replicas", "increased memory"],
  "outcome": "resolved",
  "learnings": "OOM caused by trace_too_large spans; memory alone doesn't fix root cause",
  "tags": ["tempo", "oom", "observability"]
}
```

**Retrieval**: Tag-match + recency-weighted + semantic similarity on task description.

---

## Retrieval strategies

| Strategy | How | Best for |
|----------|-----|----------|
| Top-K similarity | Nearest K vectors to query | General knowledge lookup |
| MMR (Max Marginal Relevance) | Diversity-aware results | Broad context injection |
| Hybrid (keyword + semantic) | BM25 + vector scores, fused | Technical docs with exact terms |
| Recency-weighted | Score × decay(age) | Conversations, evolving state |
| Metadata-filtered | Filter by tags BEFORE similarity | Multi-tenant, scoped retrieval |
| Agentic retrieval | Agent decides WHAT to search, iterates | Complex multi-step research |

---

## Context window management

### Budget allocation (typical 128K model)

| Segment | Budget | Purpose |
|---------|--------|---------|
| System prompt + steering | 5–15% | Identity, rules, guardrails |
| Retrieved context (memory) | 20–40% | Knowledge injection |
| Conversation history | 20–30% | Recent turns |
| Reasoning headroom | 30–40% | Thinking + output |

### When to compress vs drop

```
Token usage approaching 70% of window?
├── Summarize oldest conversation turns
├── Reduce retrieved context (fewer chunks, higher threshold)
├── Drop tool outputs from >5 turns ago
└── NEVER drop: system prompt, last 3 user turns, active task state
```

---

## TTL and eviction policies

| Memory layer | Default TTL | Eviction trigger |
|--------------|-------------|------------------|
| Buffer (session) | End of session | Session close or idle timeout |
| Summary | 30 days | Age + no-access in 14 days |
| Vector (knowledge) | Indefinite | Manual refresh or source-change detection |
| Graph (entities) | Indefinite | Edge staleness > 90 days → soft-delete |
| Episodic | 180 days | Age; keep high-value episodes indefinitely |

---

## Knowledge base indexing

### Ingestion pipeline

```
Source (git repo, docs, wiki, past sessions)
  → Chunk (size + overlap per content type)
  → Embed (text-embedding-3-small or equivalent)
  → Store (vector DB + metadata: source, date, tags)
  → Index (optional: keyword index for hybrid search)
```

### Refresh strategy

| Source type | Refresh frequency | Method |
|-------------|-------------------|--------|
| Git repo docs | On commit (webhook) | Incremental — changed files only |
| Wiki/Confluence | Daily poll | Diff against last-seen version |
| Past agent sessions | End of session | Extract learnings as episodes |
| Structured data (CMDB) | Hourly | Full replace (small, fast) |

---

## Anti-patterns

- ❌ Stuffing entire history into every prompt (token waste)
- ❌ No memory for multi-turn agents (loses user intent)
- ❌ Vector-only without metadata filters (noisy retrieval)
- ❌ Never evicting (unbounded growth, quality degrades)
- ❌ Summarizing too aggressively (key details lost)
- ❌ Same chunk size for all content types
- ❌ No deduplication (same fact stored 50 times)
- ❌ Graph without maintenance (stale edges = wrong reasoning)

---

## Checklist: designing agent memory

- [ ] Identified which memory types are needed (decision tree)
- [ ] Defined context window budget allocation
- [ ] Chunking strategy matches content types
- [ ] Retrieval strategy chosen (top-K, hybrid, MMR, etc.)
- [ ] TTL and eviction policies defined per layer
- [ ] Refresh/ingestion pipeline for knowledge sources
- [ ] Deduplication strategy (hash-based or semantic)
- [ ] Fallback when retrieval returns nothing relevant
- [ ] Monitoring: retrieval hit rate, context utilization, token budget
