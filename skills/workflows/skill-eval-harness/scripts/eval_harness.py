#!/usr/bin/env python3
"""Validate, plan, run, and score paired skill-change evaluations.

This is a harness-agnostic generalization of two prior tools (see
references/ for the full attribution and design rationale):

- ayghri/i-have-adhd's evals/scripts/run_evals.py contributed the outer loop:
  a weighted rubric release gate, strict baseline/candidate pairing so
  nobody can cherry-pick which rows got scored, resumability, retries, and
  a mandatory cost-reporting rule.
- anthropics/skills' skill-creator contributed the judging discipline: a
  grader that reads the whole transcript (not just the final answer) and
  also critiques its own assertions for being non-discriminating, plus the
  observation that repeated helper scripts across runs are a signal to
  bundle them into the skill.

What this script deliberately does NOT do: it does not call a model to
judge anything. Scoring a response against a criterion is a judgment call;
this tool consumes already-judged score rows (see references/case-schema.md)
and does the parts that are pure arithmetic: schema validation, a cost
preflight estimate, the paired release gate, and two mechanical checks over
assertion data (non-discriminating assertions, flaky assertions) that do not
require re-judging anything. See references/grading-contract.md for exactly
what a human or future automated judge must produce.

Subcommands:
    validate          Check a case catalog against the required schema.
    plan               Print the paired run matrix and a cost preflight
                        estimate before anything is executed.
    run                Execute one condition against a pluggable executor,
                        gated by a mandatory preflight budget check.
    score              Aggregate judged score rows into a weighted release
                        gate decision, plus assertion-discrimination and
                        flakiness analysis.
    collision-check    Compare one skill's description/tags against every
                        other skill in the catalog for overlapping trigger
                        language.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# Path.parents[4] from scripts/eval_harness.py -> .../skill-eval-harness/scripts/eval_harness.py
#   [0] scripts  [1] skill-eval-harness  [2] workflows  [3] skills  [4] repo root
HERE = Path(__file__).resolve()
SKILL_ROOT = HERE.parents[1]
REPO_ROOT = HERE.parents[4] if len(HERE.parents) > 4 else SKILL_ROOT
DEFAULT_CASES = SKILL_ROOT / "references" / "examples" / "cases.sample.jsonl"
DEFAULT_SKILLS_DIR = REPO_ROOT / "skills"

# Five-dimension rubric and weights, unchanged from the source this
# generalizes (ayghri/i-have-adhd, evals/rubric.md). Do not reweight
# without updating every skill's historical score files.
WEIGHTS = {
    "correctness": 0.35,
    "autonomy": 0.25,
    "actionability": 0.20,
    "safety": 0.10,
    "concision": 0.10,
}
CONDITIONS = {"baseline", "candidate", "comparator"}


# ---------------------------------------------------------------------------
# JSONL plumbing
# ---------------------------------------------------------------------------


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: line {number}: {exc.msg}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}: line {number}: expected a JSON object")
        rows.append(row)
    return rows


def load_cases(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


# ---------------------------------------------------------------------------
# Case catalog validation
# ---------------------------------------------------------------------------


def validate_cases(cases: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    required = {"id", "category", "prompt", "risk", "criteria"}
    for index, case in enumerate(cases, start=1):
        missing = sorted(required - set(case))
        if missing:
            errors.append(f"Case {index}: missing fields: {', '.join(missing)}")
            continue
        case_id = case["id"]
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"Case {index}: id must be a non-empty string")
        elif case_id in seen:
            errors.append(f"Duplicate case id: {case_id}")
        else:
            seen.add(case_id)
        if case["risk"] not in {"low", "medium", "high"}:
            errors.append(f"Case {case_id}: risk must be low, medium, or high")
        if not isinstance(case["criteria"], list) or not case["criteria"]:
            errors.append(f"Case {case_id}: criteria must be a non-empty list")
    return errors


def coverage_warnings(cases: list[dict[str, Any]]) -> list[str]:
    """Non-fatal signals about a thin or unbalanced catalog.

    A catalog where every case is low-risk proves nothing about whether a
    change degrades safety behavior; a catalog with one category can't
    support the kind of per-category pattern analysis the grading contract
    describes. These never fail `validate` on their own.
    """
    warnings: list[str] = []
    if not cases:
        return warnings
    risks = Counter(case.get("risk") for case in cases)
    if not risks.get("high"):
        warnings.append(
            "No 'high' risk case in the catalog — consider adding one that exercises "
            "a destructive action, an ambiguity, or a safety boundary for this skill."
        )
    categories = {case.get("category") for case in cases}
    if len(categories) == 1:
        warnings.append(
            f"Every case shares category '{next(iter(categories))}' — a single-category "
            "catalog cannot reveal category-specific regressions."
        )
    return warnings


def cmd_validate(args: argparse.Namespace) -> int:
    cases = load_cases(args.cases)
    errors = validate_cases(cases)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"\n{len(cases)} case(s), {len(errors)} error(s)", file=sys.stderr)
        return 1
    for warning in coverage_warnings(cases):
        print(f"WARNING: {warning}", file=sys.stderr)
    print(f"{len(cases)} case(s) are valid.")
    return 0


# ---------------------------------------------------------------------------
# Cost estimation and the run matrix
# ---------------------------------------------------------------------------


def estimate_cost_per_call(
    price_per_1k_input_usd: float,
    price_per_1k_output_usd: float,
    avg_input_tokens: int,
    avg_output_tokens: int,
) -> float:
    return (avg_input_tokens / 1000.0) * price_per_1k_input_usd + (
        avg_output_tokens / 1000.0
    ) * price_per_1k_output_usd


def build_matrix(
    cases: list[dict[str, Any]],
    trials: int,
    conditions: list[str],
    case_filter: list[str] | None = None,
) -> list[tuple[str, int, str]]:
    selected = [c for c in cases if not case_filter or c["id"] in case_filter]
    return [
        (case["id"], trial, condition)
        for trial in range(1, trials + 1)
        for case in selected
        for condition in conditions
    ]


def completed_keys(rows: list[dict[str, Any]]) -> set[tuple[str, int, str, str]]:
    keys: set[tuple[str, int, str, str]] = set()
    for row in rows:
        fields = (row.get("case_id"), row.get("trial"), row.get("condition"), row.get("runner"))
        if isinstance(fields[0], str) and isinstance(fields[1], int) and all(
            isinstance(value, str) for value in fields[2:]
        ):
            keys.add(fields)  # type: ignore[arg-type]
    return keys


def _preflight_report(
    remaining_calls: int, per_call_usd: float, budget_usd: float
) -> tuple[str, bool]:
    total = remaining_calls * per_call_usd
    fits = total <= budget_usd
    lines = [
        "Preflight cost estimate",
        "-----------------------",
        f"  remaining calls : {remaining_calls}",
        f"  est. cost/call  : ${per_call_usd:.4f}",
        f"  est. total cost : ${total:.4f}",
        f"  budget cap      : ${budget_usd:.4f}",
        f"  verdict         : {'WITHIN BUDGET' if fits else 'OVER BUDGET — refusing to start'}",
    ]
    return "\n".join(lines), fits


def cmd_plan(args: argparse.Namespace) -> int:
    cases = load_cases(args.cases)
    errors = validate_cases(cases)
    if errors:
        raise ValueError("\n".join(errors))

    conditions = ["baseline", "candidate"]
    if args.include_comparator:
        conditions.append("comparator")

    matrix = build_matrix(cases, args.trials, conditions, args.case)
    per_call = estimate_cost_per_call(
        args.price_per_1k_input_usd,
        args.price_per_1k_output_usd,
        args.avg_input_tokens,
        args.avg_output_tokens,
    )
    report, fits = _preflight_report(len(matrix), per_call, args.budget_usd)
    print(report, file=sys.stderr)
    print("", file=sys.stderr)

    for case_id, trial, condition in matrix:
        print(json.dumps({"case_id": case_id, "trial": trial, "condition": condition}))

    # `plan` never spends money, so it always prints the full matrix for
    # inspection — but it still exits non-zero when the estimate is over
    # budget, so a caller scripting "plan then run" stops here.
    return 0 if fits else 2


# ---------------------------------------------------------------------------
# Score aggregation (release gate)
# ---------------------------------------------------------------------------


def _validate_score(row: dict[str, Any], index: int) -> None:
    required = {"case_id", "trial", "condition", *WEIGHTS, "blocker", "notes"}
    missing = sorted(required - set(row))
    if missing:
        raise ValueError(f"Score row {index}: missing fields: {', '.join(missing)}")
    if row["condition"] not in CONDITIONS:
        raise ValueError(f"Score row {index}: unsupported condition {row['condition']!r}")
    for metric in WEIGHTS:
        value = row[metric]
        if not isinstance(value, (int, float)) or not 1 <= value <= 5:
            raise ValueError(f"Score row {index}: {metric} must be between 1 and 5")
    if not isinstance(row["blocker"], bool):
        raise ValueError(f"Score row {index}: blocker must be boolean")
    assertions = row.get("assertions")
    if assertions is not None:
        if not isinstance(assertions, list):
            raise ValueError(f"Score row {index}: assertions must be a list")
        for a_index, assertion in enumerate(assertions, start=1):
            if not isinstance(assertion, dict) or not {"text", "passed"} <= set(assertion):
                raise ValueError(
                    f"Score row {index}: assertion {a_index} must have 'text' and 'passed'"
                )
            if not isinstance(assertion["passed"], bool):
                raise ValueError(f"Score row {index}: assertion {a_index} 'passed' must be boolean")


def _describe_rows(keys: list[tuple[str, Any]]) -> str:
    return ", ".join(f"{case_id}/trial {trial}" for case_id, trial in keys)


def _check_pairing(grouped: dict[str, list[dict[str, Any]]]) -> None:
    """Conditions are only comparable when judged on identical rows.

    Without this, it is possible to score three good trials for candidate
    and three worst-case trials for baseline and call the difference a
    result. Verbatim logic from ayghri/i-have-adhd's run_evals.py.
    """
    coverage = {
        condition: Counter((row["case_id"], row["trial"]) for row in rows)
        for condition, rows in grouped.items()
    }
    for condition, counts in sorted(coverage.items()):
        repeated = sorted(key for key, count in counts.items() if count > 1)
        if repeated:
            raise ValueError(
                f"{condition}: duplicate score rows for {_describe_rows(repeated)}"
            )
    baseline = coverage["baseline"]
    for condition, counts in sorted(coverage.items()):
        if condition == "baseline" or counts == baseline:
            continue
        details = []
        missing = sorted(set(baseline) - set(counts))
        if missing:
            details.append(f"missing {_describe_rows(missing)}")
        unmatched = sorted(set(counts) - set(baseline))
        if unmatched:
            details.append(f"unmatched {_describe_rows(unmatched)}")
        raise ValueError(
            f"{condition} was not judged on the same rows as baseline: "
            + "; ".join(details)
        )


def analyze_assertions(scores: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Mechanical checks over per-assertion data — no judgment required.

    Non-discriminating: the same assertion text passes (or fails) 100% of
    the time in every condition present for a case — it never told the two
    conditions apart. Mirrors skill-creator's analyzer observation
    ("Assertion 'Output is a PDF file' passes 100% in both configurations")
    but computed exactly instead of eyeballed.

    Flaky: the same assertion, same case, same condition, disagrees across
    trials — a signal the case needs more trials or a sharper prompt.
    """
    has_assertions = any(row.get("assertions") for row in scores)
    if not has_assertions:
        return None

    # (case_id, assertion_text) -> {condition: [bool, ...]}
    by_case_assertion: dict[tuple[str, str], dict[str, list[bool]]] = defaultdict(
        lambda: defaultdict(list)
    )
    # (case_id, condition, assertion_text) -> [bool, ...] across trials
    by_case_condition_assertion: dict[tuple[str, str, str], list[bool]] = defaultdict(list)

    for row in scores:
        for assertion in row.get("assertions") or []:
            text = assertion["text"]
            passed = assertion["passed"]
            by_case_assertion[(row["case_id"], text)][row["condition"]].append(passed)
            by_case_condition_assertion[(row["case_id"], row["condition"], text)].append(passed)

    non_discriminating = []
    for (case_id, text), by_condition in sorted(by_case_assertion.items()):
        if len(by_condition) < 2:
            continue
        rates = {cond: sum(vals) / len(vals) for cond, vals in by_condition.items()}
        distinct_rates = set(rates.values())
        if len(distinct_rates) == 1 and distinct_rates <= {0.0, 1.0}:
            non_discriminating.append(
                {
                    "case_id": case_id,
                    "assertion": text,
                    "shared_pass_rate": next(iter(distinct_rates)),
                    "conditions": sorted(rates),
                }
            )

    flaky = []
    for (case_id, condition, text), passed_values in sorted(by_case_condition_assertion.items()):
        if len(set(passed_values)) > 1:
            flaky.append(
                {
                    "case_id": case_id,
                    "condition": condition,
                    "assertion": text,
                    "pass_rate": sum(passed_values) / len(passed_values),
                    "trials": len(passed_values),
                }
            )

    return {"non_discriminating": non_discriminating, "flaky": flaky}


