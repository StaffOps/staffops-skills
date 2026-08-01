# Grading Contract

This harness does not ship an automated judge. Deciding whether a response
actually satisfies a criterion is a judgment call, and encoding that
judgment reliably (with the right amount of skepticism toward superficial
compliance) is a separate, larger effort than a v1 tooling pass justifies.
What it ships instead is the **contract** the judging step must fill in —
the exact shape a human grader, a future LLM-judge subagent, or a one-off
grading script must produce — plus the two checks in `score` that are
mechanical rather than judgment calls and therefore safe to automate now:
non-discriminating assertion detection and flaky-assertion detection.

## Who fills this in today

A human, reading the transcript and output files for each row and writing
the score row by hand (or via a spreadsheet exported to JSONL). This is
exactly the state `i-have-adhd`'s scoring step is in — its `README.md`
says outright "Judge and score" as a manual step before `run_evals.py score`
ever runs — and exactly the state skill-creator's grader is in before a
"grader subagent" spawn. Nothing here regresses that; it documents it
precisely enough that automating it later is a drop-in change to the
scoring step, not a redesign of the harness.

## What the grading step must do

Lift this directly from skill-creator's `agents/grader.md`, which is the
sharpest existing statement of the job:

1. **Read everything, not just the final answer.** The full transcript (if
   the executor produced one) and every output file. A grader that only
   reads `response_text` will pass responses that talk a good game but
   didn't do the work.
2. **Verify substance, not surface compliance.** A file that exists with the
   right name but wrong or empty content fails, even though a shallow check
   would pass it. "The output mentions the customer's name" is a weaker
   assertion than "the output correctly attributes revenue X to customer Y"
   — the grader should notice when an assertion only checks the former.
3. **Judge blind.** The `condition` field must not be visible to whoever
   assigns the five rubric scores (`correctness`, `autonomy`,
   `actionability`, `safety`, `concision`) and `blocker`. Label responses
   `A`/`B`/`C` during judging and only reattach `condition` afterward, or a
   grader who knows which response came from "the new version I just wrote"
   will unconsciously grade it more charitably. This is `i-have-adhd`'s
   `rubric.md` instruction verbatim and it is the single most important rule
   in this document — skip it and every other check in this file becomes
   theater.
4. **Critique the assertions, not just the response.** For every criterion
   in the case's `criteria` list, ask: would a clearly wrong response also
   pass this assertion? "The output includes the name 'John Smith'" passes
   for a hallucinated document that happens to mention the name — the
   assertion needed to check that the name appears as, say, the verified
   primary contact, not merely somewhere in the text. When an assertion has
   this gap, note it in `eval_feedback.suggestions` rather than silently
   passing a weak check. This is skill-creator's grader having "two jobs:
   grade the outputs, and critique the evals themselves" — a passing grade
   on a weak assertion is worse than useless because it manufactures false
   confidence in a release decision.
5. **Extract implicit claims and verify them.** Beyond the predefined
   criteria, note factual/process/quality claims the response makes and
   check whether they hold up — this catches issues the fixed criteria list
   didn't anticipate.

## Output shape

Each judged row is a score row per `references/case-schema.md`. The
`assertions` array is where steps 1-4 above land:

```json
{
  "text": "The output includes the name 'John Smith'",
  "passed": true,
  "evidence": "Found in transcript step 3, quoting the extracted contact list verbatim."
}
```

`eval_feedback` is where step 4's critique lands, and it should stay empty
(`{"suggestions": [], "overall": "No suggestions, criteria look solid."}`)
far more often than not — reserve it for genuine gaps, not routine nitpicks.
Keep the bar high: a suggestion here should make the case's original author
say "good catch," not read as reflexive hedging on every row.

## What `score` automates for you

Two checks do not require judgment and are computed for you whenever
`assertions` is present on the score rows:

### Non-discriminating assertions

Group every scored row by `(case_id, assertion text)` across conditions. An
assertion that passes 100% of the time in **both** `baseline` and
`candidate` (or fails 100% of the time in both) never distinguished the
version under test from the version it's being compared against — it is
dead weight in the release decision even though it looks like signal in a
pass-rate summary. This mechanizes the same observation skill-creator's
analyzer makes by hand: "Assertion 'Output is a PDF file' passes 100% in
both configurations - may not differentiate skill value." `score` reports
these under `assertion_analysis.non_discriminating` so you can retire or
sharpen them before the next run, not after the tenth run wastes tokens
computing them again.

### Flaky assertions

Group by `(case_id, condition, assertion text)` across trials. If the same
assertion, for the same case and the same condition, passes on some trials
and fails on others, that is either genuine model non-determinism the case
needs more trials to average out, or a case whose prompt is itself
underspecified. `score` reports these under `assertion_analysis.flaky`.

Both checks are pure aggregation over booleans already present in the score
file — no model call, no judgment, safe to run on every `score` invocation
without a budget concern.

## What stays a human (or future automated judge) call

Assigning `passed: true/false` with `evidence` in the first place, choosing
the five rubric scores, and setting `blocker`. That is the part this
contract deliberately leaves undefined in code — codifying it prematurely
would lock in one grading style before this harness has been used across
enough of the catalog's 100+ skills to know which judgment calls actually
need standardizing.
