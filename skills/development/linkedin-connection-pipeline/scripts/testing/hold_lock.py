#!/usr/bin/env python3
"""hold_lock.py -- test helper, not part of the pipeline CLI.

Acquires the per-account scheduler lock for ACCOUNT under DATA_DIR and then
sleeps until killed. test_pipeline.py spawns this as a real subprocess to
exercise acquire_lock()/is_process_alive() against an actual live-then-dead
process, rather than mocking os.kill.

Usage: python3 hold_lock.py DATA_DIR ACCOUNT
Prints "LOCKED" to stdout (and flushes) once the lock is held, so the
parent test can wait deterministically instead of sleeping and guessing.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import acquire_lock  # noqa: E402  -- path insert must precede this import


def main() -> int:
    data_dir = Path(sys.argv[1])
    account = sys.argv[2]
    if not acquire_lock(data_dir, account):
        print("FAILED_TO_ACQUIRE", flush=True)
        return 1
    print("LOCKED", flush=True)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
