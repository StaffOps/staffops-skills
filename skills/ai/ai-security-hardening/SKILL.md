---
name: ai-security-hardening
description: "Use when hardening AI/ML infrastructure — securing model serving endpoints, API key rotation, rate limiting LLM APIs, network isolation for inference workloads, and securing the training/fine-tuning pipeline from data poisoning."
---
# AI Security Hardening

## When to use

- Deploying model-serving infrastructure (vLLM, TGI, Ollama, SageMaker endpoints)
- Securing LLM API keys and access tokens in production
- Implementing rate limiting and abuse prevention on AI endpoints
- Network-isolating inference workloads from general compute
- Hardening training/fine-tuning pipelines against data poisoning
- Compliance review of AI infrastructure (SOC2, ISO 27001 AI controls)

## When NOT to use

- Application-layer LLM security (use `llm-app-security`)
- Agent-level permission scoping (use `ai-agent-security`)
- Defending against prompt injection (use `prompt-injection-defense`)
- Model provenance and SBOM (use `model-supply-chain-security`)

## Steps

1. **Secure model-serving endpoints** — never expose directly:
   ```yaml
   # Network policy: inference pods only reachable from API gateway
   apiVersion: networking.k8s.io/v1
   kind: NetworkPolicy
   metadata:
     name: inference-isolation
     namespace: ai-inference
   spec:
     podSelector:
       matchLabels:
         app: vllm-server
     policyTypes: [Ingress]
     ingress:
       - from:
           - namespaceSelector:
               matchLabels:
                 name: api-gateway
           - podSelector:
               matchLabels:
                 role: llm-proxy
         ports:
           - port: 8000
             protocol: TCP
   ```

2. **API key management** — rotate, scope, audit:
   ```yaml
   # ExternalSecret for LLM API keys
   apiVersion: external-secrets.io/v1beta1
   kind: ExternalSecret
   metadata:
     name: llm-api-keys
     namespace: ai-services
   spec:
     refreshInterval: 1h
     secretStoreRef:
       name: aws-secrets
       kind: ClusterSecretStore
     target:
       name: llm-credentials
       creationPolicy: Owner
     data:
       - secretKey: ANTHROPIC_API_KEY
         remoteRef:
           key: ai-platform/anthropic
           property: api_key
       - secretKey: OPENAI_API_KEY
         remoteRef:
           key: ai-platform/openai
           property: api_key
   ```

   ```python
   # Application reads from file-mounted secret, not env var
   from pathlib import Path

   def get_api_key(provider: str) -> str:
       key_path = Path(f"/etc/secrets/llm-credentials/{provider.upper()}_API_KEY")
       return key_path.read_text().strip()
   ```

3. **Rate limiting and abuse prevention**:
   ```yaml
   # Istio/Envoy rate limit on AI endpoints
   apiVersion: networking.istio.io/v1
   kind: EnvoyFilter
   metadata:
     name: ai-rate-limit
   spec:
     workloadSelector:
       labels:
         app: ai-gateway
     configPatches:
       - applyTo: HTTP_ROUTE
         match:
           routeConfiguration:
             vhost:
               route:
                 name: ai-completions
         patch:
           operation: MERGE
           value:
             rate_limits:
               - actions:
                   - header_value_match:
                       descriptor_value: "per_user"
                       headers:
                         - name: x-user-id
                           present_match: true
                 stage: 0
   ```

   ```python
   # Application-level token budget per user/team
   from redis import Redis

   redis = Redis.from_url(os.environ["REDIS_URL"])

   async def check_token_budget(user_id: str, tokens_requested: int) -> bool:
       key = f"token_budget:{user_id}:{date.today()}"
       current = int(redis.get(key) or 0)
       daily_limit = 1_000_000  # 1M tokens/day per user
       if current + tokens_requested > daily_limit:
           return False
       redis.incrby(key, tokens_requested)
       redis.expire(key, 86400)
       return True
   ```

