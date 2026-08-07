---
name: mcp-tool-design-patterns
description: "Use when designing MCP (Model Context Protocol) tools — input schemas, error handling, idempotency, pagination, naming conventions. Covers validation with Zod/Pydantic, output structure (structured vs streaming), error codes, rate limiting, testing patterns, and the decision tree for when to build a new tool vs extend an existing one."
---
# MCP Tool Design Patterns

## When to use

- Designing a new MCP tool (server-side function exposed to an AI agent)
- Reviewing an existing tool for correctness, safety, or usability
- Deciding whether to add a new tool or extend an existing one
- Building input validation schemas for tool parameters
- Designing error handling and retry strategies
- Implementing pagination for large result sets
- Writing integration tests for MCP tools

## When NOT to use

- Building the MCP server transport layer (use `mcp-server-development`)
- Securing MCP endpoints against prompt injection (use `mcp-server-security`)
- Monitoring MCP tool usage in production (use `agent-observability`)

---

## Decision tree: New tool vs extend existing

```
Does an existing tool cover >70% of the use case?
├── YES → Can you add optional params without breaking callers?
│   ├── YES → Extend existing tool (add optional params + docs)
│   └── NO  → New tool (name: <existing>_<variant>)
└── NO  → Is the new capability a single atomic operation?
    ├── YES → One new tool (verb_noun pattern)
    └── NO  → Decompose into 2–3 focused tools
```

**Heuristic**: a tool that needs >8 parameters or does >2 things is too broad. Split it.

---

## Tool naming conventions

| Pattern | Example | When |
|---------|---------|------|
| `verb_noun` | `list_pods`, `get_metric` | Standard CRUD/query |
| `verb_noun_qualifier` | `search_logs_by_label` | Disambiguation |
| `check_noun` | `check_dns_resolution` | Boolean/diagnostic |
| `analyze_noun` | `analyze_network_policies` | Multi-step inference |

**Rules:**
- snake_case (not camelCase, not kebab-case)
- Verb first — action-oriented
- Singular noun for single-resource ops (`get_pod`), plural for collections (`list_pods`)
- Max 40 characters — agent token budgets are real
- Avoid generic verbs: `do_thing`, `run_operation`, `handle_request`

---

## Input schema design

### Principles

1. **Required params = minimum viable input.** If the tool can work without it, make it optional.
2. **Enums over free-text** when values are bounded.
3. **Descriptions are for the LLM**, not humans — write them as if explaining to a colleague.
4. **Defaults in the description**, not hidden in code.

### Zod (TypeScript)

```typescript
const ListPodsInput = z.object({
  namespace: z.string()
    .describe("K8s namespace. Omit for all namespaces.").optional(),
  labelSelector: z.string()
    .describe("Label selector (e.g. 'app=nginx,env=prod')").optional(),
  limit: z.number().int().min(1).max(500).default(100)
    .describe("Max results to return. Default: 100"),
});
```

### Pydantic (Python)

```python
class ListPodsInput(BaseModel):
    namespace: str | None = Field(
        None, description="K8s namespace. Omit for all namespaces."
    )
    label_selector: str | None = Field(
        None, description="Label selector (e.g. 'app=nginx,env=prod')"
    )
    limit: int = Field(
        100, ge=1, le=500, description="Max results to return. Default: 100"
    )
```

### Common validation patterns

| Pattern | Implementation |
|---------|---------------|
| Enum constraint | `z.enum(["amd64","arm64"])` / `Literal["amd64","arm64"]` |
| Regex pattern | `z.string().regex(/^[a-z0-9-]+$/)` / `Field(pattern=...)` |
| Mutually exclusive | Runtime check + clear error; document in description |
| Dependent params | "Required when X is set" in description + runtime validation |
| Array with bounds | `z.array().min(1).max(50)` / `Field(min_length=1, max_length=50)` |

---

## Output structure

### Structured (default — prefer this)

```json
{
  "items": [...],
  "total": 142,
  "truncated": true,
  "nextCursor": "eyJvZmZzZXQiOjEwMH0="
}
```

### Streaming (use sparingly)

Only for: log tailing (unbounded), long-running ops (progress), large files (chunked).
Never stream when total result fits in <50KB.

### Output rules

