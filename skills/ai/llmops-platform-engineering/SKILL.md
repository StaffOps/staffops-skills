---
name: llmops-platform-engineering
description: "Use when building the platform layer for LLM operations — API gateway for model routing, shared inference infrastructure, A/B model deployment, feature flags for AI capabilities, and providing golden-path templates for teams adopting LLM features."
---
# LLMOps Platform Engineering

## When to use

- Building shared LLM infrastructure for multiple teams (API gateway, model proxy)
- Deploying model serving infrastructure (vLLM, TGI, Ollama) on Kubernetes
- Implementing A/B testing between model versions
- Providing golden-path templates for teams adopting LLM features
- Setting up model routing, fallback, and load balancing across providers
- Managing shared prompt registries and versioning

## When NOT to use

- Single-team, single-model usage (just call the API directly)
- Optimizing costs for one agent (use `llm-cost-optimization`)
- Evaluating model quality (use `agent-evals`)
- Security hardening of AI infrastructure (use `ai-security-hardening`)

## Steps

1. **LLM API Gateway** — single entry point for all teams:
   ```python
   # gateway/main.py — FastAPI proxy with routing, auth, metering
   from fastapi import FastAPI, Request, HTTPException
   from opentelemetry import trace

   app = FastAPI(title="LLM Gateway")
   tracer = trace.get_tracer("llm.gateway")

   MODEL_BACKENDS = {
       "claude-sonnet": {"provider": "anthropic", "endpoint": "https://api.anthropic.com"},
       "gpt-4o": {"provider": "openai", "endpoint": "https://api.openai.com"},
       "local-llama": {"provider": "vllm", "endpoint": "http://vllm.ai-inference.svc:8000"},
   }

   @app.post("/v1/chat/completions")
   async def proxy_completion(request: Request):
       body = await request.json()
       model = body.get("model", "claude-sonnet")
       team = request.headers.get("X-Team-ID", "unknown")

       with tracer.start_as_current_span("gateway.route") as span:
           span.set_attribute("team", team)
           span.set_attribute("model_requested", model)

           # Check budget
           if not await check_team_budget(team, model):
               raise HTTPException(429, "Team budget exhausted")

           # Route to backend
           backend = MODEL_BACKENDS[model]
           response = await forward_to_backend(backend, body)

           # Meter usage
           await record_usage(team, model, response.usage)
           return response
   ```

2. **Self-hosted model deployment** (vLLM on K8s):
   ```yaml
   # helm values for vLLM deployment
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: vllm-llama
     namespace: ai-inference
   spec:
     replicas: 2
     template:
       spec:
         containers:
           - name: vllm
             image: vllm/vllm-openai:latest
             args:
               - "--model=/models/Meta-Llama-3.1-8B-Instruct"
               - "--tensor-parallel-size=1"
               - "--max-model-len=8192"
               - "--gpu-memory-utilization=0.90"
             ports:
               - containerPort: 8000
             resources:
               requests:
                 nvidia.com/gpu: 1
                 memory: 24Gi
               limits:
                 nvidia.com/gpu: 1
                 memory: 32Gi
             volumeMounts:
               - name: model-cache
                 mountPath: /models
                 readOnly: true
             readinessProbe:
               httpGet:
                 path: /health
                 port: 8000
               initialDelaySeconds: 120  # Model loading takes time
         volumes:
           - name: model-cache
             persistentVolumeClaim:
               claimName: model-cache-pvc
         tolerations:
           - key: nvidia.com/gpu
             operator: Exists
             effect: NoSchedule
   ---
   apiVersion: v1
   kind: Service
   metadata:
     name: vllm
   spec:
     ports:
       - port: 8000
         targetPort: 8000
     selector:
       app: vllm-llama
   ```

3. **A/B model routing** (canary new models):
   ```python
   # Feature flag based routing
   import random

   AB_CONFIG = {
       "code-review": {
           "control": {"model": "claude-sonnet-4-20250514", "weight": 80},
           "treatment": {"model": "claude-opus-4-20250514", "weight": 20},
       }
   }

   def select_model_ab(task: str, session_id: str) -> tuple[str, str]:
       """Returns (model_name, variant: 'control'|'treatment')."""
       config = AB_CONFIG.get(task)
       if not config:
           return "claude-sonnet-4-20250514", "default"

       # Deterministic assignment by session (consistent experience)
       hash_val = int(hashlib.md5(session_id.encode()).hexdigest(), 16) % 100
       if hash_val < config["control"]["weight"]:
           return config["control"]["model"], "control"
       else:
           return config["treatment"]["model"], "treatment"
   ```