4. **Secure training data pipeline** (prevent poisoning):
   ```yaml
   # Validation pipeline for training data
   steps:
     - name: data-integrity
       checks:
         - hash_verification: "sha256 of source files matches manifest"
         - size_bounds: "no single sample > 100KB (injection attempt signal)"
         - encoding_check: "UTF-8 only, no hidden Unicode"
     - name: content-filter
       checks:
         - no_instruction_patterns: "filter samples containing 'ignore previous', 'you are now', 'system:'"
         - statistical_outlier: "flag samples whose embedding distance > 3σ from cluster mean"
     - name: provenance
       checks:
         - source_allowlist: "data only from approved repositories"
         - contributor_verification: "all contributors have signed CLA"
   ```

5. **Audit logging for all AI operations**:
   ```python
   # Structured audit log for every LLM call
   import structlog

   audit_log = structlog.get_logger("ai.audit")

   async def audited_llm_call(user_id: str, model: str, messages: list, **kwargs):
       request_id = str(uuid4())
       audit_log.info("llm_request",
           request_id=request_id, user_id=user_id, model=model,
           input_tokens=count_tokens(messages),
           tools_requested=[m.get("tool_use") for m in messages if "tool_use" in m])

       response = await client.messages.create(model=model, messages=messages, **kwargs)

       audit_log.info("llm_response",
           request_id=request_id, model=response.model,
           output_tokens=response.usage.output_tokens,
           stop_reason=response.stop_reason,
           tools_called=[c.name for c in response.content if c.type == "tool_use"])

       return response
   ```

6. **GPU/inference workload isolation**:
   ```yaml
   # Pod security for inference pods
   apiVersion: v1
   kind: Pod
   spec:
     securityContext:
       runAsNonRoot: true
       runAsUser: 65534
       fsGroup: 65534
       seccompProfile:
         type: RuntimeDefault
     containers:
       - name: vllm
         securityContext:
           allowPrivilegeEscalation: false
           readOnlyRootFilesystem: true
           capabilities:
             drop: ["ALL"]
         resources:
           requests:
             nvidia.com/gpu: 1
           limits:
             nvidia.com/gpu: 1
             memory: 32Gi
         volumeMounts:
           - name: model-cache
             mountPath: /models
             readOnly: true
           - name: tmp
             mountPath: /tmp
     volumes:
       - name: model-cache
         persistentVolumeClaim:
           claimName: model-cache-pvc
           readOnly: true
       - name: tmp
         emptyDir:
           sizeLimit: 5Gi
   ```

## Decision tree

```
IF deploying self-hosted model (vLLM, TGI, Ollama):
  → Network isolate (step 1)
  → Read-only model volume (step 6)
  → No direct internet access from inference pods
IF using external LLM API (OpenAI, Anthropic):
  → File-mounted secrets, never env vars (step 2)
  → Rate limit per user/team (step 3)
  → Audit log every call (step 5)
IF fine-tuning or training:
  → Validate training data integrity (step 4)
  → Air-gap training infra from production
  → Sign output model artifacts
IF compliance requirement (SOC2, ISO):
  → Ensure audit logs are immutable (ship to Loki, retain 90d)
  → Document data flow (what data reaches the model)
  → Implement access controls per model endpoint
```

## Anti-patterns

- ❌ LLM API keys in environment variables (visible in pod describe, crash dumps)
- ❌ Inference pods with internet egress (model can be exfiltrated)
- ❌ No rate limiting (runaway agent = $10k bill in minutes)
- ❌ Training on unvalidated external data (poisoning vector)
- ❌ Same network segment for inference and general workloads
- ❌ No audit trail of who called which model with what
- ❌ GPU pods running as root with writable filesystem

## Related skills

- `ai-agent-security` — agent-level permission scoping
- `llm-app-security` — application-layer protections
- `model-supply-chain-security` — model provenance and integrity
- `mcp-server-security` — securing tool-calling interfaces
- `external-secrets-aws-sm` — secret management patterns
