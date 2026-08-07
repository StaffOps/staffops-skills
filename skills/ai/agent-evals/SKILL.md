---
name: agent-evals
description: "Use when building golden-dataset regression suites to measure agent/skill correctness over time, designing rubrics for graded evaluation, setting release gates based on eval scores, or deciding whether a prompt/tool change improved or degraded quality."
---
# Agent Evals

## When to use

- Before shipping a change to an agent's prompt, tool set, or skill instructions
- When specific failure modes recur — turn each into a permanent regression case
- When onboarding a new agent capability and wanting a repeatable quality bar
- When comparing model versions (GPT-4o vs Claude Sonnet vs local) on the same task set
- When a skill has >10 real usage samples available for golden dataset creation

## When NOT to use

- One-off wording tweaks with no behavioral surface
- Adversarial/security testing (use `ai-red-teaming` instead)
- Measuring latency/cost (use `agent-observability` + `llm-cost-optimization`)
- Evaluating retrieval quality specifically (use `rag-observability-evals`)

## Steps

1. **Source golden cases from real interactions** (never from memory):
   ```bash
   # Export past agent sessions, redact PII
   jq '.messages[] | select(.role == "user")' sessions/*.json \
     | grep -v "password\|secret\|token" > raw_cases.jsonl
   ```

2. **Structure each case** with input + expected output + rubric:
   ```yaml
   # evals/cases/ticket-triage-001.yaml
   id: ticket-triage-001
   input: "Pod CrashLoopBackOff in ns payments, OOMKilled 3x in 10min"
   expected_behavior: "Identifies OOM as root cause, checks resource limits, suggests increase"
   rubric:
     - criterion: "Identifies OOMKilled"
       weight: 0.4
     - criterion: "Checks current memory limits"
       weight: 0.3
     - criterion: "Proposes actionable fix"
       weight: 0.3
   tags: [k8s, troubleshooting, common]
   ```

3. **Build the eval runner** (Python, minimal):
   ```python
   # evals/run_eval.py
   import yaml, json, sys
   from pathlib import Path
   from openai import OpenAI  # or anthropic

   def grade(response: str, rubric: list[dict], grader_model="gpt-4o-mini") -> float:
       prompt = f"Grade this response against criteria. Return JSON {{scores: [0-1]}}.\n\nResponse: {response}\n\nCriteria: {json.dumps(rubric)}"
       result = OpenAI().chat.completions.create(
           model=grader_model,
           messages=[{"role": "user", "content": prompt}],
           response_format={"type": "json_object"}
       )
       scores = json.loads(result.choices[0].message.content)["scores"]
       weights = [r["weight"] for r in rubric]
       return sum(s * w for s, w in zip(scores, weights))

   cases = list(Path("evals/cases").glob("*.yaml"))
   results = []
   for case_file in cases:
       case = yaml.safe_load(case_file.read_text())
       # Run agent under test
       response = run_agent(case["input"])
       score = grade(response, case["rubric"])
       results.append({"id": case["id"], "score": score})
       print(f"{case['id']}: {score:.2f}")

   avg = sum(r["score"] for r in results) / len(results)
   print(f"\nOverall: {avg:.2f}")
   sys.exit(0 if avg >= 0.85 else 1)  # Release gate
   ```

4. **Set the release gate threshold**:
   ```yaml
   # evals/config.yaml
   thresholds:
     overall_min: 0.85        # Average across all cases
     per_case_min: 0.60       # No single case below this
     regression_tolerance: 0.05  # Max allowed drop from baseline
   baseline_file: evals/baseline.json  # Previous run scores
   ```

5. **Run in CI** (pre-merge):
   ```yaml
   # .gitlab-ci.yml
   agent-eval:
     stage: test
     image: python:3.11-slim
     script:
       - pip install -q openai pyyaml
       - python evals/run_eval.py
     rules:
       - if: $CI_MERGE_REQUEST_SOURCE_BRANCH_NAME =~ /^feat\//
         changes: ["prompts/**", "skills/**", "agents/**"]
   ```

6. **Maintain the baseline** — update after each accepted release:
   ```bash
   python evals/run_eval.py --save-baseline evals/baseline.json
   ```

## Decision tree

```
IF change touches prompt/skill/tool-set:
  IF golden dataset exists for that capability:
    → Run eval suite, compare to baseline
    IF score >= threshold AND no regression > tolerance:
      → Ship
    ELSE:
      → Iterate on change until passing
  ELIF capability is new:
    → Create 5-10 golden cases BEFORE shipping
    → Run eval, establish baseline
  ELSE (minor wording tweak, no behavioral change):
    → Skip eval, note in commit why
ELIF change is model swap (e.g., gpt-4o → claude-sonnet):
  → Run FULL eval suite on both, compare scores side by side
```

## Anti-patterns

- ❌ Writing eval cases from imagination instead of real usage (fantasy != production)
- ❌ Binary pass/fail without weighted rubric (hides partial improvements)
- ❌ Running evals manually "when I remember" instead of in CI
- ❌ Same person writes the agent AND the eval cases (blind spots transfer)
- ❌ Golden dataset never updated (stale cases measure old behavior)
- ❌ Using the production model as the grader for its own output (self-grading bias)
- ❌ Threshold set at 1.0 (no eval is perfect; 0.85-0.90 is realistic)
- ❌ Conflating adversarial red-team cases with golden correctness cases

## Related skills

- `ai-red-teaming` — adversarial testing (different scoring posture)
- `agent-observability` — emit metrics from eval runs for tracking over time
- `rag-observability-evals` — specialized retrieval + groundedness evals
- `llm-cost-optimization` — cost of running evals at scale
