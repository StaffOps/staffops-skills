# Executor Contract

The harness never calls a model API or a CLI directly. It shells out to an
**executor** — any program that speaks one JSON object on stdin and writes
one JSON object on stdout. This is the pluggability seam: swapping the
executor swaps the agent under test (Claude Code today, a different CLI or a
raw API client tomorrow) without touching `scripts/eval_harness.py`.

This is a deliberate departure from `ayghri/i-have-adhd`'s `run_evals.py`,
which builds the `claude`/`codex` subprocess argv directly inside the runner.
That works for exactly the two CLIs it hardcodes and requires editing the
runner itself to add a third. A JSON-over-stdio contract works for anything
that can read stdin and write stdout, including a Python API client, a shell
wrapper around a proprietary internal endpoint, or a mock used in the
harness's own tests.

## Request (written to the executor's stdin)

```json
{
  "skill_path": "skills/aws/iam-patterns/SKILL.md",
  "condition": "candidate",
  "case_id": "direct-answer",
  "trial": 1,
  "prompt": "What is 17 multiplied by 6?",
  "budget_usd_remaining": 9.5,
  "workdir": "/abs/path/to/a/scratch/dir/for/this/run"
}
```

| Field | Meaning |
| --- | --- |
| `skill_path` | Path to the `SKILL.md` (or arbitrary instructions file) to inject for this condition. `null` for the `baseline` condition — baseline gets the bare `prompt`, nothing injected. |
| `condition` | `baseline`, `candidate`, or `comparator`. Executors that don't special-case anything can ignore this and just check `skill_path is None`. |
| `case_id`, `trial` | Echoed back into the response row; useful for the executor's own logging. |
| `prompt` | The exact case prompt. Identical text across every condition for the same case. |
| `budget_usd_remaining` | What's left of the run's `--budget-usd` at the moment this call starts. An executor that supports a hard per-call spend cap (Claude Code's `--max-budget-usd`, for instance) should pass this straight through instead of letting a single call blow through the remaining budget. |
| `workdir` | A scratch directory unique to this (case, trial, condition) row. The executor may write a transcript, output files, or scratch state here; the harness does not clean it up mid-run so a human can inspect it after. |

## Response (read from the executor's stdout)

```json
{
  "ok": true,
  "response_text": "102",
  "transcript_path": "/abs/path/.../transcript.md",
  "output_files": [],
  "usage": {"input_tokens": 612, "output_tokens": 8},
  "cost_usd": 0.0041,
  "duration_ms": 1830,
  "error": null
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `ok` | yes | `false` means the call failed; the harness retries per `--retries` and surfaces `error` if every attempt fails. |
| `response_text` | yes when `ok` | The final answer text. This is what a grader reads first. |
| `transcript_path` | no | Path to a full execution transcript (markdown or plain text), if the executor produced one. Required in practice for anything beyond single-turn Q&A — the grading contract (`references/grading-contract.md`) expects a transcript to exist for multi-step cases. |
| `output_files` | no | Any files the executor produced beyond the text response (a patched file, a generated script). Empty list if none. |
| `usage` | no | Raw token counts if the executor's provider reports them. Purely informational — cost accounting uses `cost_usd`. |
| `cost_usd` | see below | Dollar cost of this single call, if the provider reports it. |
| `duration_ms` | no | Wall-clock time for this call. Feeds the same kind of timing data skill-creator's benchmark.json captures. |
| `error` | when `ok` is false | Human-readable failure reason. |

### The cost-reporting rule is not optional

If `cost_usd` is `null` on every response from an executor, `eval_harness.py
run` refuses to proceed past the first call unless `--allow-unmetered` is
explicitly passed — mirroring `i-have-adhd`'s rule verbatim, because the
reasoning does not change with the design: an executor that cannot report
what it spent cannot be trusted to stop at a budget on its own. Reach for
`--allow-unmetered` only when the account behind the executor has its own
separate hard spending cap enforced by the provider, not by this harness.

## Reference implementation: Claude Code

`scripts/claude_code_executor.py` implements this contract by wrapping
`claude -p`. Two things it does that a naive wrapper would not:

1. **Isolation.** It always passes `--setting-sources ""` so the operator's
   own installed plugins, hooks, memory, and output styles cannot leak into
   a condition. The sharpest failure mode this prevents: an operator who has
   a skill's rules permanently enabled locally would otherwise get that
   skill's behavior injected into the `baseline` condition too, silently
   making the comparison measure the skill against itself.
2. **A pinned model.** Isolation also drops the operator's saved model
   default, so the executor pins `--model` explicitly (configurable via
   `SKILL_EVAL_MODEL`, defaulting to a fixed model id). Without a pin, the
   eval runs whatever the CLI defaults to on the day it happens to run,
   which drifts under you and changes per-token cost without warning.

Both points come from `i-have-adhd`'s `evals/README.md`, which documents the
exact same failure modes for its own two example runners. This reference
implementation exists to demonstrate the contract works end to end for one
real executor — not to be the only one anybody ever writes. A minimal
executor for a different agent needs to do exactly three things: read one
JSON object from stdin, run the case, write one JSON object to stdout in the
shape above.

## Writing a new executor

- Read the request JSON from stdin (not argv — argv leaks into shell
  history and process listings, JSON on stdin does not).
- If `skill_path` is set, inject its contents into the agent's context
  however that agent supports doing so (system prompt, project file,
  first-turn preamble). Do not let the agent quote or discuss the injected
  instructions in its answer; that would leak the condition to a grader who
  is supposed to be blind to it.
- If `skill_path` is `null`, run the bare `prompt` with no injected
  instructions at all.
- Respect `budget_usd_remaining` if the underlying provider supports a
  per-call spend cap; otherwise document that it does not, so operators know
  `--budget-usd` is only enforced between calls, not within one.
- Write exactly one JSON object to stdout and exit 0 even on a handled
  failure (`{"ok": false, "error": "..."}`) — reserve a non-zero exit code
  for the executor itself crashing before it could produce a response.