4. **Prompt registry** — versioned, shared prompts:
   ```yaml
   # prompts/registry.yaml
   prompts:
     ticket-classification:
       version: "2.1.0"
       template: |
         Classify this support ticket into exactly one category.
         Categories: {categories}
         Ticket: {ticket_text}
         Output JSON: {"category": "...", "confidence": 0.0-1.0}
       variables: [categories, ticket_text]
       model_tier: cheap
       owner: platform-team
       last_eval_score: 0.92

     incident-summary:
       version: "1.3.0"
       template: |
         Summarize this incident for a post-mortem.
         Timeline: {timeline}
         Logs: {relevant_logs}
         Format: Impact → Root Cause → Fix → Prevention
       variables: [timeline, relevant_logs]
       model_tier: standard
       owner: sre-team
       last_eval_score: 0.88
   ```

5. **Golden-path template for teams** (starter kit):
   ```
   templates/llm-service/
   ├── Dockerfile
   ├── src/
   │   ├── main.py              # FastAPI with /health, /ready
   │   ├── llm_client.py        # Gateway client with retry/fallback
   │   ├── models.py            # Pydantic schemas for I/O
   │   └── observability.py     # OTel setup with GenAI attributes
   ├── tests/
   │   └── test_llm_client.py   # Mocked LLM responses
   ├── evals/
   │   ├── cases/               # Golden dataset
   │   └── run_eval.py
   ├── helm/
   │   └── values.yaml          # K8s deployment with IRSA, secrets
   └── .gitlab-ci.yml           # Build + eval + deploy pipeline
   ```

6. **Shared observability dashboard**:
   ```json
   // Grafana dashboard panels (platform-wide view)
   {
     "panels": [
       {"title": "Total LLM Spend by Team", "type": "piechart", "query": "sum(gen_ai_cost_total) by (team)"},
       {"title": "Requests/sec by Model", "type": "timeseries", "query": "sum(rate(gen_ai_requests_total[5m])) by (model)"},
       {"title": "P95 Latency by Model", "type": "timeseries", "query": "histogram_quantile(0.95, rate(gen_ai_request_duration_seconds_bucket[5m]))"},
       {"title": "Cache Hit Rate", "type": "stat", "query": "sum(rate(llm_cache_hits_total[5m])) / sum(rate(llm_cache_hits_total[5m]) + rate(llm_cache_misses_total[5m]))"},
       {"title": "Error Rate by Provider", "type": "timeseries", "query": "sum(rate(gen_ai_requests_total{status=\"error\"}[5m])) by (provider)"}
     ]
   }
   ```

## Decision tree

```
IF multiple teams consuming LLM APIs:
  → Build shared gateway (step 1) — centralizes auth, metering, routing
IF monthly spend > $5k across teams:
  → Self-host for high-volume low-complexity tasks (step 2)
  → Keep API for complex/infrequent tasks
IF testing new model version:
  → A/B route (step 3) + run agent-evals on both variants
IF teams duplicating prompt engineering effort:
  → Prompt registry (step 4) with versioning and eval scores
IF onboarding new team to LLM usage:
  → Provide golden-path template (step 5) — don't let them start from scratch
IF no visibility into cross-team LLM usage:
  → Shared dashboard (step 6) — can't optimize what you can't see
```

## Anti-patterns

- ❌ Every team managing their own API keys (no central audit, budget, or routing)
- ❌ No shared patterns (each team re-invents prompt engineering, caching, error handling)
- ❌ Self-hosting without dedicated ops capacity (becomes someone's side project)
- ❌ A/B testing without quality evals (can't tell if new model is better)
- ❌ No budget limits per team (shared platform = tragedy of the commons)
- ❌ Golden path that's too complex (teams skip it, go direct to API)

## Related skills

- `llm-cost-optimization` — individual workload cost reduction
- `llm-caching` — caching layer within the gateway
- `ai-security-hardening` — securing the inference infrastructure
- `agent-observability` — GenAI span instrumentation
- `model-registry-governance` — tracking which models are deployed where