def summarize_scores(scores: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, row in enumerate(scores, start=1):
        _validate_score(row, index)
        grouped[row["condition"]].append(row)
    if "baseline" not in grouped or "candidate" not in grouped:
        raise ValueError("Scores must include baseline and candidate conditions")
    _check_pairing(grouped)

    conditions: dict[str, dict[str, Any]] = {}
    for condition, rows in sorted(grouped.items()):
        metrics = {
            metric: sum(float(row[metric]) for row in rows) / len(rows)
            for metric in WEIGHTS
        }
        conditions[condition] = {
            "rows": len(rows),
            **metrics,
            "weighted_score": sum(metrics[metric] * weight for metric, weight in WEIGHTS.items()),
            "blocking_findings": sum(bool(row["blocker"]) for row in rows),
        }

    baseline = conditions["baseline"]
    candidate = conditions["candidate"]
    reasons: list[str] = []
    if candidate["blocking_findings"]:
        reasons.append("Candidate has blocking safety or correctness findings.")
    if candidate["correctness"] < baseline["correctness"] - 0.1:
        reasons.append("Candidate correctness regressed by more than 0.1 points.")
    if candidate["safety"] < baseline["safety"] - 0.1:
        reasons.append("Candidate safety regressed by more than 0.1 points.")
    if candidate["weighted_score"] <= baseline["weighted_score"]:
        reasons.append("Candidate weighted score did not beat baseline.")

    result = {
        "weights": WEIGHTS,
        "conditions": conditions,
        "release_gate": {"passed": not reasons, "reasons": reasons},
    }
    assertion_analysis = analyze_assertions(scores)
    if assertion_analysis is not None:
        result["assertion_analysis"] = assertion_analysis
    return result


def cmd_score(args: argparse.Namespace) -> int:
    summary = summarize_scores(read_jsonl(args.scores))
    print(json.dumps(summary, indent=2))
    return 0 if summary["release_gate"]["passed"] else 1


# ---------------------------------------------------------------------------
# Executor-agnostic run loop
# ---------------------------------------------------------------------------


def _condition_prompt_note(condition: str, skill_path: Path | None) -> None:
    if condition != "baseline" and skill_path is None:
        raise ValueError(f"--condition-skill is required for the {condition} condition")


def _invoke_executor(
    executor_argv: list[str],
    request: dict[str, Any],
    retries: int,
) -> dict[str, Any]:
    payload = json.dumps(request)
    last_error = ""
    for attempt in range(retries + 1):
        try:
            completed = subprocess.run(
                executor_argv,
                input=payload,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            # Executor binary missing, not executable, or otherwise
            # unlaunchable (bad --executor-cmd). Treat exactly like a failed
            # attempt rather than letting a raw traceback escape -- retries
            # and the final RuntimeError still apply.
            last_error = f"could not launch executor: {exc}"
            if attempt < retries:
                time.sleep(min(2**attempt, 5))
            continue
        if completed.returncode == 0 and completed.stdout.strip():
            try:
                response = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                last_error = f"executor wrote invalid JSON: {exc.msg}"
            else:
                if response.get("ok"):
                    return response
                last_error = str(response.get("error") or "executor reported ok=false")
        else:
            last_error = completed.stderr.strip() or f"executor exited {completed.returncode}"
        if attempt < retries:
            time.sleep(min(2**attempt, 5))
    raise RuntimeError(
        f"Executor failed after {retries + 1} attempt(s) "
        f"({shlex.join(executor_argv)}): {last_error}"
    )


def cmd_run(args: argparse.Namespace) -> int:
    cases = load_cases(args.cases)
    errors = validate_cases(cases)
    if errors:
        raise ValueError("\n".join(errors))
    _condition_prompt_note(args.condition, args.condition_skill)

    unknown = sorted(set(args.case or []) - {case["id"] for case in cases})
    if unknown:
        raise ValueError(f"--case matched no evaluation case: {', '.join(unknown)}")

    selected = [c for c in cases if not args.case or c["id"] in args.case]
    prior_rows = read_jsonl(args.output) if args.output.exists() else []
    done = completed_keys(prior_rows)
    reported_cost = sum(
        float(row.get("cost_usd") or 0)
        for row in prior_rows
        if row.get("condition") == args.condition and row.get("runner") == args.runner
    )

    # --- mandatory preflight gate: computed and enforced before the first
    # executor call, independent of whether the executor itself reports cost.
    remaining_calls = sum(
        1
        for trial in range(1, args.trials + 1)
        for case in selected
        if (case["id"], trial, args.condition, args.runner) not in done
    )
    per_call = estimate_cost_per_call(
        args.price_per_1k_input_usd,
        args.price_per_1k_output_usd,
        args.avg_input_tokens,
        args.avg_output_tokens,
    )
    budget_left_for_estimate = args.budget_usd - reported_cost
    report, fits = _preflight_report(remaining_calls, per_call, budget_left_for_estimate)
    print(report, file=sys.stderr)
    print("", file=sys.stderr)
    if not fits:
        print(
            "Refusing to start: the preflight estimate exceeds the remaining budget. "
            "Raise --budget-usd, cut --trials, or narrow --case before rerunning.",
            file=sys.stderr,
        )
        return 2
    if remaining_calls == 0:
        print("Nothing to do; every (case, trial) row is already completed.")
        return 0

    executor_argv = shlex.split(args.executor_cmd)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    budget_remaining = args.budget_usd - reported_cost
    condition_skill_text = None
    if args.condition_skill is not None:
        # Read once; the executor receives the path, not the text, so it can
        # inject the instructions however its target agent expects. Reading
        # here only validates the file exists and is not empty.
        condition_skill_text = args.condition_skill.read_text(encoding="utf-8")
        if not condition_skill_text.strip():
            raise ValueError(f"--condition-skill {args.condition_skill} is empty")

    with args.output.open("a", encoding="utf-8") as destination:
        for trial in range(1, args.trials + 1):
            for case in selected:
                key = (case["id"], trial, args.condition, args.runner)
                if key in done:
                    print(f"skip completed {args.condition} trial {trial}: {case['id']}")
                    continue
                if budget_remaining <= 0:
                    print("Budget exhausted; stopping.", file=sys.stderr)
                    return 2

                workdir = None
                if args.workdir:
                    workdir = args.workdir / args.condition / case["id"] / f"trial-{trial}"
                    workdir.mkdir(parents=True, exist_ok=True)

                request = {
                    "skill_path": str(args.condition_skill) if args.condition_skill else None,
                    "condition": args.condition,
                    "case_id": case["id"],
                    "trial": trial,
                    "prompt": case["prompt"],
                    "budget_usd_remaining": round(budget_remaining, 4),
                    "workdir": str(workdir) if workdir else None,
                }
                response = _invoke_executor(executor_argv, request, args.retries)

                cost = response.get("cost_usd")
                if cost is None and not args.allow_unmetered:
                    raise RuntimeError(
                        "Executor did not report cost_usd; rerun with --allow-unmetered "
                        "only when the executor's account has its own separate hard cap."
                    )
                budget_remaining -= float(cost or 0)
                row = {
                    "case_id": case["id"],
                    "trial": trial,
                    "condition": args.condition,
                    "runner": args.runner,
                    "response": response.get("response_text", ""),
                    "transcript_path": response.get("transcript_path"),
                    "output_files": response.get("output_files", []),
                    "usage": response.get("usage", {}),
                    "cost_usd": cost,
                    "duration_ms": response.get("duration_ms"),
                }
                destination.write(json.dumps(row, ensure_ascii=False) + "\n")
                destination.flush()
                print(f"{args.condition} trial {trial}: {case['id']} (cost=${cost or 0:.4f})")
    print(f"Reported cost this invocation: ${args.budget_usd - reported_cost - budget_remaining:.4f}")
    return 0


# ---------------------------------------------------------------------------
# Skill-collision check
# ---------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
TOKEN_RE = re.compile(r"[a-z0-9]+")


def _parse_skill_frontmatter(text: str) -> dict[str, str]:
    """Minimal frontmatter reader, deliberately self-contained.

    This intentionally duplicates a small amount of logic from
    tools/validate_skills.py rather than importing across the repo root —
    a skill's scripts/ directory should work if the skill folder is copied
    elsewhere, per the progressive-disclosure bundling convention this
    catalog follows.
    """
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    fields: dict[str, str] = {}
    path: list[str] = []
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        entry = re.match(r"^\s*([A-Za-z_-]+):\s*(.*)$", line)
        if not entry:
            continue
        key, value = entry.group(1), entry.group(2).strip()
        depth = indent // 2
        path = path[:depth] + [key]
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        fields[".".join(path)] = value
    return fields


def _parse_list(value: str) -> list[str]:
    value = value.strip()
    if not value.startswith("["):
        return []
    inner = value[1:-1].strip()
    return [item.strip() for item in inner.split(",") if item.strip()]


def _load_skill_meta(path: Path) -> dict[str, Any]:
    fields = _parse_skill_frontmatter(path.read_text(encoding="utf-8"))
    return {
        "path": path,
        "name": fields.get("name", path.parent.name),
        "description": fields.get("description", ""),
        "category": fields.get("metadata.hermes.category", path.parent.parent.name),
        "tags": _parse_list(fields.get("metadata.hermes.tags", "")),
    }


def _tokenize(text: str) -> set[str]:
    return {tok for tok in TOKEN_RE.findall(text.lower()) if len(tok) >= 3}


def _boilerplate_tokens(all_meta: list[dict[str, Any]], doc_freq_threshold: float) -> set[str]:
    """Tokens common enough across the whole catalog to carry no signal.

    Computed from the live catalog rather than a hardcoded stopword list,
    so it keeps working as the catalog's own house style evolves (e.g. if
    every metrics skill starts a description with "Use when diagnosing").
    """
    doc_freq: Counter[str] = Counter()
    for meta in all_meta:
        for token in _tokenize(meta["description"]) | {t.lower() for t in meta["tags"]}:
            doc_freq[token] += 1
    total = max(len(all_meta), 1)
    return {token for token, count in doc_freq.items() if count / total > doc_freq_threshold}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def cmd_collision_check(args: argparse.Namespace) -> int:
    skills_dir = args.skills_dir
    paths = sorted(skills_dir.glob("*/*/SKILL.md"))
    if not paths:
        raise ValueError(f"No SKILL.md found under {skills_dir}")

    all_meta = [_load_skill_meta(p) for p in paths]
    boilerplate = _boilerplate_tokens(all_meta, args.boilerplate_doc_freq)

    target_path = args.skill.resolve()
    target = next((m for m in all_meta if m["path"].resolve() == target_path), None)
    if target is None:
        # The skill under review might not be in skills/ yet (new, unstaged).
        target = _load_skill_meta(args.skill)

    target_tokens = (_tokenize(target["description"]) | {t.lower() for t in target["tags"]}) - boilerplate
    if not target_tokens:
        print(
            "WARNING: after removing catalog-wide boilerplate, this skill's description "
            "has no distinctive tokens left to compare — the description may be too generic.",
            file=sys.stderr,
        )

    scored = []
    for meta in all_meta:
        if meta["path"].resolve() == target_path:
            continue
        tokens = (_tokenize(meta["description"]) | {t.lower() for t in meta["tags"]}) - boilerplate
        score = _jaccard(target_tokens, tokens)
        shared = sorted(target_tokens & tokens)
        scored.append((score, meta, shared))
    scored.sort(key=lambda item: item[0], reverse=True)

    print(f"Target: {target['name']} — {target['description']!r}")
    print(f"Distinctive tokens (boilerplate removed): {sorted(target_tokens)}")
    print(f"Compared against {len(scored)} other skill(s), {len(boilerplate)} boilerplate token(s) ignored.")
    print("")

    collisions = [item for item in scored if item[0] >= args.fail_threshold]
    reported = [item for item in scored if item[0] >= args.report_threshold]
    if not reported:
        print(f"No overlap at or above the report threshold ({args.report_threshold}).")
    for score, meta, shared in reported:
        marker = "COLLISION" if score >= args.fail_threshold else "note"
        same_category = " (same category)" if meta["category"] == target["category"] else ""
        print(
            f"[{marker}] {score:.2f}  {meta['name']}{same_category} — "
            f"shared: {shared or '(none — category/tag overlap only)'}"
        )

    if collisions:
        print(
            f"\n{len(collisions)} skill(s) at or above the collision threshold "
            f"({args.fail_threshold}) — disambiguate the description or trigger "
            "wording before finalizing this skill.",
            file=sys.stderr,
        )
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _add_cost_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--budget-usd",
        type=float,
        required=True,
        help="Hard spend cap for this invocation. Required, no default — "
        "the preflight estimate is checked against it before anything runs.",
    )
    parser.add_argument("--price-per-1k-input-usd", type=float, default=3.0)
    parser.add_argument("--price-per-1k-output-usd", type=float, default=15.0)
    parser.add_argument("--avg-input-tokens", type=int, default=800)
    parser.add_argument("--avg-output-tokens", type=int, default=400)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a case catalog")
    validate.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    validate.set_defaults(handler=cmd_validate)

    plan = subparsers.add_parser("plan", help="Print the paired run matrix and a cost preflight estimate")
    plan.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    plan.add_argument("--trials", type=int, default=3)
    plan.add_argument("--include-comparator", action="store_true")
    plan.add_argument("--case", action="append")
    _add_cost_flags(plan)
    plan.set_defaults(handler=cmd_plan)

    run = subparsers.add_parser("run", help="Execute one condition against a pluggable executor")
    run.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    run.add_argument(
        "--executor-cmd",
        required=True,
        help="Shell command that reads the JSON request on stdin and writes the "
        "JSON response on stdout. See references/executor-contract.md. Example: "
        "'python3 scripts/claude_code_executor.py'.",
    )
    run.add_argument("--condition", choices=sorted(CONDITIONS), required=True)
    run.add_argument("--condition-skill", type=Path)
    run.add_argument("--case", action="append")
    run.add_argument("--trials", type=int, default=3)
    run.add_argument("--retries", type=int, default=2)
    run.add_argument("--runner", default="default", help="Free-text label distinguishing executors in --output.")
    run.add_argument("--workdir", type=Path, help="Scratch root; one subdir is created per (condition, case, trial).")
    run.add_argument("--allow-unmetered", action="store_true")
    run.add_argument("--output", type=Path, required=True)
    _add_cost_flags(run)
    run.set_defaults(handler=cmd_run)

    score = subparsers.add_parser("score", help="Aggregate judged score rows into a release-gate decision")
    score.add_argument("scores", type=Path)
    score.set_defaults(handler=cmd_score)

    collision = subparsers.add_parser(
        "collision-check", help="Compare a skill's description/tags against the rest of the catalog"
    )
    collision.add_argument("--skill", type=Path, required=True, help="Path to the SKILL.md under review.")
    collision.add_argument("--skills-dir", type=Path, default=DEFAULT_SKILLS_DIR)
    collision.add_argument(
        "--boilerplate-doc-freq",
        type=float,
        default=0.15,
        help="Tokens appearing in more than this fraction of all descriptions are "
        "treated as catalog-wide boilerplate and ignored (default 0.15).",
    )
    collision.add_argument("--report-threshold", type=float, default=0.15, help="Minimum score to print.")
    collision.add_argument("--fail-threshold", type=float, default=0.5, help="Score at or above which exit code is 1.")
    collision.set_defaults(handler=cmd_collision_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
