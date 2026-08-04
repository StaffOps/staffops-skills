#!/usr/bin/env python3
"""fake_backend.py -- TEST-ONLY in-memory LinkedInBackend. Not a vendor.

This is NOT a usable default and is never loaded automatically by
pipeline.py -- there is no default backend (see SKILL.md, "Vendor-agnostic
by design"). It exists so `test_pipeline.py` and anyone evaluating this
skill can exercise the full state machine (invite sweeps, pending sweeps,
the restricted-outcome disambiguation, round-robin import assignment)
without any real automation vendor account, credentials, or network
access.

Behavior is entirely scripted by the caller via `queue_invite_outcome()` /
`queue_status()` -- it never makes a real decision about a real person. A
production backend implementing LinkedInBackend for a real vendor belongs
in your own codebase, not in this catalog (see CONTRIBUTING.md: this
catalog ships patterns and reference implementations, not production
vendor integrations).
"""

from __future__ import annotations

import sys
from collections import defaultdict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import (  # noqa: E402  -- path insert must precede this import
    Candidate,
    ConnectionStatus,
    InviteResult,
    LinkedInBackend,
    Outcome,
)


class FakeBackend(LinkedInBackend):
    """Deterministic, in-memory, single-process fake. Queue outcomes per
    person_ref; each call to send_connection_request/check_connection_status
    pops the next queued value. An empty queue defaults to Outcome.SENT /
    ConnectionStatus.CONNECTED so a test that doesn't care about a
    particular person still gets a sensible default instead of an error."""

    def __init__(self) -> None:
        self._invite_queue: dict[str, deque[InviteResult]] = defaultdict(deque)
        self._status_queue: dict[str, deque[ConnectionStatus]] = defaultdict(deque)
        self._candidates: dict[str, list[Candidate]] = {}
        self.withdraw_calls: list[tuple[str, str]] = []
        self.withdraw_result = True

    def queue_invite_outcome(self, person_ref: str, outcome: Outcome, message: str | None = None) -> None:
        self._invite_queue[person_ref].append(InviteResult(outcome=outcome, message=message))

    def queue_status(self, person_ref: str, status: ConnectionStatus) -> None:
        self._status_queue[person_ref].append(status)

    def set_search_results(self, query: str, candidates: list[Candidate]) -> None:
        self._candidates[query] = candidates

    def send_connection_request(self, account_ref: str, person_ref: str) -> InviteResult:
        queue = self._invite_queue[person_ref]
        if queue:
            return queue.popleft()
        return InviteResult(outcome=Outcome.SENT)

    def check_connection_status(self, account_ref: str, person_ref: str) -> ConnectionStatus:
        queue = self._status_queue[person_ref]
        if queue:
            return queue.popleft()
        return ConnectionStatus.CONNECTED

    def withdraw_connection_request(self, account_ref: str, person_ref: str) -> bool:
        self.withdraw_calls.append((account_ref, person_ref))
        return self.withdraw_result

    def search_candidates(self, account_ref: str, query: str, limit: int) -> list[Candidate]:
        return self._candidates.get(query, [])[:limit]
