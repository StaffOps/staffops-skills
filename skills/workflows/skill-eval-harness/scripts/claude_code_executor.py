#!/usr/bin/env python3
"""Reference executor: implements references/executor-contract.md for Claude Code.

Reads one JSON request object from stdin, runs it through `claude -p`, and
writes one JSON response object to stdout. This is ONE implementation of the
contract, not the only one — see references/executor-contract.md for what a
different executor (a different CLI, a raw API client, a mock for testing
eval_harness.py itself) needs to do instead.

Two things this wrapper does deliberately, both lifted from the isolation
notes in ayghri/i-have-adhd's evals/README.md:

1. Isolation: always passes --setting-sources "" so the operator's own
   installed plugins, hooks, memory, and output styles cannot leak into a
   condition. Without this, an operator with a skill's rules permanently
   enabled locally would inject that skill into the BASELINE condition too,
   silently making the comparison measure the skill against itself.
2. A pinned model: isolation also drops the operator's saved model default,
   so this pins --model explicitly (override with SKILL_EVAL_MODEL). Without
   a pin, the eval runs whatever the CLI defaults to on the day it happens to
   run, and per-token cost drifts with it.

Usage (called by eval_harness.py, not normally run by hand):
    echo '{"skill_path": null, "condition": "baseline", "case_id": "x",
           "trial": 1, "prompt": "What is 2+2?", "budget_usd_remaining": 5.0,
           "workdir": null}' | python3 claude_code_executor.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_MODEL = os.environ.get("SKILL_EVAL_MODEL", "claude-opus-4-8")


def _condition_prompt(prompt: str, skill_path: str | None) -> str:
    if not skill_path:
        return prompt
    instructions = Path(skill_path).read_text(encoding="utf-8")
    return (
        "Follow the skill below while completing the task. Do not discuss or "
        "quote the skill in your answer.\n\n"
        f"<skill>\n{instructions}\n</skill>\n\n"
        f"<task>\n{prompt}\n</task>"
    )


def run(request: dict) -> dict:
    prompt = _condition_prompt(request["prompt"], request.get("skill_path"))
    budget_remaining = request.get("budget_usd_remaining")

    command = [
        "claude",
        "--disable-slash-commands",
        "--print",
        "--output-format",
        "json",
        "--no-session-persistence",
        "--setting-sources",
        "",
        "--model",
        DEFAULT_MODEL,
        "--tools",
        "",
    ]
    if budget_remaining is not None:
        command.extend(["--max-budget-usd", f"{max(budget_remaining, 0):.4f}"])
    command.append(prompt)

    start = time.monotonic()
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    duration_ms = int((time.monotonic() - start) * 1000)

    if completed.returncode != 0:
        return {
            "ok": False,
            "error": completed.stderr.strip() or completed.stdout.strip() or "claude exited non-zero",
            "duration_ms": duration_ms,
        }

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"could not parse claude output: {exc.msg}", "duration_ms": duration_ms}

    transcript_path = None
    workdir = request.get("workdir")
    if workdir:
        Path(workdir).mkdir(parents=True, exist_ok=True)
        transcript_path = str(Path(workdir) / "transcript.json")
        Path(transcript_path).write_text(completed.stdout, encoding="utf-8")

    return {
        "ok": True,
        "response_text": str(payload.get("result", "")).strip(),
        "transcript_path": transcript_path,
        "output_files": [],
        "usage": payload.get("usage", {}) or {},
        "cost_usd": payload.get("total_cost_usd"),
        "duration_ms": duration_ms,
        "error": None,
    }


def main() -> int:
    request = json.loads(sys.stdin.read())
    response = run(request)
    print(json.dumps(response))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