1. Always include metadata — `total`, `truncated`, `nextCursor` for collections.
2. Consistent shape — same top-level keys whether 0 or 1000 results.
3. No secrets in output — redact values, show key names only.
4. Truncate aggressively — 200 items is plenty for an LLM.

---

## Error handling

### Error response structure

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Pod 'nginx-abc123' not found in namespace 'default'",
    "retryable": false,
    "suggestion": "Check namespace with list_namespaces or verify pod name"
  }
}
```

### Standard error codes

| Code | Meaning | Retryable |
|------|---------|-----------|
| `INVALID_INPUT` | Schema validation failed | No |
| `RESOURCE_NOT_FOUND` | Target doesn't exist | No |
| `PERMISSION_DENIED` | Auth/RBAC insufficient | No |
| `RATE_LIMITED` | Too many requests | Yes (backoff) |
| `TIMEOUT` | Operation exceeded deadline | Yes |
| `UPSTREAM_ERROR` | Dependency failed | Yes |
| `INTERNAL_ERROR` | Bug in tool implementation | No |

### Principles

- **Actionable messages** — tell the agent what to try next.
- **Never expose stack traces** — they waste tokens.
- **Distinguish retryable vs terminal** — agents retry retryable errors.
- **Include the failing input** so the agent can self-correct.

---

## Idempotency

Tools that modify state MUST be idempotent or clearly documented as non-idempotent.

| Pattern | How |
|---------|-----|
| Create-if-not-exists | Check existence first, return existing if found |
| Upsert | Apply desired state regardless of current state |
| Idempotency key | Accept `requestId` param; deduplicate server-side |
| Non-idempotent (acknowledged) | Mark in description: "Calling twice creates duplicates" |

---

## Pagination

### Cursor-based (preferred)

```typescript
// Input: { cursor?: string, limit?: number }
// Output: { items: [...], nextCursor: "abc123" | null }
```

- Opaque cursor (base64-encoded offset or token)
- `nextCursor: null` means last page
- Stateless — no server-side session

### Offset-based (simple cases only)

Use when total count is cheap and data doesn't shift between pages.

---

## Rate limiting

- Document limits in tool description: "Max 10 calls/minute per session"
- Return `RATE_LIMITED` error with `retryAfterMs` field
- Server-side: sliding window per session/user
- Client-side: agents should respect `retryAfterMs`

---

## Testing patterns

### Unit tests (per tool)

```python
def test_list_pods_empty_namespace():
    result = list_pods_tool(namespace="nonexistent")
    assert result["items"] == []
    assert result["total"] == 0

def test_list_pods_invalid_selector():
    result = list_pods_tool(label_selector="not!valid")
    assert result["error"]["code"] == "INVALID_INPUT"
```

### Integration tests (end-to-end via MCP protocol)

```python
def test_tool_via_mcp_protocol():
    response = mcp_client.call_tool("list_pods", {"namespace": "default"})
    assert "items" in response.content[0].text
```

### Agent-level evals (behavioral)

```yaml
- input: "How many pods are running in kube-system?"
  expected_tool_call: list_pods
  expected_params_contain: { namespace: "kube-system" }
  expected_answer_contains: "running"
```

---

## Anti-patterns

- ❌ Tools that do 5 things (split into focused tools)
- ❌ Required params that could have sensible defaults
- ❌ Descriptions that say "A tool that..." (just describe the action)
- ❌ Returning raw upstream API responses without shaping
- ❌ No pagination on collections (token explosion)
- ❌ Swallowing errors and returning empty results
- ❌ Side effects in tools named `get_*` or `list_*`
- ❌ Hardcoded limits without documenting them
- ❌ Tools that require multi-step orchestration to be useful

---

## Checklist: shipping a new MCP tool

- [ ] Name follows `verb_noun` convention
- [ ] Input schema has descriptions for every param
- [ ] Required params are genuinely required
- [ ] Output shape is consistent (same keys for 0 and N results)
- [ ] Collections are paginated with cursor/limit
- [ ] Errors return structured code + actionable message
- [ ] Idempotency behavior is documented
- [ ] Rate limits documented in description
- [ ] Unit + integration tests cover happy path + error cases
- [ ] Tool description is <200 chars and answers "when would I call this?"
