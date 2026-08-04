---
name: skill-eval-harness
description: "Run paired, budget-capped evals to validate a skill change."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [skill, eval, harness, testing, benchmark, workflows]
    category: workflows
    related_skills: [how-this-agent-works, spec-writing]
---
# Skill Evaluation Harness

A harness-agnostic way to answer "did this change to a skill actually make
it better?" for any skill in this catalog. It covers case-file validation, a
pluggable executor contract (so the harness is not wired to one CLI), a
mandatory cost preflight before any run starts, a paired and blind release
gate, mechanical assertion-quality checks, and a skill-collision scan
against the rest of the catalog. It deliberately does **not** ship an
automated LLM judge — deciding whether a response satisfies a criterion is a
judgment call, and this pass documents that step as a strict contract
(`references/grading-contract.md`) that a human or a future judge fills in,
rather than encoding it half-heartedly.

## When to Use

Use before shipping a non-trivial edit to any skill's `description` or body
— a rewording that could change when it triggers, a restructure of the
instructions, or a new script bundled into it — and this catalog currently
has no other way to tell whether that edit helped or hurt. Also use when
adding a brand-new skill, to check its trigger language against the other
100+ skills already in `skills/` before it ships.

Do not reach for this on a typo fix or a pure formatting change with no
behavioral surface — run `tools/validate_skills.py` for those, per
`CONTRIBUTING.md`.

## Where this comes from

This generalizes two existing tools rather than picking one:

- **ayghri/i-have-adhd** (`evals/scripts/run_evals.py`, `evals/rubric.md`,
  `evals/README.md`) contributed the outer loop: a weighted five-dimension
  rubric, a release gate with tolerance bands, strict pairing so baseline
  and candidate can only be compared on identical case/trial rows, a
  resumable run loop, retries, and a hard rule that an executor which
  cannot report dollar cost gets rejected unless the operator opts in.
- **anthropics/skills' skill-creator** (`agents/grader.md`,
  `agents/analyzer.md`, `skill-creator/references/schemas.md`) contributed the judging
  discipline: read the whole transcript and every output file, not just the
  final answer; verify substance over surface compliance; and critique the
  eval's own assertions for being non-discriminating.

Four places this design goes further than either source, because a 100+
skill catalog has requirements neither single-skill tool anticipated:

1. **Pluggable executor, not a hardcoded CLI.** i-have-adhd's runner builds
   `claude`/`codex` argv directly inside `run_evals.py`; adding a third
   agent means editing the runner. This harness defines a JSON-over-stdio
   contract (`references/executor-contract.md`) any program can implement,
   with one reference implementation for Claude Code
   (`scripts/claude_code_executor.py`).
2. **Merged grading pipeline.** i-have-adhd's blind/paired/budget-capped/
   resumable mechanics are the outer loop; skill-creator's
   read-everything-and-self-critique discipline is the judging step that
   fills each score row. Neither alone covers both.
3. **A mandatory, visible-before-any-run cost gate.** This repository's own
   history has a commit literally titled "audit... before hitting API spend
   limit" (`7c99c79`) — 15 of 16 parallel subagents burned through a spend
   limit mid-audit. `plan` and `run` both require `--budget-usd` (no
   default) and refuse to invoke an executor even once if the token-based
   preflight estimate exceeds it.
4. **A skill-collision check.** Neither source tool works inside a catalog
   large enough to have many similarly-named skills (this repo currently
   has dozens of `*-metrics` skills alone). `collision-check` compares one
   skill's description and tags against every other skill's, after
   stripping catalog-wide boilerplate phrasing, to catch overlapping
   trigger language before it ships.

## Case file and score row formats

See `references/case-schema.md` for the full field-by-field schema. In
short: cases live in a JSONL file (`id`, `category`, `prompt`, `risk`,
`criteria`), and each judged response is one score row carrying the five
weighted rubric dimensions (`correctness` 0.35, `autonomy` 0.25,
`actionability` 0.20, `safety` 0.10, `concision` 0.10), a `blocker` flag, and
an optional `assertions` array with per-criterion evidence. A tiny example
catalog lives at `references/examples/cases.sample.jsonl`.

## Workflow

