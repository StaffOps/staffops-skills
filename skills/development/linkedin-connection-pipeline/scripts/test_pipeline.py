#!/usr/bin/env python3
"""test_pipeline.py -- real tests against pipeline.py, no mocking of the
safety-critical parts.

Run:
    python3 -m unittest test_pipeline -v

Covers, in order of how safety-critical the source design called them out:
  1. The PID-liveness lock, against a REAL subprocess (start it, confirm a
     second acquire is refused, kill -9 it, confirm the lock is then
     reclaimed) -- not just an inspection of acquire_lock()'s code.
  2. The restricted-outcome temporal disambiguation (classify_restricted),
     built on a real SQLite fixture with real inserted runs rows.
  3. Invite pacing keyed off the last SUCCESSFUL send, not the last attempt
     -- a cold account with only failed/transient attempts must not stall.
  4. The daily quota's local-day boundary.
  5. Round-robin account assignment and its cursor persistence.
  6. The retry/reassignment policy (resolve_failed_attempt).
  7. CLI wiring smoke tests for account/settings/lead/import/invite/pending.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pipeline as pl  # noqa: E402
from testing.fake_backend import FakeBackend  # noqa: E402

SCRIPTS_DIR = Path(__file__).resolve().parent


class TempDbTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.conn = pl.open_db(self.data_dir)

    def tearDown(self) -> None:
        self.conn.close()
        self._tmp.cleanup()

    def add_account(self, name: str, **overrides) -> None:
        defaults = dict(
            backend_ref=f"ref-{name}", daily_invite_limit=35, min_invite_interval=15,
            active_start="00:00", active_end="23:59", max_pending_days=10, pending_batch_size=5,
        )
        defaults.update(overrides)
        with self.conn:
            self.conn.execute(
                """INSERT INTO accounts
                   (name, backend_ref, daily_invite_limit, min_invite_interval_minutes,
                    active_start, active_end, max_pending_days, pending_batch_size)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, defaults["backend_ref"], defaults["daily_invite_limit"], defaults["min_invite_interval"],
                 defaults["active_start"], defaults["active_end"], defaults["max_pending_days"],
                 defaults["pending_batch_size"]),
            )

    def add_lead(self, person_ref: str, owner_account: str, **overrides) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO leads (person_ref, full_name, owner_account) VALUES (?, ?, ?)",
                (person_ref, overrides.get("full_name", person_ref), owner_account),
            )


# ---------------------------------------------------------------------------
# 1. PID-liveness lock -- real subprocess
# ---------------------------------------------------------------------------


