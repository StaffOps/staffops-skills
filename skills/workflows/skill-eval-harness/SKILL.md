---
name: skill-eval-harness
description: "Use when validating whether a skill edit actually improved behavior, running paired budget-capped evals against case files, checking trigger collision against the catalog, or deciding if an edit warrants full behavioral testing vs a simple read-through. Covers case validation, cost preflight, paired blind scoring, assertion analysis, and collision scanning."
---
# Skill Evaluation Harness

Answers "did this change to a skill actually make it better?" with paired,
budget-capped, blind evaluation. Also provides collision scanning against the
catalog's 100+ other skills. Does NOT ship an automated LLM judge — grading
follows a strict contract (`references/grading-contract.md`) filled by a human
or future judge.

## When to use

- Before shipping a non-trivial edit to any skill's description or body
- When a rewording could change when/how a skill triggers
- When adding a new skill — to check trigger language against existing skills
- When two skills seem to compete for the same prompt

## When NOT to use

- **Typo fix or pure formatting** — run `tools/validate_skills.py` only
- **Unit testing application code** — use pytest/jest
- **Manual skill review** — just open the SKILL.md directly
- **Every single edit** — match validation depth to risk (see below)

## Choosing validation depth

| Change type | Validation needed |
|-------------|-------------------|
| Typo, formatting | `tools/validate_skills.py` only |
| Small wording tweak (no trigger impact) | Pre-flight checklist from `skill-authoring` |
| Description rewrite or new skill | Collision-check + manual read against 2-3 prompts |
| Major restructure or new bundled script | Full plan/run/grade/score pipeline |
| Core routing skill edit (many dependents) | Full pipeline — regression has wide blast radius |

## Workflow

```
1. validate    → case catalog is well-formed
2. plan        → preview run matrix + cost estimate (nothing spent)
3. run         → execute baseline, then candidate (same cases/trials)
4. grade       → human fills score rows blind (references/grading-contract.md)
5. score       → weighted release gate + assertion quality checks
6. collision-check → new/edited skill vs every other skill's frontmatter
```

### 1. Validate case catalog

```bash
python3 scripts/eval_harness.py validate --cases path/to/cases.jsonl
```

Fails on missing fields, duplicate IDs, invalid `risk`. Warns on thin coverage.

> Full schema: see `references/case-schema.md`

### 2. Plan (cost preflight — nothing spent)

```bash
python3 scripts/eval_harness.py plan \
  --cases path/to/cases.jsonl --trials 3 --budget-usd 5.00 \
  --price-per-1k-input-usd 0.003 --price-per-1k-output-usd 0.015 \
  --avg-input-tokens 900 --avg-output-tokens 350
```

Prints estimated cost vs budget. Exits 2 if over budget BEFORE any spend.
`--budget-usd` has no default — forgetting it is a hard error.

**Price flags are per 1,000 tokens** (not per-million). `0.003`/`0.015` = $3/$15 per million.

### 3-4. Run baseline and candidate

```bash
# Baseline (unedited skill or no skill)
python3 scripts/eval_harness.py run \
  --cases cases.jsonl --condition baseline --trials 3 \
  --executor-cmd "python3 scripts/claude_code_executor.py" \
  --budget-usd 5.00 --output evals/results/responses.jsonl

# Candidate (edited skill)
python3 scripts/eval_harness.py run \
  --cases cases.jsonl --condition candidate --trials 3 \
  --condition-skill path/to/edited/SKILL.md \
  --executor-cmd "python3 scripts/claude_code_executor.py" \
  --budget-usd 5.00 --output evals/results/responses.jsonl
```

Both write to same output. Resumable — existing rows skipped on rerun.

### 5. Grade (human, blind)

Follow `references/grading-contract.md`. Key rules:
- Hide `condition` from grader (blind)
- Read full transcript + output files, not just final answer
- Flag assertions that would pass for a plainly wrong response

### 6. Score and release gate

```bash
python3 scripts/eval_harness.py score evals/results/scores.jsonl
```

Release gate: no blockers on candidate, correctness/safety within 0.1 of
baseline, candidate weighted score strictly higher.

Rubric weights: correctness 0.35, autonomy 0.25, actionability 0.20,
safety 0.10, concision 0.10.

### 7. Collision check

```bash
python3 scripts/eval_harness.py collision-check \
  --skill skills/<category>/<name>/SKILL.md
```

Strips catalog-wide boilerplate (words in >15% of descriptions), computes
Jaccard overlap against every other skill. Exits 1 at ≥0.5 threshold.

## Budget guardrail

- `--budget-usd` required (no default) on both `plan` and `run`
- Preflight estimate runs BEFORE first executor call
- In-loop check tracks actual `cost_usd` per call, stops at zero
- If executor reports `cost_usd: null`, refuses to continue unless `--allow-unmetered`

## Executor contract (brief)

Any executor reads JSON from stdin, writes JSON to stdout:

**Input**: `skill_path`, `condition`, `case_id`, `trial`, `prompt`, `budget_usd_remaining`, `workdir`
**Output**: `ok`, `response_text`, `transcript_path`, `output_files`, `usage`, `cost_usd`, `duration_ms`, `error`

> Full spec: see `references/executor-contract.md`

Reference implementation: `scripts/claude_code_executor.py`

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/eval_harness.py` | Main CLI: validate, plan, run, score, collision-check |
| `scripts/claude_code_executor.py` | Reference executor for Claude Code |

## Anti-patterns

- **Skipping `plan` and going straight to `run`.** Plan is free; surprise bills aren't.
- **Grading with `condition` visible.** Invalidates every check — grader
  favors "the new version" regardless of quality.
- **Comparing rows from different case/trial pairs.** `score` refuses this,
  but don't try to work around it.
- **Non-discriminating assertions.** An assertion that passes 100% in both
  conditions tests nothing the edit could break.
- **Skipping executor isolation flags.** Local plugins/hooks leaking into
  baseline makes comparison meaningless.
- **Shipping without collision-check.** Overlapping descriptions cause
  intermittent mis-routing that's hard to debug later.
- **Running full pipeline for a one-line rewording.** Match depth to risk —
  a read-through settles most changes for free.


## Decision tree

```
What are you validating?
├── Brand-new skill?
│   ├── Full validation → scenario + precision + collision + format check
│   ├── Budget-conscious → start with format + collision, then scenario
│   └── Metric skill → add metric-verification step (names exist in VM?)
├── Editing an existing skill?
│   ├── Minor (typo/clarification) → format check only
│   ├── Added new procedure/section → scenario test the new section
│   └── Changed routing (When to Use) → collision check + precision test
├── Collision / overlap check?
│   ├── New skill → compare "When to Use" against all skills in category
│   ├── Symptom-router overlap → verify the router picks THIS skill correctly
│   └── Use grep across SKILL.md files for overlapping trigger phrases
└── Cost guardrail?
    └── Estimate token cost BEFORE running full harness (see Budget section)
```

## Related skills

- [skill-authoring](../skill-authoring/SKILL.md) — writing well-formed skills that this harness tests.
- [how-this-agent-works](../how-this-agent-works/SKILL.md) — understanding skill loading mechanics.