```
1. validate        -- catalog is well-formed (references/case-schema.md)
2. plan             -- preview the run matrix + cost estimate, nothing spent yet
3. run (baseline)   -- execute the unedited skill (or no skill, for a new one)
4. run (candidate)  -- execute the edited skill, same cases/trials/executor
5. grade            -- human or future judge fills in score rows (references/grading-contract.md)
6. score             -- weighted release gate + assertion-quality checks
7. collision-check  -- new/edited skill vs. every other skill's frontmatter
```

### 1. Validate the case catalog

```bash
python3 scripts/eval_harness.py validate --cases path/to/cases.jsonl
```

Fails on missing fields, duplicate `id`s, an invalid `risk` value, or empty
`criteria`. Prints non-fatal warnings when the catalog has no `high`-risk
case or only one `category` — a thin catalog can pass the schema check and
still tell you nothing useful about a regression.

### 2. Plan the run and see the cost before spending anything

```bash
python3 scripts/eval_harness.py plan \
  --cases path/to/cases.jsonl --trials 3 --budget-usd 5.00 \
  --price-per-1k-input-usd 0.003 --price-per-1k-output-usd 0.015 \
  --avg-input-tokens 900 --avg-output-tokens 350
```

The price flags are **per 1,000 tokens**, not per call and not per million —
`0.003`/`0.015` above corresponds to a model priced at $3/$15 per million
tokens. Get this unit wrong (e.g. pasting a per-million price directly into
a per-1k flag) and the estimate inflates by 1000x, which will make `plan`
refuse a run that would actually have been cheap.

Prints a preflight cost estimate (`remaining calls x est. cost/call`)
against `--budget-usd`, then the full paired run matrix as JSONL. `plan`
exits 2 when the estimate is over budget even though it never calls an
executor — that is the visible-before-any-run guardrail from design goal 3.
`--budget-usd` has no default on purpose: forgetting it is a hard error, not
a silent 25-dollar ceiling. Against the shipped `references/examples/cases.sample.jsonl`
(4 cases) this example estimates roughly $0.19 for the full baseline+candidate
matrix and comfortably clears the $5.00 cap; get the price units wrong and
you will see `OVER BUDGET` instead — that is the gate working, not a bug.

### 3-4. Run baseline and candidate through the same executor

```bash
python3 scripts/eval_harness.py run \
  --cases path/to/cases.jsonl --condition baseline --trials 3 \
  --executor-cmd "python3 scripts/claude_code_executor.py" \
  --budget-usd 5.00 --output evals/results/responses.jsonl

python3 scripts/eval_harness.py run \
  --cases path/to/cases.jsonl --condition candidate --trials 3 \
  --condition-skill path/to/the/edited/SKILL.md \
  --executor-cmd "python3 scripts/claude_code_executor.py" \
  --budget-usd 5.00 --output evals/results/responses.jsonl
```

Both write to the same `--output` file. `run` repeats the `plan` preflight
gate before touching the executor, then tracks actual reported `cost_usd`
per call and stops when the remaining budget hits zero. Rows already
present in `--output` for the same `(case_id, trial, condition, runner)` are
skipped on rerun — a failed run halfway through is resumable, not a
restart-from-zero. See `references/executor-contract.md` for the exact
request/response JSON any executor must speak, and swap `--executor-cmd`
for a different program to test a different agent entirely.

### 5. Grade

This step is a defined contract, not automation shipped here — see
`references/grading-contract.md`. The short version: judge every response
**blind** (hide `condition` from whoever assigns scores), read the whole
transcript and output files rather than trusting the final answer alone,
and note in `eval_feedback` any assertion that would pass even for a
plainly wrong response.

### 6. Score and apply the release gate

```bash
python3 scripts/eval_harness.py score evals/results/scores.jsonl
```

Requires `baseline` and `candidate` rows judged on identical
`(case_id, trial)` pairs — mismatched pairing raises an error rather than
silently comparing apples to oranges. Applies the same release gate as the
source rubric: no blocking findings on candidate, correctness and safety
each within 0.1 points of baseline, and candidate's weighted score strictly
higher. When score rows include `assertions`, it also reports
`assertion_analysis.non_discriminating` (a criterion that passed or failed
100% of the time in every condition — it never told the two apart) and
`assertion_analysis.flaky` (a criterion whose verdict changed across trials
for the same case and condition). Both are pure aggregation over already-
judged booleans; neither requires re-judging anything.

### 7. Check for trigger collisions against the rest of the catalog

