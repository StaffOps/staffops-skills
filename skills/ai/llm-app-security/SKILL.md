---
name: llm-app-security
description: "Use when building application-layer security for LLM-powered features — output validation, PII filtering, content moderation, output format enforcement, and preventing the application from acting on hallucinated or manipulated LLM responses."
---
# LLM Application Security

## When to use

- Building a user-facing feature powered by LLM responses
- Need to validate/sanitize LLM output before it reaches users or systems
- Implementing PII detection and redaction in LLM I/O
- Enforcing output format (JSON schema, enum values) from LLM responses
- Preventing hallucinated URLs, code, or commands from being executed
- Adding content moderation to chat interfaces

## When NOT to use

- Defending against prompt injection in inputs (use `prompt-injection-defense`)
- Securing the agent's tool permissions (use `ai-agent-security`)
- Infrastructure-level hardening (use `ai-security-hardening`)
- Model supply chain concerns (use `model-supply-chain-security`)

## Steps

1. **Validate LLM output against schema** — never trust free-form:
   ```python
   from pydantic import BaseModel, validator
   from enum import Enum

   class Severity(str, Enum):
       low = "low"
       medium = "medium"
       high = "high"
       critical = "critical"

   class TriageResult(BaseModel):
       category: str
       severity: Severity
       summary: str  # Max 500 chars
       suggested_action: str
       confidence: float  # 0.0-1.0

       @validator("summary")
       def summary_length(cls, v):
           if len(v) > 500:
               return v[:500]
           return v

       @validator("confidence")
       def confidence_range(cls, v):
           return max(0.0, min(1.0, v))

   # Use structured output (Anthropic/OpenAI support this natively)
   response = client.messages.create(
       model="claude-sonnet-4-20250514",
       messages=[...],
       # Force JSON output matching schema
       response_format={"type": "json_object"}
   )

   # Parse + validate — reject if malformed
   try:
       result = TriageResult.model_validate_json(response.content[0].text)
   except ValidationError as e:
       log.warning(f"LLM output failed validation: {e}")
       return fallback_response()
   ```

2. **PII detection and redaction** on both input and output:
   ```python
   import re

   PII_PATTERNS = {
       "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
       "cpf": r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b',
       "phone_br": r'\b\+?55?\s?\(?\d{2}\)?\s?\d{4,5}-?\d{4}\b',
       "credit_card": r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
       "aws_key": r'\bAKIA[0-9A-Z]{16}\b',
   }

   def redact_pii(text: str) -> tuple[str, list[str]]:
       """Returns (redacted_text, list_of_detected_types)."""
       detected = []
       for pii_type, pattern in PII_PATTERNS.items():
           if re.search(pattern, text):
               detected.append(pii_type)
               text = re.sub(pattern, f"[REDACTED_{pii_type.upper()}]", text)
       return text, detected

   # Apply to both input (before sending to LLM) and output (before showing user)
   clean_input, input_pii = redact_pii(user_message)
   if input_pii:
       log.info(f"Redacted PII from input: {input_pii}")

   response = call_llm(clean_input)
   clean_output, output_pii = redact_pii(response)
   if output_pii:
       log.warning(f"LLM leaked PII in output: {output_pii}")
   ```

3. **Output content moderation** — block harmful outputs:
   ```python
   BLOCKED_PATTERNS = [
       r'(?i)(password|secret|token)\s*[:=]\s*\S+',  # Credential-like output
       r'(?i)rm\s+-rf\s+/',  # Destructive commands
       r'(?i)(drop|delete)\s+(table|database|schema)',  # SQL DDL
       r'https?://(?!internal\.|docs\.|grafana\.)',  # External URLs (hallucinated)
   ]

   def moderate_output(text: str) -> tuple[str, bool]:
       """Returns (text, was_modified)."""
       modified = False
       for pattern in BLOCKED_PATTERNS:
           if re.search(pattern, text):
               text = re.sub(pattern, "[BLOCKED_CONTENT]", text)
               modified = True
       return text, modified
   ```

4. **Prevent hallucinated action execution**:
   ```python
   # NEVER execute LLM-generated code/commands without validation
   def safe_execute_suggestion(llm_suggestion: dict) -> dict:
       action = llm_suggestion.get("action")
       target = llm_suggestion.get("target")

       # Allowlist of valid actions
       VALID_ACTIONS = {"restart_pod", "scale_deployment", "check_logs", "query_metric"}
       if action not in VALID_ACTIONS:
           return {"error": f"Action '{action}' not in allowlist"}

       # Validate target exists
       if action == "restart_pod" and not pod_exists(target):
           return {"error": f"Pod '{target}' does not exist (hallucinated?)"}

       # Execute only after validation
       return execute_action(action, target)
   ```

5. **Rate limit and quota per user session**:
   ```python
   from datetime import datetime, timedelta

   class SessionGuard:
       def __init__(self, max_messages=50, max_tokens=100_000, window=timedelta(hours=1)):
           self.max_messages = max_messages
           self.max_tokens = max_tokens
           self.window = window

       async def check(self, session_id: str) -> bool:
           key = f"session:{session_id}"
           usage = await redis.hgetall(key)
           msg_count = int(usage.get("messages", 0))
           token_count = int(usage.get("tokens", 0))

           if msg_count >= self.max_messages:
               raise RateLimitExceeded("Message limit reached")
           if token_count >= self.max_tokens:
               raise RateLimitExceeded("Token budget exhausted")
           return True
   ```

6. **Logging for security forensics** (without logging sensitive content):
   ```python
   # Log decisions and anomalies, NOT full prompts/responses
   audit_log.info("llm_interaction",
       session_id=session_id,
       user_id=user_id,
       input_token_count=input_tokens,
       output_token_count=output_tokens,
       pii_detected_in_input=bool(input_pii),
       pii_detected_in_output=bool(output_pii),
       output_moderated=was_modified,
       validation_passed=True,
       model=model_used,
       latency_ms=latency,
   )
   ```

## Decision tree

```
IF building chat interface (user sees raw LLM output):
  → PII redaction on output (step 2)
  → Content moderation (step 3)
  → Rate limiting per session (step 5)
IF LLM output drives automated action:
  → Schema validation mandatory (step 1)
  → Action allowlist (step 4)
  → Never execute generated code directly
IF LLM processes user-uploaded documents:
  → PII redaction on input (step 2)
  → Size limits on input
  → Scan for injection patterns (see prompt-injection-defense)
IF compliance requirement (LGPD, GDPR):
  → PII redaction on BOTH directions
  → Audit logging without content (step 6)
  → Retention policy on LLM interaction logs
```

## Anti-patterns

- ❌ Displaying raw LLM output to users without moderation
- ❌ Executing LLM-suggested commands/code without allowlist validation
- ❌ No PII filtering (LLM can hallucinate or repeat PII from training)
- ❌ Trusting LLM JSON output without schema validation
- ❌ Logging full prompts/responses (PII + storage explosion)
- ❌ No rate limiting (abuse via chat flooding)
- ❌ Hallucinated URLs rendered as clickable links (phishing vector)

## Related skills

- `prompt-injection-defense` — input-side defense
- `ai-agent-security` — agent tool permission scoping
- `ai-security-hardening` — infrastructure layer
- `rag-observability-evals` — ensuring grounded outputs
