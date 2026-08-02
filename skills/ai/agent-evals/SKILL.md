---
name: agent-evals
description: "Build golden-dataset regression evals for agent quality."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [ai, eval, golden-dataset, rubric, regression-testing, quality-assurance]
    category: ai
    related_skills: [skill-eval-harness, skill-authoring, ai-red-teaming]
---
# Agent Evals

A methodology for building golden-dataset-based regression suites that
measure an agent's or skill's correctness and quality over time, using this
catalog's `skill-eval-harness` as the execution engine rather than a second,
bespoke runner. It covers what a golden dataset actually is, how to source
one responsibly, how to turn the harness's existing case schema and rubric
into a real grading contract instead of a single pass/fail, and how to read
its release gate to decide a change is safe to ship. It deliberately does
not cover adversarial or security testing -- finding a tool-abuse,
exfiltration, or scope-escalation bypass is `ai-red-teaming`'s job, built on
the same harness but scored under an opposite posture (a single bypass is a
finding to act on, not noise to average into a passing score).

## When to Use

- Before shipping a change to an agent's prompt, tool set, or a skill's
  instructions where "did this actually get better or worse at the task"
  cannot be answered by reading the diff alone.
- When a skill or agent has accumulated enough real usage that specific
  failure modes recur -- turn each one into a permanent case instead of
  re-discovering it manually next release.
- When onboarding a new agent capability and wanting a repeatable quality
  bar before it goes live, distinct from (and usually prior to) the
  adversarial pass `ai-red-teaming` runs against the same capability.
- Not for a one-off skill edit unlikely to change again, or a wording
  tweak with no behavioral surface -- see "When not to build a
  golden-dataset suite" below.

## What a golden dataset actually is

A golden dataset is a curated set of (input, expected-behavior) pairs
representative of how the agent is actually used -- not a set of synthetic
edge cases engineered to be hard. Synthetic adversarial edge cases are
`ai-red-teaming`'s attack catalog, a different discipline with a different
scoring posture; conflating the two produces a suite that scores well
against contrived gotchas while missing the boring, frequent request that
actually breaks in production.

Two responsible ways to source cases, neither of which is "write ten
examples from memory":

- **Sampled from real past interactions, redacted.** Pull transcripts
  (support threads, past agent sessions, ticket resolutions) that represent
  genuinely common requests, then strip anything sensitive before it enters
  a versioned, git-tracked case file: customer names, account identifiers,
  internal hostnames, secrets, and any org-specific data that
  `CONTRIBUTING.md`'s placeholder vocabulary exists to keep out of this
  catalog. A case file lives in Git forever -- redact at authoring time, not
  as a follow-up.
- **Hand-authored to cover known-important scenarios.** Three scenario
  shapes are worth deliberately covering rather than leaving to chance: the
  core supported task done the ordinary way, the case that is boring but
  high-frequency (most of an agent's real traffic is not exotic), and a
  specific regression that already happened once -- turning a bug report
  into a permanent case is cheaper than letting the same regression recur
  silently. `skill-eval-harness`'s own
  `references/examples/cases.sample.jsonl` models this: `direct-answer` and
  `concept-explanation` are ordinary-task cases, `real-ambiguity` encodes a
  specific failure mode (guessing instead of asking) worth watching for
  permanently.

Either way, `case-schema.md`'s coverage warning applies directly to a
quality suite, not only a security one: a catalog where every case is
`low` risk proves nothing about a regression that only shows up under a
`medium`- or `high`-risk scenario -- include at least one non-trivial case
per capability the suite is meant to protect.

## Rubric design: five weighted dimensions, not one pass/fail

A single pass/fail verdict on an open-ended agent response collapses
several independent failure modes into one bit: a response can be
factually correct but push work back onto the user that the agent should
have done itself, or correct and autonomous but bury the answer somewhere a
human has to hunt for it. `skill-eval-harness`'s score row
(`references/case-schema.md`) already encodes this as five weighted
dimensions instead of one flag: `correctness` (0.35), `autonomy` (0.25),
`actionability` (0.20), `safety` (0.10), `concision` (0.10). Reuse this
format rather than inventing a parallel rubric -- the weights are shared
across every skill's historical score files, and reweighting them for one
suite breaks trend comparisons across the catalog.

What makes this a good rubric instead of a bad one is not the weights
themselves but what each dimension catches that a single pass/fail would
miss:

| Dimension | Catches |
| --- | --- |
| `correctness` | The core failure mode a golden dataset exists to protect: is the technical content right, are required details preserved. |
| `autonomy` | A response that is factually fine but reflexively pushes agent-owned work back onto the user instead of doing it. |
| `actionability` | A correct answer buried in hedging or missing the concrete next step. |
| `safety` | Risk and ambiguity handled correctly -- weighted lower here than in an `ai-red-teaming` catalog, because exercising safety boundaries is not this suite's primary purpose. |
| `concision` | Filler that dilutes a correct answer without adding anything the user needed. |

`blocker` (per `case-schema.md`) is the one boolean in the row, and it
exists for a narrower reason than "this response scored low": it flags a
dangerous instruction, a material factual error, a broken output contract,
or an autonomy regression that blocks task completion. Any `blocker: true`
on a `candidate` row fails the release gate outright, independent of the
weighted score -- see the next section. Do not use `blocker` as a synonym
for "low score"; a correct-but-verbose response is a `concision` ding, not
a blocker.

Write each case's `criteria` (the array `score`'s `assertions` grade
against) as answer-shaped, not refusal-shaped -- "identifies X as the
cause" or "names the specific config field," not "does not do Y." That
contrast is the same one `ai-red-teaming` draws explicitly in its own
case-encoding section: a red-team `criteria` entry describes a safe refusal
boundary, a quality-eval `criteria` entry describes what a correct,
complete answer contains.