```bash
python3 scripts/eval_harness.py collision-check --skill skills/apm-metrics/argocd-metrics/SKILL.md
```

Tokenizes the target skill's `description` and `tags`, strips tokens that
appear in more than 15% of every other skill's description (catalog-wide
phrasing like "diagnosing" or "use when" carries no signal — computed live
from the catalog, not a hardcoded stopword list, so it keeps working as
house style shifts), then reports Jaccard overlap against every other
skill, sorted highest first. Anything at or above `--fail-threshold`
(default 0.5) exits 1 and should be resolved — narrow the wording, or
confirm the two skills really are meant to compete for the same trigger and
one should win. This is the check neither source tool needed, because
neither operated inside a catalog with dozens of similarly-shaped skills
(the `*-metrics` family alone).

## Budget guardrail, in detail

`--budget-usd` is required with no default on both `plan` and `run` — the
CLI raises `argparse`'s missing-argument error rather than falling back to
a number nobody chose. The preflight check runs before the very first
executor invocation: it multiplies the number of not-yet-completed
`(case, trial)` rows by a per-call cost estimate derived from
`--price-per-1k-input-usd` / `--price-per-1k-output-usd` /
`--avg-input-tokens` / `--avg-output-tokens`, and refuses to start if that
projected total exceeds the budget. This is stricter than i-have-adhd's own
guardrail, which only checks the running total of *actually reported* cost
after each call — useful, and this harness keeps it as a second, in-loop
check, but it cannot stop a run before the first dollar is spent. The
preflight estimate can.

Separately, if every response from an executor reports `cost_usd: null`,
`run` refuses to continue past the first call unless `--allow-unmetered` is
passed explicitly — reach for that flag only when the executor's own
account has a hard cap enforced by its provider, not by this harness.

## Executor contract, in brief

Any executor reads one JSON object from stdin (`skill_path`, `condition`,
`case_id`, `trial`, `prompt`, `budget_usd_remaining`, `workdir`) and writes
one JSON object to stdout (`ok`, `response_text`, `transcript_path`,
`output_files`, `usage`, `cost_usd`, `duration_ms`, `error`). Full field
descriptions and the isolation requirements (why `--setting-sources ""` and
a pinned model matter) live in `references/executor-contract.md`.
`scripts/claude_code_executor.py` is the reference implementation; writing
a new one for a different agent means satisfying that one JSON shape, not
touching `eval_harness.py`.

## Scripts reference

| Script | Purpose |
| --- | --- |
| `scripts/eval_harness.py` | Main CLI: `validate`, `plan`, `run`, `score`, `collision-check`. |
| `scripts/claude_code_executor.py` | Reference executor implementing `references/executor-contract.md` for Claude Code. |

## Anti-patterns

- **Skipping `validate` and hand-editing the JSONL.** A malformed case
  silently drops out of the matrix instead of failing loudly — catch it
  before spending a call on it.
- **Running `run` without ever running `plan` first.** `plan` is free; a
  surprise bill is not. The preflight estimate in `run` is a safety net, not
  a replacement for reading the plan output.
- **Grading with the `condition` field visible.** This single mistake
  invalidates every other check in this harness — a grader who knows which
  response is "the new version" grades it more charitably regardless of
  quality.
- **Comparing baseline and candidate scored on different case/trial rows.**
  `score` refuses this outright (`_check_pairing`), because it is exactly
  how cherry-picked comparisons get made, intentionally or not.
- **Treating a non-discriminating assertion as a real pass.** An assertion
  that passes 100% of the time in both baseline and candidate is not
  evidence the candidate is fine — it is evidence the assertion is not
  testing anything the edit could have broken.
- **Skipping the isolation flags when writing a new executor.** An
  operator's own locally-enabled plugins, hooks, or memory leaking into the
  `baseline` condition makes the comparison measure the skill against
  itself. Keep `--setting-sources ""` (or the equivalent for a different
  CLI) and a pinned model in any executor you write.
- **Shipping a new skill without `collision-check`.** A description that
  overlaps heavily with an existing skill's trigger language causes
  intermittent mis-routing that is hard to notice until two skills start
  competing for the same prompt in production use.
- **Treating `score`'s output as the final word without reading
  `assertion_analysis`.** A candidate can beat the weighted release gate
  while every discriminating assertion is masked by non-discriminating ones
  padding the average — read the flagged assertions, not just the verdict.
