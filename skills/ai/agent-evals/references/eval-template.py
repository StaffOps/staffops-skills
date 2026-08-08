#!/usr/bin/env python3
"""Agent Eval Harness Template

Simple evaluation framework:
1. Load golden dataset (JSON with input/expected pairs)
2. Run agent on each input
3. Score with exact match + LLM-as-judge
4. Print summary report

Usage:
    python eval-template.py --dataset golden.json --model gpt-4o
"""

import json
import argparse
from dataclasses import dataclass, field
from pathlib import Path


# --- Data Structures ---------------------------------------------------------

@dataclass
class EvalCase:
    """Single evaluation case from the golden dataset."""
    id: str
    input: str
    expected: str
    tags: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    """Result of evaluating one case."""
    case_id: str
    actual: str
    exact_match: bool
    llm_judge_score: float  # 0.0 to 1.0
    llm_judge_rationale: str


# --- Core Functions ----------------------------------------------------------

def load_dataset(path: Path) -> list[EvalCase]:
    """Load golden dataset from JSON file.

    Expected format:
    [{"id": "case-1", "input": "...", "expected": "...", "tags": ["tag1"]}]
    """
    with open(path) as f:
        data = json.load(f)
    return [EvalCase(**item) for item in data]


async def run_agent(input_text: str) -> str:
    """Run the agent under test. Replace with your agent invocation."""
    # Example: call your agent API, subprocess, or SDK
    # response = await agent.run(input_text)
    # return response.output
    raise NotImplementedError("Replace with your agent invocation")


def score_exact_match(expected: str, actual: str) -> bool:
    """Exact string match after normalization."""
    return expected.strip().lower() == actual.strip().lower()


async def score_llm_judge(input_text: str, expected: str, actual: str) -> tuple[float, str]:
    """Use an LLM to judge quality of the response.

    Returns (score: 0.0-1.0, rationale: str).
    Replace with your LLM API call.
    """
    prompt = f"""You are an evaluation judge. Score the ACTUAL response against EXPECTED.

INPUT: {input_text}
EXPECTED: {expected}
ACTUAL: {actual}

Score 0.0 (completely wrong) to 1.0 (perfect). Respond as JSON:
{{"score": 0.8, "rationale": "..."}}"""

    # response = await llm_client.complete(prompt)
    # parsed = json.loads(response)
    # return parsed["score"], parsed["rationale"]
    raise NotImplementedError("Replace with your LLM API call")


# --- Orchestration -----------------------------------------------------------

async def run_eval(dataset_path: Path) -> list[EvalResult]:
    """Run full evaluation pipeline."""
    cases = load_dataset(dataset_path)
    results: list[EvalResult] = []

    for case in cases:
        actual = await run_agent(case.input)
        exact = score_exact_match(case.expected, actual)
        llm_score, rationale = await score_llm_judge(case.input, case.expected, actual)

        results.append(EvalResult(
            case_id=case.id,
            actual=actual,
            exact_match=exact,
            llm_judge_score=llm_score,
            llm_judge_rationale=rationale,
        ))

    return results


def print_report(results: list[EvalResult]) -> None:
    """Print summary report to stdout."""
    total = len(results)
    exact_matches = sum(1 for r in results if r.exact_match)
    avg_llm_score = sum(r.llm_judge_score for r in results) / total if total else 0

    print(f"\n{'='*60}")
    print(f"  EVAL REPORT — {total} cases")
    print(f"{'='*60}")
    print(f"  Exact match:     {exact_matches}/{total} ({exact_matches/total*100:.1f}%)")
    print(f"  LLM judge avg:   {avg_llm_score:.2f}/1.00")
    print(f"{'='*60}\n")

    # Detail failures
    failures = [r for r in results if not r.exact_match or r.llm_judge_score < 0.7]
    if failures:
        print(f"  FAILURES ({len(failures)}):")
        for r in failures:
            print(f"    [{r.case_id}] exact={r.exact_match} llm={r.llm_judge_score:.2f} — {r.llm_judge_rationale[:80]}")


# --- CLI Entrypoint ----------------------------------------------------------

if __name__ == "__main__":
    import asyncio

    parser = argparse.ArgumentParser(description="Run agent evaluation")
    parser.add_argument("--dataset", type=Path, required=True, help="Path to golden dataset JSON")
    args = parser.parse_args()

    results = asyncio.run(run_eval(args.dataset))
    print_report(results)