## Discriminating assertions: a criterion that always passes tests nothing

`grading-contract.md` names the mechanical check `score` runs whenever
score rows carry `assertions`: group every judged row by
`(case_id, assertion text)` across `baseline` and `candidate`, and flag any
assertion that passes 100% of the time in **both** conditions (or fails
100% of the time in both) as non-discriminating. It never told the two
versions apart, even though a pass-rate summary makes it look like signal.
This mechanizes the same observation `skill-eval-harness`'s design credits
to `anthropics/skills`' `skill-creator` grader: an assertion like "the
output mentions the customer's name" passes even for a response that got
the customer's *role* wrong, because it never checked the claim that
actually mattered ("Assertion 'Output is a PDF file' passes 100% in both
configurations - may not differentiate skill value.").

For a quality-eval suite specifically -- unlike `ai-red-teaming`'s cases,
where a 100%-pass safety-refusal criterion in both conditions is the
desired outcome, not a defect -- a non-discriminating assertion here is
close to a straightforward smell: either the criterion is too weak to fail
for a wrong answer, or the case itself is too easy to ever exercise the
failure mode it was written to catch. Sharpen or retire it before the next
run rather than letting it pad every future score's apparent pass rate.
`score` also reports `assertion_analysis.flaky` -- the same assertion, same
case, same condition, disagreeing across trials -- which for a quality
suite usually means the prompt is underspecified enough that the model's
answer genuinely varies, not that the grading itself was inconsistent.

## Regression gates: how `score` decides "safe to ship"

`skill-eval-harness`'s `score` subcommand is the actual release-gate logic
-- this skill points at it rather than re-describing generic before/after
comparison advice:

```bash
python3 skills/workflows/skill-eval-harness/scripts/eval_harness.py score evals/results/scores.jsonl
```

Three mechanics matter for deciding whether a candidate change is safe to
ship:

1. **Pairing is enforced, not assumed.** `score` requires `baseline` and
   `candidate` rows judged on identical `(case_id, trial)` pairs and raises
   an error on any mismatch instead of silently comparing whatever rows
   happen to exist. A candidate run missing three of the baseline's cases
   cannot be scored until those three are backfilled -- this is what stops
   a cherry-picked comparison from passing by omission.
2. **The gate itself**: no `blocker: true` on any `candidate` row,
   `correctness` and `safety` each within 0.1 points of `baseline`, and
   `candidate`'s weighted score strictly higher than `baseline`'s. All
   three conditions, not the weighted score alone -- a candidate that wins
   on the weighted average while regressing `safety` by 0.3 does not clear
   the gate.
3. **`assertion_analysis` is a required read, not optional detail.** A
   candidate can clear the weighted gate while every discriminating
   assertion is masked by non-discriminating ones inflating the average --
   read the flagged non-discriminating and flaky assertions from the
   previous section before trusting the headline verdict.

Grading itself is a human (or future judge) filling in the score row per
`grading-contract.md`'s contract -- blind (`condition` hidden), reading the
full transcript and output files rather than the final answer alone, and
critiquing weak assertions in `eval_feedback` rather than silently passing
them. Nothing in this skill re-derives that contract; follow it as written.

## Worked example: encoding a diagnosis-quality case

A golden-dataset case for "does this agent correctly diagnose a root cause
from a log excerpt" -- the kind of case sourced from a real recurring
support pattern, not a contrived edge case -- encoded in
`skill-eval-harness`'s exact case schema:

```json
{"id": "diagnose-oomkill-from-log-excerpt", "category": "root-cause-diagnosis", "prompt": "A pod restarted 3 times in the last hour. The log before each restart shows repeated lines like 'level=info msg=processing batch batch_size=50000' with no error line, then the process just stops. kubectl describe pod shows lastState.terminated.reason: OOMKilled, exitCode: 137. What is the root cause, and what should I check next?", "risk": "medium", "criteria": ["Identifies OOMKilled memory exhaustion as the root cause, not merely that the pod restarted.", "Connects the batch_size log line to the memory growth instead of treating it as unrelated noise.", "Names a concrete next check (actual memory usage vs the configured limit, whether batch_size is configurable or unbounded) rather than a generic check the logs suggestion.", "Does not recommend only raising the memory limit without first identifying why usage grew."]}
```

Validated against the harness's real schema check (run from the repository
root, against a single-line file containing exactly the case above):

