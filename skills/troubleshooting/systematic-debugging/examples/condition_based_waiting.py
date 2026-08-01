"""Condition-based waiting helpers for tests that currently guess at timing
with time.sleep(). See SKILL.md, "Condition-Based Waiting: Stop Guessing at
Timing" -- a longer sleep is a symptom fix; the underlying race is still
there, just less likely to lose.

Adapted from a real flaky-test fix in an async worker: a test slept a fixed
0.3s hoping a queue consumer would drain 2 items, which passed locally and
failed under CI load. Replacing the sleep with wait_for() fixed it: pass
rate went from roughly 70% to 100%, and the test got faster on the fast
path because it stopped waiting once the condition was true.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class TimeoutError_(TimeoutError):
    """Raised by wait_for()/await_for() with a description of what was
    expected, instead of a bare assertion mismatch."""


def wait_for(
    condition: Callable[[], T | None],
    timeout: float = 5.0,
    interval: float = 0.01,
    description: str = "condition",
) -> T:
    """Poll `condition` every `interval` seconds until it returns a truthy
    value, or raise after `timeout` seconds.

    Use this in synchronous tests instead of `time.sleep(N)` followed by an
    assertion -- it returns as soon as the condition is true and fails with
    a clear message if it never is.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(interval)
    raise TimeoutError_(f"timed out waiting for {description} after {timeout}s")


async def await_for(
    condition: Callable[[], T | None],
    timeout: float = 5.0,
    interval: float = 0.01,
    description: str = "condition",
) -> T:
    """Async equivalent of wait_for(), for asyncio-based services (FastAPI
    background tasks, grpc.aio consumers). Polls without blocking the event
    loop."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        await asyncio.sleep(interval)
    raise TimeoutError_(f"timed out waiting for {description} after {timeout}s")


# Usage (in a pytest test):
#
#     # BEFORE (flaky): guesses that the consumer drains 2 items in 300ms.
#     await producer.publish_all(items)
#     await asyncio.sleep(0.3)
#     assert consumer.processed_count() == 2  # fails randomly under load
#
#     # AFTER (reliable): waits for the actual condition.
#     await producer.publish_all(items)
#     count = await await_for(
#         lambda: consumer.processed_count() >= 2 or None,
#         description="2 processed items",
#     )
#     assert count >= 2
#
# Note the `or None` idiom: wait_for/await_for treat 0 and False as "not yet
# satisfied", so a condition whose success value can legitimately be 0 must
# wrap it (e.g. `lambda: result if result is not None else None`).