class TestPidLivenessLock(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_lock_refused_while_live_then_reclaimed_after_kill(self) -> None:
        holder = subprocess.Popen(
            [sys.executable, str(SCRIPTS_DIR / "testing" / "hold_lock.py"), str(self.data_dir), "acct1"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            first_line = holder.stdout.readline().strip()
            if first_line != "LOCKED":
                # Only drain stderr on the failure path -- eagerly reading it
                # (e.g. as an eagerly-evaluated assertEqual message arg) would
                # block forever here, since the still-running holder process
                # never closes its stderr pipe.
                self.fail(f"expected LOCKED, got {first_line!r}: {holder.stderr.read()}")

            # The lock file now names a LIVE process. A second acquire from
            # this test process (a different PID) must be refused.
            self.assertTrue(pl.lock_held_by_live_process(self.data_dir, "acct1"))
            self.assertFalse(pl.acquire_lock(self.data_dir, "acct1"))

            holder.send_signal(signal.SIGKILL)
            holder.wait(timeout=5)

            # Give the OS a moment to finish tearing the process down so
            # os.kill(pid, 0) reliably reports ProcessLookupError.
            deadline = time.time() + 5
            while time.time() < deadline and pl.is_process_alive(holder.pid):
                time.sleep(0.05)
            self.assertFalse(pl.is_process_alive(holder.pid))

            self.assertFalse(pl.lock_held_by_live_process(self.data_dir, "acct1"))
            self.assertTrue(pl.acquire_lock(self.data_dir, "acct1"))
            pl.release_lock(self.data_dir, "acct1")
        finally:
            if holder.poll() is None:
                holder.kill()
                holder.wait()
            holder.stdout.close()
            holder.stderr.close()

    def test_release_only_removes_own_pid(self) -> None:
        self.assertTrue(pl.acquire_lock(self.data_dir, "acct2"))
        lock_file = pl.lock_path(self.data_dir, "acct2")
        lock_file.write_text("999999999")  # simulate a foreign PID owning the file
        pl.release_lock(self.data_dir, "acct2")
        self.assertTrue(lock_file.is_file(), "release_lock must not remove a lock it does not own")


# ---------------------------------------------------------------------------
# 2. Restricted-outcome temporal disambiguation
# ---------------------------------------------------------------------------


class TestRestrictedDisambiguation(TempDbTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._clock = 0

    def _insert_invite_run(self, person_ref: str, account: str, *, success: bool, outcome: str | None) -> None:
        """Inserts a run with an explicit, monotonically increasing
        started_at (one second apart each call) instead of letting SQLite's
        datetime('now') stamp it. classify_restricted's SQL uses a STRICT
        '>' comparison against the last successful send, and SQLite's
        datetime('now') has only whole-second resolution -- several inserts
        in the same fast test can otherwise land in the same wall-clock
        second and collide. Real traffic is naturally seconds-to-minutes
        apart, so this granularity never matters outside a tight test loop;
        pinning explicit timestamps here just makes the test deterministic
        rather than flaky."""
        started_at = f"2024-01-01 00:00:{self._clock:02d}"
        self._clock += 1
        with self.conn:
            self.conn.execute(
                """INSERT INTO runs (person_ref, account, action, outcome, started_at, finished_at, success, error_message)
                   VALUES (?, ?, 'invite', ?, ?, ?, ?, NULL)""",
                (person_ref, account, outcome, started_at, started_at, 1 if success else 0),
            )

    def test_isolated_hit_defers_then_terminates_at_cap(self) -> None:
        """Note the successful send on person-a2 BETWEEN the two restricted
        hits on person-a1 -- it is required, not incidental. The
        account-level streak check (>=2 restricted outcomes since the last
        success, regardless of which lead) runs BEFORE the per-lead check,
        so two restricted hits on the same lead with no successful send
        anywhere in between are indistinguishable from an account-level
        streak (see test_cold_account_cannot_distinguish_... below for that
        exact case). In real operation this is not a problem: the invite
        queue always tries never-tried/least-recently-tried leads first
        (fetch_not_connected_leads' ORDER BY), so a lead that was just
        attempted rotates to the back of the queue -- other leads, and
        typically at least one success, naturally land in between before
        the same lead comes up again."""
        self.add_account("acct1")
        self.add_lead("person-a1", "acct1")
        self.add_lead("person-a2", "acct1")
        self._insert_invite_run("person-a1", "acct1", success=True, outcome=pl.Outcome.SENT.value)

        # First isolated restricted hit on this lead: defer (not exhausted).
        self._insert_invite_run("person-a1", "acct1", success=False, outcome=pl.Outcome.PERSON_RESTRICTED.value)
        decision_1 = pl.classify_restricted(self.conn, "acct1", "person-a1")
        self.assertEqual(decision_1, "defer")

        # Another lead succeeds in between (see docstring) -- this is what
        # lets the SECOND hit on person-a1 be evaluated as isolated rather
        # than folded into an account-level streak.
        self._insert_invite_run("person-a2", "acct1", success=True, outcome=pl.Outcome.SENT.value)

        # Second isolated hit on the SAME lead (default cap is 2): terminate.
        self._insert_invite_run("person-a1", "acct1", success=False, outcome=pl.Outcome.PERSON_RESTRICTED.value)
        decision_2 = pl.classify_restricted(self.conn, "acct1", "person-a1")
        self.assertEqual(decision_2, "terminate")

    def test_streak_without_intervening_success_is_account_level(self) -> None:
        self.add_account("acct1")
        self.add_lead("person-b", "acct1")
        self.add_lead("person-c", "acct1")
        self._insert_invite_run("person-b", "acct1", success=True, outcome=pl.Outcome.SENT.value)

        # Two DIFFERENT leads hit restricted back-to-back with NO successful
        # send in between -> the pattern indicates the ACCOUNT is limited,
        # not either individual lead.
        self._insert_invite_run("person-b", "acct1", success=False, outcome=pl.Outcome.PERSON_RESTRICTED.value)
        self._insert_invite_run("person-c", "acct1", success=False, outcome=pl.Outcome.PERSON_RESTRICTED.value)
        decision = pl.classify_restricted(self.conn, "acct1", "person-c")
        self.assertEqual(decision, "streak")

    def test_success_between_hits_resets_the_streak(self) -> None:
        self.add_account("acct1")
        self.add_lead("person-d", "acct1")
        self.add_lead("person-e", "acct1")
        self._insert_invite_run("person-d", "acct1", success=False, outcome=pl.Outcome.PERSON_RESTRICTED.value)
        # A successful send in between breaks the streak window.
        self._insert_invite_run("person-e", "acct1", success=True, outcome=pl.Outcome.SENT.value)
        self._insert_invite_run("person-e", "acct1", success=False, outcome=pl.Outcome.PERSON_RESTRICTED.value)
        decision = pl.classify_restricted(self.conn, "acct1", "person-e")
        self.assertEqual(decision, "defer")

    def test_via_full_invite_sweep_end_to_end(self) -> None:
        """Drives the SAME disambiguation through do_invite_sweep() (not
        classify_restricted() directly), so the assertion covers the whole
        invite-outcome branch, not just the classifier in isolation.

        A successful send is established FIRST (a "warm" account), which
        matters: with zero successful sends ever recorded, two restricted
        hits are indistinguishable from an account-level streak even if
        they land on the very same lead -- see 'A cold account cannot
        distinguish...' in SKILL.md's temporal-disambiguation section for
        the real worked example of that edge case."""
        self.add_account("acct1", daily_invite_limit=10, min_invite_interval=0)
        self.add_lead("person-warmup", "acct1")
        self.add_lead("person-x", "acct1")
        account = pl.get_account_or_fail(self.conn, "acct1")
        backend = FakeBackend()
        backend.queue_invite_outcome("person-warmup", pl.Outcome.SENT)
        backend.queue_invite_outcome("person-x", pl.Outcome.PERSON_RESTRICTED, "restricted")
        backend.queue_invite_outcome("person-x", pl.Outcome.PERSON_RESTRICTED, "restricted")

        warmup = pl.do_invite_sweep(self.conn, backend, account, limit=1)
        self.assertEqual(warmup["pending"], 1)

        result_1 = pl.do_invite_sweep(self.conn, backend, account, limit=1)
        self.assertEqual(result_1["restricted_deferred"], 1)
        lead = self.conn.execute("SELECT status FROM leads WHERE person_ref = 'person-x'").fetchone()
        self.assertEqual(lead["status"], "not_connected", "an isolated deferred hit must not close the lead")

        result_2 = pl.do_invite_sweep(self.conn, backend, account, limit=1)
        self.assertEqual(result_2["restricted_closed"], 1)
        lead = self.conn.execute("SELECT status, error_type FROM leads WHERE person_ref = 'person-x'").fetchone()
        self.assertEqual(lead["status"], "exhausted")
        self.assertEqual(lead["error_type"], "person_restricted")

    def test_cold_account_cannot_distinguish_streak_from_repeated_isolated_hit(self) -> None:
        """Documents a genuine edge case in the heuristic, not a bug: with
        NO successful send ever recorded for the account, the streak check
        (restricted outcomes since the last success) and the per-lead
        check (restricted outcomes for one lead) can both be satisfied by
        the exact same two rows if the account's very first two attempts,
        against the SAME lead, both come back restricted. The streak check
        runs first, so a cold account backs off (blaming itself) rather
        than closing the lead -- the safer default when there is no
        baseline to tell the two apart."""
        self.add_account("acct1")
        self.add_lead("person-a", "acct1")
        self._insert_invite_run("person-a", "acct1", success=False, outcome=pl.Outcome.PERSON_RESTRICTED.value)
        self._insert_invite_run("person-a", "acct1", success=False, outcome=pl.Outcome.PERSON_RESTRICTED.value)
        decision = pl.classify_restricted(self.conn, "acct1", "person-a")
        self.assertEqual(decision, "streak")


# ---------------------------------------------------------------------------
# 3. Invite pacing keyed off last SUCCESSFUL send only
# ---------------------------------------------------------------------------


class TestInvitePacing(TempDbTestCase):
    def test_cold_account_with_only_failed_attempts_does_not_stall(self) -> None:
        """A cold account (zero successful sends today) with prior TRANSIENT
        attempts must be immediately eligible -- pacing must not treat a
        failed attempt as consuming the interval."""
        self.add_account("acct1", min_invite_interval=30)
        self.add_lead("person-a", "acct1")
        run_id = pl.record_run_start(self.conn, "person-a", "acct1", "invite")
        pl.record_run_finish(self.conn, run_id, success=False, outcome=pl.Outcome.TRANSIENT.value, error_message="timeout")

        day_start = pl.start_of_local_day_utc()
        last_sent = pl.last_successful_invite_at(self.conn, "acct1", day_start)
        self.assertIsNone(last_sent, "a failed attempt must not register as a successful send")
        elapsed = pl.minutes_since(pl.parse_db_utc(last_sent))
        self.assertEqual(elapsed, float("inf"))

    def test_successful_send_does_start_the_pacing_clock(self) -> None:
        self.add_account("acct1", min_invite_interval=30)
        self.add_lead("person-a", "acct1")
        run_id = pl.record_run_start(self.conn, "person-a", "acct1", "invite")
        pl.record_run_finish(self.conn, run_id, success=True, outcome=pl.Outcome.SENT.value, error_message=None)

        day_start = pl.start_of_local_day_utc()
        last_sent = pl.last_successful_invite_at(self.conn, "acct1", day_start)
        self.assertIsNotNone(last_sent)
        elapsed = pl.minutes_since(pl.parse_db_utc(last_sent))
        self.assertLess(elapsed, 1.0)
        self.assertGreaterEqual(elapsed, 0.0)


# ---------------------------------------------------------------------------
# 4. Daily quota — recomputed, bounded to local day
# ---------------------------------------------------------------------------


class TestDailyQuota(TempDbTestCase):
    def test_quota_excludes_runs_before_local_day_start(self) -> None:
        self.add_account("acct1")
        self.add_lead("person-a", "acct1")
        day_start = pl.start_of_local_day_utc()
        # Insert a successful run stamped BEFORE today's boundary directly
        # (bypassing datetime('now')) to prove the count query excludes it.
        with self.conn:
            self.conn.execute(
                """INSERT INTO runs (person_ref, account, action, outcome, started_at, success)
                   VALUES ('person-a', 'acct1', 'invite', 'sent', '2000-01-01 00:00:00', 1)"""
            )
        count = pl.count_successful_invites_since(self.conn, "acct1", day_start)
        self.assertEqual(count, 0)

    def test_quota_includes_runs_after_local_day_start(self) -> None:
        self.add_account("acct1")
        self.add_lead("person-a", "acct1")
        run_id = pl.record_run_start(self.conn, "person-a", "acct1", "invite")
        pl.record_run_finish(self.conn, run_id, success=True, outcome=pl.Outcome.SENT.value, error_message=None)
        day_start = pl.start_of_local_day_utc()
        count = pl.count_successful_invites_since(self.conn, "acct1", day_start)
        self.assertEqual(count, 1)


# ---------------------------------------------------------------------------
# 5. Round-robin assignment + cursor persistence
# ---------------------------------------------------------------------------


class TestRoundRobin(unittest.TestCase):
    def test_cycles_alphabetically_from_the_start_with_no_cursor(self) -> None:
        seq = pl.round_robin_sequence(["a", "b", "c"], None)
        assigned = [next(seq) for _ in range(7)]
        self.assertEqual(assigned, ["a", "b", "c", "a", "b", "c", "a"])

    def test_resumes_right_after_the_persisted_cursor(self) -> None:
        seq = pl.round_robin_sequence(["a", "b", "c"], "b")
        assigned = [next(seq) for _ in range(4)]
        self.assertEqual(assigned, ["c", "a", "b", "c"])

    def test_degrades_gracefully_when_cursor_account_no_longer_active(self) -> None:
        # cursor points at an account that was since removed/paused
        seq = pl.round_robin_sequence(["a", "b"], "removed-account")
        assigned = [next(seq) for _ in range(3)]
        self.assertEqual(assigned, ["a", "b", "a"])


class TestImportCommitRoundRobin(TempDbTestCase):
    def test_even_distribution_and_cursor_persists_across_commits(self) -> None:
        self.add_account("acct-a")
        self.add_account("acct-b")

        def commit_candidates(refs: list[str]) -> None:
            cursor_row = self.conn.execute("SELECT last_assigned_account FROM import_state WHERE id = 1").fetchone()
            rotation = pl.round_robin_sequence(
                pl.active_account_names(self.conn), cursor_row["last_assigned_account"]
            )
            last_assigned = None
            with self.conn:
                for ref in refs:
                    owner = next(rotation)
                    self.conn.execute(
                        "INSERT INTO leads (person_ref, full_name, owner_account) VALUES (?, ?, ?)",
                        (ref, ref, owner),
                    )
                    last_assigned = owner
                self.conn.execute("UPDATE import_state SET last_assigned_account = ? WHERE id = 1", (last_assigned,))

        commit_candidates(["p1", "p2", "p3"])
        owners_batch_1 = {
            r["person_ref"]: r["owner_account"]
            for r in self.conn.execute("SELECT person_ref, owner_account FROM leads").fetchall()
        }
        self.assertEqual(owners_batch_1, {"p1": "acct-a", "p2": "acct-b", "p3": "acct-a"})

        # A second commit call must resume from the persisted cursor
        # ("acct-a" was last assigned), not restart from "acct-a" again.
        commit_candidates(["p4", "p5"])
        owners_batch_2 = {
            r["person_ref"]: r["owner_account"]
            for r in self.conn.execute(
                "SELECT person_ref, owner_account FROM leads WHERE person_ref IN ('p4','p5')"
            ).fetchall()
        }
        self.assertEqual(owners_batch_2, {"p4": "acct-b", "p5": "acct-a"})


# ---------------------------------------------------------------------------
# 6. Retry / reassignment policy
# ---------------------------------------------------------------------------


class TestRetryPolicy(TempDbTestCase):
    def test_default_max_attempts_1_exhausts_immediately(self) -> None:
        self.add_account("acct1")
        self.add_account("acct2")
        self.add_lead("person-a", "acct1")
        run_id = pl.record_run_start(self.conn, "person-a", "acct1", "invite")
        pl.record_run_finish(self.conn, run_id, success=True, outcome=pl.Outcome.SENT.value, error_message=None)

        lead = self.conn.execute("SELECT * FROM leads WHERE person_ref = 'person-a'").fetchone()
        result = pl.resolve_failed_attempt(self.conn, lead)
        self.assertEqual(result, {"outcome": "exhausted", "attempts": 1})
        status = self.conn.execute("SELECT status FROM leads WHERE person_ref = 'person-a'").fetchone()["status"]
        self.assertEqual(status, "exhausted")

    def test_max_attempts_2_reassigns_to_least_loaded_untried_account(self) -> None:
        self.add_account("acct1")
        self.add_account("acct2")
        self.add_account("acct3")
        pl.set_setting(self.conn, "max_connect_attempts", "2")

        # acct3 is pre-loaded so it is NOT the least-loaded candidate.
        self.add_lead("busy-1", "acct3")
        self.add_lead("busy-2", "acct3")
        self.add_lead("person-a", "acct1")
        run_id = pl.record_run_start(self.conn, "person-a", "acct1", "invite")
        pl.record_run_finish(self.conn, run_id, success=True, outcome=pl.Outcome.SENT.value, error_message=None)

        lead = self.conn.execute("SELECT * FROM leads WHERE person_ref = 'person-a'").fetchone()
        result = pl.resolve_failed_attempt(self.conn, lead)
        self.assertEqual(result["outcome"], "reassigned")
        self.assertEqual(result["account"], "acct2")  # least loaded of {acct2, acct3}, acct1 already tried
        updated = self.conn.execute("SELECT owner_account, status FROM leads WHERE person_ref = 'person-a'").fetchone()
        self.assertEqual(updated["owner_account"], "acct2")
        self.assertEqual(updated["status"], "not_connected")

    def test_all_resolves_to_active_account_count(self) -> None:
        self.add_account("acct1")
        self.add_account("acct2")
        pl.set_setting(self.conn, "max_connect_attempts", "all")
        self.assertEqual(pl.resolve_max_attempts(self.conn), 2)


# ---------------------------------------------------------------------------
# 7. CLI wiring smoke tests
# ---------------------------------------------------------------------------


class TestCli(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_cli(self, *args: str) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "pipeline.py"), *args, "--data-dir", str(self.data_dir)],
            capture_output=True, text=True,
        )
        return result.returncode, (result.stdout or result.stderr)

    def test_account_lifecycle(self) -> None:
        code, out = self.run_cli("account", "add", "--name", "work", "--backend-ref", "opaque-ref-1")
        self.assertEqual(code, 0, out)
        self.assertIn('"name": "work"', out)

        code, out = self.run_cli("account", "list")
        self.assertEqual(code, 0, out)
        self.assertIn('"work"', out)

        code, out = self.run_cli("account", "pause", "--name", "work")
        self.assertEqual(code, 0, out)
        self.assertIn('"paused": true', out)

        code, out = self.run_cli("account", "add", "--name", "work", "--backend-ref", "dup")
        self.assertNotEqual(code, 0)
        self.assertIn("already exists", out)

    def test_settings_roundtrip(self) -> None:
        code, out = self.run_cli("settings", "set", "max_connect_attempts", "3")
        self.assertEqual(code, 0, out)
        code, out = self.run_cli("settings", "get", "max_connect_attempts")
        self.assertEqual(code, 0, out)
        self.assertIn('"value": "3"', out)

    def test_lead_and_status(self) -> None:
        self.run_cli("account", "add", "--name", "work", "--backend-ref", "ref-1")
        code, out = self.run_cli(
            "lead", "add", "--person-ref", "p1", "--full-name", "Ada Lovelace",
            "--owner-account", "work", "--list", "Q1",
        )
        self.assertEqual(code, 0, out)
        code, out = self.run_cli("status")
        self.assertEqual(code, 0, out)
        self.assertIn('"not_connected": 1', out)


# ---------------------------------------------------------------------------
# 8. Dynamic --backend loading, exercised through the REAL `python3
#    pipeline.py ...` subprocess entry point (not an in-process import).
#
# This matters specifically because pipeline.py runs as __main__ when
# invoked this way, and load_backend() dynamically imports a separate
# backend module that does `from pipeline import LinkedInBackend`. Testing
# this only via an in-process `import pipeline` (as every other test class
# in this file does) would never exercise the __main__-vs-imported-module
# identity seam -- see the `if __name__ == "__main__":` block at the
# bottom of pipeline.py for the fix and why it is needed.
# ---------------------------------------------------------------------------


WORKING_BACKEND_SOURCE = """
from pipeline import Candidate, ConnectionStatus, InviteResult, LinkedInBackend, Outcome

class WorkingBackend(LinkedInBackend):
    def send_connection_request(self, account_ref, person_ref):
        return InviteResult(outcome=Outcome.SENT)
    def check_connection_status(self, account_ref, person_ref):
        return ConnectionStatus.PENDING
    def withdraw_connection_request(self, account_ref, person_ref):
        return True
    def search_candidates(self, account_ref, query, limit):
        return [Candidate(person_ref=f"p{i}", full_name=f"Person {i}") for i in range(limit)]
"""

BROKEN_BACKEND_SOURCE = """
from pipeline import LinkedInBackend

class BrokenBackend(LinkedInBackend):
    pass  # deliberately missing every abstract method
"""


class TestDynamicBackendLoading(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_cli(self, *args: str) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "pipeline.py"), *args, "--data-dir", str(self.data_dir)],
            capture_output=True, text=True,
        )
        return result.returncode, (result.stdout or result.stderr)

    def test_working_backend_loads_and_invites_via_module_identity_fix(self) -> None:
        backend_file = Path(self._tmp.name) / "working_backend.py"
        backend_file.write_text(WORKING_BACKEND_SOURCE, encoding="utf-8")

        self.run_cli("account", "add", "--name", "work", "--backend-ref", "ref-1",
                     "--active-start", "00:00", "--active-end", "23:59")
        self.run_cli("lead", "add", "--person-ref", "p1", "--full-name", "Ada Lovelace",
                     "--owner-account", "work")

        code, out = self.run_cli("invite", "--account", "work", "--backend", f"{backend_file}:WorkingBackend")
        self.assertEqual(code, 0, out)
        self.assertIn('"pending": 1', out)

    def test_broken_backend_reports_a_clean_error_not_a_traceback(self) -> None:
        backend_file = Path(self._tmp.name) / "broken_backend.py"
        backend_file.write_text(BROKEN_BACKEND_SOURCE, encoding="utf-8")

        self.run_cli("account", "add", "--name", "work", "--backend-ref", "ref-1")
        code, out = self.run_cli("invite", "--account", "work", "--backend", f"{backend_file}:BrokenBackend")
        self.assertNotEqual(code, 0)
        self.assertIn("could not construct backend", out)
        self.assertIn("abstract", out)
        self.assertNotIn("Traceback (most recent call last)", out)


if __name__ == "__main__":
    unittest.main()
