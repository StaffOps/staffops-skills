---
name: model-registry-governance
description: "Use when managing model lifecycle governance — tracking which models are deployed where, version control for model artifacts, approval workflows for model promotion, deprecation policies, and compliance documentation for model usage across the organization."
---
# Model Registry Governance

## When to use

- Tracking which LLM/ML models are deployed in which environments
- Implementing approval workflows for promoting models to production
- Enforcing deprecation timelines when providers sunset model versions
- Compliance requirements for documenting model usage (EU AI Act, SOC2)
- Multiple teams using different model versions inconsistently
- Evaluating whether to adopt a new model version org-wide

## When NOT to use

- Model serving infrastructure (use `llmops-platform-engineering`)
- Model signing and provenance (use `model-supply-chain-security`)
- Cost optimization per model (use `llm-cost-optimization`)
- Quality evaluation of model outputs (use `agent-evals`)

## Steps

1. **Define model registry schema**:
   ```yaml
   # registry/models.yaml — single source of truth
   models:
     claude-sonnet-4-20250514:
       provider: anthropic
       type: api  # api | self-hosted | fine-tuned
       status: approved  # candidate | approved | deprecated | banned
       approved_date: "2025-02-01"
       approved_by: platform-team
       environments: [dev, hml, prd]
       use_cases: [generation, analysis, code-review]
       cost_tier: standard
       context_window: 200000
       deprecation_date: null
       successor: null
       compliance:
         data_classification: internal  # public | internal | confidential | restricted
         data_residency: us-east-1
         pii_allowed: false  # Can PII be sent to this model?

     claude-3-5-haiku-20241022:
       provider: anthropic
       type: api
       status: approved
       environments: [dev, hml, prd]
       use_cases: [classification, extraction, routing]
       cost_tier: cheap
       compliance:
         data_classification: internal
         pii_allowed: false

     gpt-4-turbo:
       provider: openai
       type: api
       status: deprecated
       deprecation_date: "2025-06-01"
       successor: gpt-4o
       migration_guide: "docs/migrations/gpt4-to-gpt4o.md"

     llama-3.1-8b:
       provider: meta (self-hosted)
       type: self-hosted
       status: approved
       environments: [dev, hml]  # Not yet in prd
       hosting: vllm on ai-inference namespace
       use_cases: [classification, low-latency-routing]
       compliance:
         data_classification: confidential  # PII stays in-house
         pii_allowed: true
   ```

2. **Model promotion workflow**:
   ```yaml
   # promotion-gates.yaml
   promotion_workflow:
     candidate_to_approved:
       gates:
         - eval_score: ">= 0.85 on standard golden dataset"
         - cost_analysis: "within 20% of current model's cost for same workload"
         - security_review: "no new risk vs current model"
         - compliance_review: "data residency + PII handling documented"
       approvers: [platform-lead, security-lead]
       evidence_required:
         - eval_report_url
         - cost_comparison_url
         - security_review_ticket

     approved_to_production:
       gates:
         - canary_period: "7 days in HML with no regressions"
         - rollback_plan: documented
       approvers: [platform-lead]
   ```

3. **Deprecation enforcement** — automated alerts:
   ```python
   # scripts/check_deprecations.py — run weekly in CI
   import yaml
   from datetime import date, timedelta

   registry = yaml.safe_load(open("registry/models.yaml"))
   today = date.today()

   for model_id, config in registry["models"].items():
       if config["status"] == "deprecated":
           dep_date = date.fromisoformat(config["deprecation_date"])
           days_left = (dep_date - today).days

           if days_left <= 0:
               print(f"🚨 OVERDUE: {model_id} deprecated {-days_left} days ago!")
               print(f"   Successor: {config.get('successor', 'NONE')}")
               print(f"   Migration: {config.get('migration_guide', 'MISSING')}")
           elif days_left <= 30:
               print(f"⚠️  WARNING: {model_id} deprecated in {days_left} days")
           elif days_left <= 90:
               print(f"ℹ️  NOTICE: {model_id} deprecated in {days_left} days")
   ```

4. **Usage tracking** — who's using what:
   ```python
   # Query from agent-observability metrics
   # Which teams use which models?
   USAGE_QUERY = """
   sum by (team, model) (
     increase(gen_ai_requests_total[7d])
   ) > 0
   """

   # Find usage of deprecated models
   DEPRECATED_USAGE_QUERY = """
   sum by (team, model) (
     rate(gen_ai_requests_total{model=~"gpt-4-turbo|claude-2.*"}[1d])
   ) > 0
   """
   ```

5. **Compliance documentation template**:
   ```yaml
   # compliance/model-card-template.yaml
   model_card:
     model_id: ""
     purpose: "What business problem does this model solve?"
     data_handling:
       input_data_types: []  # What data is sent to the model?
       output_data_types: []  # What data comes back?
       pii_categories: []  # Which PII types, if any?
       data_retention: "none"  # Does the provider retain data?
       data_residency: ""  # Where is inference processed?
     risk_assessment:
       risk_level: ""  # low | medium | high
       failure_mode: "What happens if the model is wrong?"
       human_oversight: "How is output validated?"
       bias_considerations: ""
     monitoring:
       quality_metrics: []  # How is quality tracked?
       alert_thresholds: {}  # When does degradation trigger action?
     approvals:
       - approver: ""
         date: ""
         conditions: ""
   ```

6. **Automated compliance checks in CI**:
   ```yaml
   # .gitlab-ci.yml
   model-governance-check:
     stage: pre-build
     script:
       - python scripts/check_deprecations.py
       - python scripts/check_model_approved.py  # Verify model in code is in registry
       - python scripts/check_compliance_card.py  # Verify model card exists
     rules:
       - if: $CI_MERGE_REQUEST_SOURCE_BRANCH_NAME
         changes: ["**/*llm*", "**/*model*", "**/prompts/**"]
   ```

## Decision tree

```
IF adopting a new model (never used in org before):
  → Create registry entry with status "candidate"
  → Run agent-evals against golden dataset
  → Complete compliance model card
  → Submit for approval (security + platform leads)
  → After approval: status → "approved"

IF provider announces model deprecation:
  → Update registry: status → "deprecated", set date
  → Identify all teams using it (usage query, step 4)
  → Notify teams, provide migration guide
  → Set successor model in registry
  → After deprecation date: status → "banned" (gateway rejects)

IF team wants to use a model not in registry:
  → Check if it's a known model → add to registry as candidate
  → Unknown model → require evaluation + compliance review first
  → Never allow unregistered models in production

IF compliance audit requested:
  → Export model cards for all approved models
  → Show usage by team + environment
  → Demonstrate approval workflow evidence
```

## Anti-patterns

- ❌ No registry (teams use whatever model, no visibility)
- ❌ Registry exists but never enforced (models used without approval)
- ❌ Deprecated models used indefinitely (no enforcement mechanism)
- ❌ No successor documented when deprecating (teams stuck)
- ❌ Compliance documentation written once, never updated
- ❌ Fine-tuned models deployed without provenance tracking
- ❌ No usage data (can't tell who's affected by deprecation)

## Related skills

- `model-supply-chain-security` — provenance and integrity of model artifacts
- `llmops-platform-engineering` — platform that enforces registry policies
- `agent-evals` — quality evaluation for model promotion decisions
- `llm-cost-optimization` — cost comparison between model versions