```bash
python3 skills/workflows/skill-eval-harness/scripts/eval_harness.py validate --cases /tmp/agent-evals-worked-example.jsonl
```

```
WARNING: No 'high' risk case in the catalog — consider adding one that exercises a destructive action, an ambiguity, or a safety boundary for this skill.
WARNING: Every case shares category 'root-cause-diagnosis' — a single-category catalog cannot reveal category-specific regressions.
1 case(s) are valid.
```

Both warnings are expected and correct for a single-case illustration; a
real suite built from this pattern would add sibling cases across more
categories and at least one `high`-risk scenario before relying on it as a
release gate, per the coverage guidance above.

## When not to build a golden-dataset suite

`skill-authoring`'s "Choosing a validation depth" section already makes the
cost/benefit case for a skill's own validation, and the same tradeoff
applies one level up, to whether an agent or skill needs a golden-dataset
regression suite at all: everything free -- a read-through, the schema
validator, a manual check against 2-3 realistic prompts -- covers the large
majority of changes, and a budget-capped, paired, multi-trial eval run is
optional rigor for the changes where being wrong is expensive, not a
mandatory step for every edit. For a one-off skill or agent capability
unlikely to change again, building and maintaining a golden dataset, a
rubric, and a paired baseline/candidate run is pure overhead with no repeat
payoff. Reach for a full suite specifically when a
capability sees repeated edits, sits behind routing with wide blast radius,
or has already regressed once silently -- not by default.

## Anti-patterns

- Building a golden dataset entirely from synthetic edge cases instead of
  sampled or hand-authored real usage -- that is `ai-red-teaming`'s
  attack-catalog job, and a quality suite built the same way misses the
  boring, frequent failure that actually ships.
- Committing raw, unredacted past interactions into a versioned case file
  -- redact at authoring time; the file lives in Git forever.
- A single pass/fail verdict instead of `skill-eval-harness`'s five
  weighted dimensions -- it collapses independent failure modes (wrong
  answer vs. unhelpfully non-autonomous vs. a buried actionable step) into
  one bit.
- Writing `criteria` as a refusal boundary ("does not do X") for a quality
  case -- that phrasing belongs to a red-team case; a quality case's
  criteria describe what a correct, complete answer contains.
- Treating `blocker` as shorthand for "scored low" instead of its actual,
  narrower meaning (dangerous instruction, material factual error, broken
  output contract, or a blocking autonomy regression).
- Trusting the weighted release-gate verdict without reading
  `assertion_analysis.non_discriminating` and `.flaky` -- a candidate can
  clear the gate while its discriminating assertions are masked by weak
  ones padding the average.
- Building a second, bespoke eval runner instead of `skill-eval-harness`'s
  existing validate/plan/run/grade/score pipeline -- this catalog already
  paid for that machinery once.
- Running a full paired, multi-trial suite for a one-off skill or a wording
  change unlikely to recur -- see "When not to build" above and
  `skill-authoring`'s lightweight-default guidance.
- Grading with `condition` visible, or comparing `baseline`/`candidate`
  rows that are not paired on identical `(case_id, trial)` -- both
  invalidate every other check in this workflow, per `grading-contract.md`
  and `score`'s own pairing enforcement.
