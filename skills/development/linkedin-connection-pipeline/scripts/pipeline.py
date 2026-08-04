#!/usr/bin/env python3
"""pipeline.py -- vendor-agnostic connection-request pipeline state machine.

Design goal: a single SQLite-backed state machine (accounts, leads, runs,
import batches, settings) plus a liveness-locked scheduler, driven entirely
through one abstract interface -- `LinkedInBackend` -- so the engineering
here (retry policy, pacing, the restricted-outcome disambiguation, the
per-account scheduler lock) never depends on any specific automation
vendor's CLI, JSON error shapes, or rate-limit semantics.

No concrete production backend ships. `testing/fake_backend.py` is a
deterministic in-memory fake for tests and demos only -- see its module
docstring and SKILL.md's "Vendor-agnostic by design" section for why. A
real backend is a `LinkedInBackend` subclass you write and point the CLI at
with `--backend module_or_path:ClassName`.

Zero third-party dependencies. Everything here is stdlib: sqlite3, argparse,
dataclasses, enum, importlib, subprocess, os. A tool whose job is to
orchestrate someone else's automation backend should not need a pip install
just to run its own state machine.

Usage (see SKILL.md for the full walkthrough with real output):
    python3 pipeline.py account add --name work --backend-ref <opaque-ref>
    python3 pipeline.py account list
    python3 pipeline.py settings set max_connect_attempts 2
    python3 pipeline.py lead add --person-ref <ref> --full-name "..." \\
        --owner-account work --list "Q1 outreach"
    python3 pipeline.py lead list [--account NAME] [--status STATUS]
    python3 pipeline.py lead show PERSON_REF
    python3 pipeline.py lead reset PERSON_REF
    python3 pipeline.py import prepare --backend SPEC --searcher-account NAME \\
        --query "..." --list "..." [--limit N]
    python3 pipeline.py import commit --batch BATCH_ID
    python3 pipeline.py import list [--state pending|committed|aborted]
    python3 pipeline.py import show --batch BATCH_ID
    python3 pipeline.py import abort --batch BATCH_ID
    python3 pipeline.py invite --account NAME --backend SPEC [--limit N]
    python3 pipeline.py pending --account NAME --backend SPEC [--limit N]
    python3 pipeline.py tick --backend SPEC [--account NAME]
    python3 pipeline.py status [--account NAME]
    python3 pipeline.py schema

`--backend SPEC` is `path/to/module.py:ClassName` or `dotted.module:ClassName`,
loaded via `load_backend()`. There is no default; every command that talks
to a backend requires `--backend` explicitly.

All DB row timestamps are written and compared via SQLite's own
`datetime('now')` (naive UTC strings, 'YYYY-MM-DD HH:MM:SS') so every writer
in the process trusts one clock. Only the *local* wall-clock day boundary
and active-window comparisons (which SQLite cannot know) are computed in
Python -- see `start_of_local_day_utc()` and `local_hhmm()`.
"""

from __future__ import annotations

import abc
import argparse
import contextlib
import dataclasses
import enum
import importlib
import importlib.util
import json
import math
import os
import platform
import re
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

APP_NAME = "linkedin-connection-pipeline"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def default_data_dir() -> Path:
    """Where the DB, per-account locks, and import tmp files live by
    default. Overridable per-invocation with --data-dir, or globally with
    the PIPELINE_DATA_DIR env var (checked first, mirroring the source
    project's LEADS_DATA_DIR override -- useful for pointing a whole shell
    session at a scratch directory during testing)."""
    if os.environ.get("PIPELINE_DATA_DIR"):
        return Path(os.environ["PIPELINE_DATA_DIR"])
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(xdg) / APP_NAME


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path(data_dir: Path) -> Path:
    return data_dir / "db.sqlite"


def locks_dir(data_dir: Path) -> Path:
    return data_dir / "locks"


def tmp_dir(data_dir: Path) -> Path:
    return data_dir / "tmp"


# ---------------------------------------------------------------------------
# Time helpers
#
# DB timestamps are SQLite datetime('now') strings: naive UTC,
# 'YYYY-MM-DD HH:MM:SS'. The active window (active_start/active_end) and the
# daily-quota boundary are expressed in the machine's LOCAL time -- these
# helpers bridge the two, exactly as the source project's lib/time.mjs does.
# ---------------------------------------------------------------------------

DB_TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def to_db_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime(DB_TS_FORMAT)


def parse_db_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, DB_TS_FORMAT).replace(tzinfo=timezone.utc)


def start_of_local_day_utc(now: datetime | None = None) -> str:
    """UTC string for the start of the current LOCAL day. Bounds 'today'
    quota queries at local midnight regardless of the machine's offset
    from UTC. Recomputed fresh on every call -- there is no cached
    'today' value anywhere in this module, which is what lets the daily
    quota self-correct across restarts and interruptions with no separate
    reset job (see SKILL.md 'Daily quota' section)."""
    now = now or datetime.now(timezone.utc)
    local_now = now.astimezone()
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return to_db_utc(local_midnight)


def local_hhmm(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.astimezone().strftime("%H:%M")


def minutes_since(dt: datetime | None, now: datetime | None = None) -> float:
    if dt is None:
        return math.inf
    now = now or datetime.now(timezone.utc)
    return (now - dt).total_seconds() / 60.0


# ---------------------------------------------------------------------------
# Normalized backend outcome vocabulary
#
# This is the seam that keeps the whole engine vendor-agnostic. Every
# concrete LinkedInBackend implementation is responsible for translating its
# own vendor's response shapes (HTTP status, JSON error `type` strings,
# CLI exit codes, whatever) into exactly one of these values. The
# retry/backoff/pacing/disambiguation logic below switches ONLY on these
# enums -- it never inspects a vendor error string. That is a deliberate
# improvement over the source design this skill generalizes (see "Where
# this comes from" in SKILL.md): the source's restricted-outcome
# disambiguation matched on `error_message LIKE '%restricted sending a
# connection request%'`, a fragile substring match against one vendor's
# human-readable text. Here the same disambiguation matches on
# `outcome == Outcome.PERSON_RESTRICTED`, a value every backend must supply
# regardless of what its own vendor's message text says.
# ---------------------------------------------------------------------------


class Outcome(str, enum.Enum):
    """Result of one attempt to send a connection request."""

    SENT = "sent"
    ALREADY_PENDING = "already_pending"
    ALREADY_CONNECTED = "already_connected"
    # Platform-side limit on the account's ability to send requests right
    # now (daily/weekly cap, note-limit, generic rate limit). NOT a verdict
    # on the lead -- the caller leaves the lead not_connected and backs off
    # the whole account for this cycle.
    ACCOUNT_LIMITED = "account_limited"
    # Ambiguous: LinkedIn-style platforms return the same "restricted"
    # signal both when the ACCOUNT has hit an invite limit and when the
    # PERSON themselves restricts incoming requests. The backend cannot
    # tell these apart from a single response -- only the orchestrator can,
    # by looking at the pattern across recent attempts. See
    # `classify_restricted()`.
    PERSON_RESTRICTED = "person_restricted"
    # Infra/session hiccup: timeout, transient network error, an empty or
    # unparseable response. NOT a verdict on the lead -- retried later.
    TRANSIENT = "transient"
    # A definite, permanent per-lead failure (e.g. the request was
    # evaluated and explicitly refused for a reason that will not change on
    # retry). Terminal.
    TERMINAL_ERROR = "terminal_error"


class ConnectionStatus(str, enum.Enum):
    """Result of checking a person's current connection state."""

    CONNECTED = "connected"
    PENDING = "pending"
    NOT_CONNECTED = "not_connected"  # declined, or the request expired
    PERSON_NOT_FOUND = "person_not_found"  # profile no longer resolves
    TRANSIENT = "transient"


@dataclasses.dataclass(frozen=True)
class InviteResult:
    outcome: Outcome
    message: str | None = None


@dataclasses.dataclass(frozen=True)
class Candidate:
    """One result from a backend search, before it becomes a `leads` row."""

    person_ref: str
    full_name: str
    position: str | None = None
    location: str | None = None


class LinkedInBackend(abc.ABC):
    """The one seam every concrete automation vendor plugs into.

    Why abc.ABC and not typing.Protocol: this interface is loaded
    dynamically by dotted string (`--backend module:ClassName`, see
    `load_backend()` below), not by static type-checking against a known
    import. abc.ABC gives a real, enforced base class -- instantiating a
    subclass that is missing one of the @abstractmethod methods raises
    TypeError immediately, at load time, with a message naming the missing
    method. A Protocol only checks structurally at static-analysis time;
    a dynamically loaded class that happens to duck-type close enough
    would be accepted at runtime and fail confusingly deep inside a
    scheduler tick instead of at load time. Fail loud, fail early, fail
    at the CLI boundary where a human is looking.

    `account_ref` in every method is the account's `backend_ref` column --
    an opaque string this pipeline never interprets, only passes through.
    What it means (a session id, a stored-credential profile name, an
    account index) is entirely up to the concrete backend.
    """

    @abc.abstractmethod
    def send_connection_request(self, account_ref: str, person_ref: str) -> InviteResult:
        """Attempt to send a connection request from account_ref to
        person_ref. Must return an InviteResult, never raise, for any
        outcome representable in the Outcome enum. Raising is reserved for
        conditions the enum cannot represent -- e.g. the backend's own
        session/auth is broken -- which the caller treats as fatal for the
        current sweep (see 'Backend exceptions are fatal' in SKILL.md)."""

    @abc.abstractmethod
    def check_connection_status(self, account_ref: str, person_ref: str) -> ConnectionStatus:
        """Check whether person_ref is connected, still pending, no longer
        reachable, or declined/expired, from account_ref's perspective."""

    @abc.abstractmethod
    def withdraw_connection_request(self, account_ref: str, person_ref: str) -> bool:
        """Withdraw a still-pending request. Returns True on confirmed
        withdrawal, False on failure (the caller records this as an error
        run and does not advance the lead's retry state)."""

    @abc.abstractmethod
    def search_candidates(self, account_ref: str, query: str, limit: int) -> list[Candidate]:
        """Return up to `limit` candidates for `query`, searched as
        account_ref. `query` is an opaque string this pipeline never
        parses -- a saved-search id, free-text terms, a filter DSL,
        whatever the concrete backend's search surface accepts."""


def load_backend(spec: str) -> LinkedInBackend:
    """Load and instantiate a LinkedInBackend from `module_or_path:ClassName`.

    Two forms:
      - a filesystem path ending in .py:  path/to/my_backend.py:MyBackend
      - a dotted importable module:       my_package.my_backend:MyBackend

    Deliberately no constructor arguments here -- a real backend reads its
    own credentials from env vars or a secret store (per this catalog's
    12-factor-app steering: config and secrets never travel as CLI flags),
    not from pipeline.py's argument parser.
    """
    if ":" not in spec:
        raise PipelineError(f"--backend must be 'module_or_path:ClassName', got: {spec!r}")
    module_part, _, class_name = spec.rpartition(":")

    if module_part.endswith(".py"):
        module_path = Path(module_part)
        if not module_path.is_file():
            raise PipelineError(f"backend module not found: {module_path}")
        module_id = f"_pipeline_backend_{module_path.stem}_{uuid.uuid4().hex[:8]}"
        module_spec = importlib.util.spec_from_file_location(module_id, module_path)
        if module_spec is None or module_spec.loader is None:
            raise PipelineError(f"could not load backend module: {module_path}")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
    else:
        try:
            module = importlib.import_module(module_part)
        except ImportError as exc:
            raise PipelineError(f"could not import backend module {module_part!r}: {exc}") from exc

    if not hasattr(module, class_name):
        raise PipelineError(f"{module_part!r} has no attribute {class_name!r}")
    backend_cls = getattr(module, class_name)
    if not (isinstance(backend_cls, type) and issubclass(backend_cls, LinkedInBackend)):
        raise PipelineError(
            f"{spec} is not a LinkedInBackend subclass "
            f"(got {backend_cls!r}) -- see LinkedInBackend in this file"
        )
    try:
        return backend_cls()
    except TypeError as exc:
        # abc.ABC raises TypeError here when an @abstractmethod is left
        # unimplemented -- re-raised as PipelineError so the CLI prints a
        # clean one-line message instead of a full traceback, while
        # keeping Python's own message (it already names every missing
        # method by name).
        raise PipelineError(f"could not construct backend {spec}: {exc}") from exc


# ---------------------------------------------------------------------------
# Errors + output
# ---------------------------------------------------------------------------


class PipelineError(Exception):
    """Raised for any expected failure. Caught once, at the top level, and
    printed without a traceback."""


def emit(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


# ---------------------------------------------------------------------------
# Schema + migrations
#
# MIGRATIONS ARE APPEND-ONLY. Once an entry has shipped, never edit it --
# add a new one instead. This mirrors the source project's lib/db.mjs
# comment verbatim because the reasoning is identical: existing databases
# record the highest applied version and never re-run earlier entries, so
# an in-place edit silently diverges a fresh DB from an already-migrated one.
# ---------------------------------------------------------------------------

MIGRATIONS: list[str] = [
    # 1: initial schema
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS accounts (
        name TEXT PRIMARY KEY,
        backend_ref TEXT NOT NULL,
        paused INTEGER NOT NULL DEFAULT 0,
        daily_invite_limit INTEGER NOT NULL DEFAULT 35,
        min_invite_interval_minutes INTEGER NOT NULL DEFAULT 15,
        active_start TEXT NOT NULL DEFAULT '09:00',
        active_end TEXT NOT NULL DEFAULT '18:00',
        max_pending_days INTEGER NOT NULL DEFAULT 10,
        pending_batch_size INTEGER NOT NULL DEFAULT 5,
        last_action_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS leads (
        person_ref TEXT PRIMARY KEY,
        full_name TEXT NOT NULL,
        position TEXT,
        location TEXT,
        list_name TEXT,
        owner_account TEXT NOT NULL REFERENCES accounts(name) ON UPDATE CASCADE,
        status TEXT NOT NULL DEFAULT 'not_connected',
        sent_at TEXT,
        status_updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        error_type TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_leads_owner_status ON leads(owner_account, status);
    CREATE INDEX IF NOT EXISTS idx_leads_status_sent ON leads(status, sent_at);
    CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at);

    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person_ref TEXT REFERENCES leads(person_ref) ON DELETE SET NULL,
        account TEXT,
        action TEXT NOT NULL,
        outcome TEXT,
        started_at TEXT NOT NULL DEFAULT (datetime('now')),
        finished_at TEXT,
        success INTEGER,
        error_message TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_runs_person ON runs(person_ref);
    CREATE INDEX IF NOT EXISTS idx_runs_account_started ON runs(account, started_at);

    CREATE TABLE IF NOT EXISTS import_batches (
        id TEXT PRIMARY KEY,
        list_name TEXT NOT NULL,
        searcher_account TEXT NOT NULL,
        query TEXT,
        candidate_count INTEGER NOT NULL DEFAULT 0,
        committed_count INTEGER,
        skipped_existing_count INTEGER,
        state TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        committed_at TEXT
    );

    CREATE TABLE IF NOT EXISTS import_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        last_assigned_account TEXT
    );
    INSERT OR IGNORE INTO import_state (id, last_assigned_account) VALUES (1, NULL);

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    INSERT OR IGNORE INTO settings (key, value) VALUES ('max_connect_attempts', '1');
    INSERT OR IGNORE INTO settings (key, value) VALUES ('restricted_lead_attempts', '2');
    """,
]


def migrate(conn: sqlite3.Connection) -> int:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )"""
    )
    current = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] or 0
    for i in range(current, len(MIGRATIONS)):
        version = i + 1
        with conn:
            conn.executescript(MIGRATIONS[i])
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    return len(MIGRATIONS)


def open_db(data_dir: Path, db_file: Path | None = None) -> sqlite3.Connection:
    path = db_file or db_path(data_dir)
    ensure_dir(path.parent)
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    migrate(conn)
    return conn


@contextlib.contextmanager
def with_db(data_dir: Path, db_file: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = open_db(data_dir, db_file)
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def get_setting(conn: sqlite3.Connection, key: str, fallback: str | None) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else fallback


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )


def all_settings(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


def get_account_or_fail(conn: sqlite3.Connection, name: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
    if not row:
        raise PipelineError(f"account {name!r} not found")
    return row


def active_account_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM accounts WHERE paused = 0 ORDER BY name").fetchall()
    return [r["name"] for r in rows]


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def record_run_start(conn: sqlite3.Connection, person_ref: str | None, account: str, action: str) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO runs (person_ref, account, action, started_at) VALUES (?, ?, ?, datetime('now'))",
            (person_ref, account, action),
        )
        return cur.lastrowid


def record_run_finish(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    success: bool,
    outcome: str | None,
    error_message: str | None,
) -> None:
    with conn:
        conn.execute(
            "UPDATE runs SET finished_at = datetime('now'), success = ?, outcome = ?, error_message = ? "
            "WHERE id = ?",
            (1 if success else 0, outcome, error_message, run_id),
        )


# ---------------------------------------------------------------------------
# Retry policy: how many DISTINCT accounts may attempt one lead, and who
# gets it next when an attempt fails.
# ---------------------------------------------------------------------------


def resolve_max_attempts(conn: sqlite3.Connection) -> int:
    raw = get_setting(conn, "max_connect_attempts", "1")
    if raw == "all":
        return conn.execute("SELECT COUNT(*) FROM accounts WHERE paused = 0").fetchone()[0]
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return 1
    return n if n >= 1 else 1


def resolve_restricted_lead_attempts(conn: sqlite3.Connection) -> int:
    raw = get_setting(conn, "restricted_lead_attempts", "2")
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return 2
    return n if n >= 1 else 2


def attempted_accounts(conn: sqlite3.Connection, person_ref: str) -> set[str]:
    """Distinct accounts that have already sent a successful invite to this
    lead. The lead's current owner is among them -- it sent the request
    that just failed."""
    rows = conn.execute(
        "SELECT DISTINCT account FROM runs WHERE person_ref = ? AND action = 'invite' AND success = 1",
        (person_ref,),
    ).fetchall()
    return {r["account"] for r in rows if r["account"]}


def resolve_failed_attempt(conn: sqlite3.Connection, lead: sqlite3.Row) -> dict:
    """Applied when an account's attempt on a lead failed (withdrew a stale
    pending, or the person declined/let it expire). Either hands the lead
    to another untried account, or marks it terminally 'exhausted'.

    Reassignment picks the least-loaded active account that has NOT yet
    tried this lead -- 'load' is its current not_connected+pending count --
    so retries spread the same way the import-time round robin does."""
    tried = attempted_accounts(conn, lead["person_ref"])
    max_attempts = resolve_max_attempts(conn)

    candidates = conn.execute(
        """
        SELECT a.name AS name,
               (SELECT COUNT(*) FROM leads l
                WHERE l.owner_account = a.name AND l.status IN ('not_connected', 'pending')) AS load
        FROM accounts a
        WHERE a.paused = 0
        ORDER BY load ASC, a.name ASC
        """
    ).fetchall()
    eligible = [row for row in candidates if row["name"] not in tried]

    if len(tried) < max_attempts and eligible:
        next_account = eligible[0]["name"]
        with conn:
            conn.execute(
                """UPDATE leads SET owner_account = ?, status = 'not_connected', sent_at = NULL,
                   status_updated_at = datetime('now'), error_type = NULL, error_message = NULL
                   WHERE person_ref = ?""",
                (next_account, lead["person_ref"]),
            )
        return {"outcome": "reassigned", "account": next_account, "attempt_number": len(tried) + 1}

    with conn:
        conn.execute(
            "UPDATE leads SET status = 'exhausted', status_updated_at = datetime('now') WHERE person_ref = ?",
            (lead["person_ref"],),
        )
    return {"outcome": "exhausted", "attempts": len(tried)}


# ---------------------------------------------------------------------------
# Temporal-pattern disambiguation for Outcome.PERSON_RESTRICTED
#
# The single cleverest piece of the design this skill generalizes. A
# "restricted" outcome is genuinely ambiguous from one data point alone: it
# fires both when the ACCOUNT has hit its own request-sending limit and when
# the PERSON restricts incoming requests. Neither the backend nor a single
# run row can tell these apart -- only the PATTERN across recent attempts
# can:
#   - 2+ restricted outcomes in a row for the account, with no successful
#     send in between, means the ACCOUNT is limited. Not the lead's fault:
#     leave it not_connected and back off the whole account for this cycle.
#   - An isolated restricted hit (the account is otherwise sending fine)
#     means the PERSON is the one restricting. Count it against the lead;
#     after `restricted_lead_attempts` isolated hits, close the lead so it
#     never hangs forever waiting on someone who will never accept.
# ---------------------------------------------------------------------------

ACCOUNT_LIMIT_STREAK_THRESHOLD = 2


def classify_restricted(conn: sqlite3.Connection, account: str, person_ref: str) -> str:
    """Returns 'streak' (account-level, back off), 'terminate' (isolated,
    lead has hit its cap, close it), or 'defer' (isolated, under the cap,
    leave it and retry later). Call this AFTER recording the current
    restricted run -- it counts rows already in the table, including the
    one that just happened."""
    last_ok = conn.execute(
        "SELECT MAX(started_at) FROM runs WHERE account = ? AND action = 'invite' AND success = 1",
        (account,),
    ).fetchone()[0]
    streak = conn.execute(
        """SELECT COUNT(*) FROM runs
           WHERE account = ? AND action = 'invite' AND success = 0
             AND outcome = ? AND started_at > COALESCE(?, '0')""",
        (account, Outcome.PERSON_RESTRICTED.value, last_ok),
    ).fetchone()[0]
    if streak >= ACCOUNT_LIMIT_STREAK_THRESHOLD:
        return "streak"

    lead_hits = conn.execute(
        "SELECT COUNT(*) FROM runs WHERE person_ref = ? AND action = 'invite' AND outcome = ?",
        (person_ref, Outcome.PERSON_RESTRICTED.value),
    ).fetchone()[0]
    cap = resolve_restricted_lead_attempts(conn)
    return "terminate" if lead_hits >= cap else "defer"


def count_trailing_person_not_found(conn: sqlite3.Connection, person_ref: str) -> int:
    """Count the most recent consecutive check_status runs for a lead that
    resolved to PERSON_NOT_FOUND. Used to close a lead only after a short
    streak, so one transient miss does not terminate an otherwise-reachable
    person."""
    rows = conn.execute(
        """SELECT outcome FROM runs
           WHERE person_ref = ? AND action = 'check_status'
           ORDER BY started_at DESC, id DESC LIMIT 10""",
        (person_ref,),
    ).fetchall()
    streak = 0
    for row in rows:
        if row["outcome"] != ConnectionStatus.PERSON_NOT_FOUND.value:
            break
        streak += 1
    return streak


PERSON_NOT_FOUND_ATTEMPTS = 2


# ---------------------------------------------------------------------------
# Round-robin account assignment (import commit)
# ---------------------------------------------------------------------------


def round_robin_sequence(active_names: list[str], start_after: str | None) -> Iterator[str]:
    """Yield account names forever, in alphabetical order, resuming right
    after `start_after` (the persisted `import_state.last_assigned_account`
    cursor). If `start_after` is no longer an active account name (paused,
    removed, or None on a fresh DB), starts from the beginning -- the
    cursor degrades gracefully instead of raising."""
    if not active_names:
        return
    if start_after in active_names:
        start_idx = (active_names.index(start_after) + 1) % len(active_names)
    else:
        start_idx = 0
    i = start_idx
    while True:
        yield active_names[i]
        i = (i + 1) % len(active_names)


# ---------------------------------------------------------------------------
# Per-account scheduler lock -- liveness-based, NEVER time-based.
#
# Reclaimed only when the owning process is verifiably dead (a PID-liveness
# probe), never on a timeout. This is what lets a slow-but-alive worker run
# indefinitely without being double-started by the next dispatcher tick, and
# what lets a crashed worker self-heal on the very next tick without a
# separate cleanup job. See SKILL.md's 'Scheduler design' section for the
# full argument and a real subprocess test in test_pipeline.py.
# ---------------------------------------------------------------------------

if os.name == "posix":

    def is_process_alive(pid: int) -> bool:
        if not pid:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but is owned by another user -- still alive.
            return True
        return True

else:  # pragma: no cover -- exercised on Windows only, not this repo's CI

    def is_process_alive(pid: int) -> bool:
        """Windows has no equivalent of POSIX signal 0 -- os.kill(pid, 0)
        on Windows maps to CTRL_C_EVENT, which is not a liveness probe and
        must not be used here. OpenProcess + GetExitCodeProcess via ctypes
        (stdlib) is the liveness-probe equivalent: a still-active process
        reports STILL_ACTIVE (259) as its (not yet real) exit code."""
        if not pid:
            return False
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)


def lock_path(data_dir: Path, account: str) -> Path:
    return locks_dir(data_dir) / f"tick-{account}.lock"


def lock_held_by_live_process(data_dir: Path, account: str) -> bool:
    path = lock_path(data_dir, account)
    if not path.is_file():
        return False
    try:
        pid = int(path.read_text().strip())
    except (OSError, ValueError):
        return False
    return is_process_alive(pid)


def acquire_lock(data_dir: Path, account: str) -> bool:
    """Create the lock file exclusively (O_CREAT|O_EXCL). If it already
    exists, reclaim it ONLY when its recorded PID is verifiably dead --
    never on age/mtime. Two attempts: create, and if that races against a
    just-freed lock, retry once."""
    ensure_dir(locks_dir(data_dir))
    path = lock_path(data_dir, account)
    for _ in range(2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode())
            finally:
                os.close(fd)
            return True
        except FileExistsError:
            try:
                existing_pid = int(path.read_text().strip())
            except (OSError, ValueError):
                return False
            if is_process_alive(existing_pid):
                return False
            try:
                path.unlink()
            except FileNotFoundError:
                pass  # raced with another reclaimer; loop and retry the create
    return False


def release_lock(data_dir: Path, account: str) -> None:
    path = lock_path(data_dir, account)
    try:
        pid = int(path.read_text().strip())
    except (OSError, ValueError):
        return
    if pid == os.getpid():
        with contextlib.suppress(FileNotFoundError):
            path.unlink()


# ---------------------------------------------------------------------------
# Invite sweep (Outcome.SENT/ALREADY_PENDING/... -> lead status transition)
# ---------------------------------------------------------------------------


def count_successful_invites_since(conn: sqlite3.Connection, account: str, since_utc: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM runs WHERE account = ? AND action = 'invite' AND success = 1 AND started_at >= ?",
        (account, since_utc),
    ).fetchone()[0]


def last_successful_invite_at(conn: sqlite3.Connection, account: str, since_utc: str) -> str | None:
    """Bounded to `since_utc` (the start of today) -- deliberately. Pacing
    keys off the last SUCCESSFUL send within the current local day, not off
    any attempt ever. Two consequences, both intentional:
      1. A failed/transient attempt never sends a request, so it must not
         consume the pacing interval -- otherwise a cold account with zero
         successful sends yet would stall for a full interval before its
         very first send, for no reason.
      2. At local-midnight rollover the pacing state resets along with the
         quota, so an account is immediately eligible again at the start of
         its window each day rather than still serving out an interval
         computed against a send made late the previous day.
    """
    row = conn.execute(
        "SELECT MAX(started_at) FROM runs WHERE account = ? AND action = 'invite' AND success = 1 AND started_at >= ?",
        (account, since_utc),
    ).fetchone()
    return row[0] if row else None


def fetch_not_connected_leads(conn: sqlite3.Connection, account: str, limit: int) -> list[sqlite3.Row]:
    """Never-tried leads first, then least-recently-attempted -- a lead
    that keeps failing transiently rotates to the back instead of blocking
    the whole queue (NULL last_try sorts first in SQLite ASC)."""
    return conn.execute(
        """
        SELECT l.person_ref, l.full_name,
               (SELECT MAX(r.started_at) FROM runs r
                WHERE r.person_ref = l.person_ref AND r.action = 'invite') AS last_try
        FROM leads l
        WHERE l.owner_account = ? AND l.status = 'not_connected'
        ORDER BY last_try ASC, l.created_at ASC
        LIMIT ?
        """,
        (account, limit),
    ).fetchall()


def set_lead_status(
    conn: sqlite3.Connection,
    person_ref: str,
    status: str,
    *,
    sent_at: bool = False,
    error_type: str | None = None,
    error_message: str | None = None,
    clear_error: bool = False,
) -> None:
    sets = ["status = ?", "status_updated_at = datetime('now')"]
    params: list[Any] = [status]
    if sent_at:
        sets.append("sent_at = datetime('now')")
    if clear_error:
        sets.append("error_type = NULL")
        sets.append("error_message = NULL")
    elif error_type is not None or error_message is not None:
        sets.append("error_type = ?")
        sets.append("error_message = ?")
        params.extend([error_type, error_message])
    params.append(person_ref)
    with conn:
        conn.execute(f"UPDATE leads SET {', '.join(sets)} WHERE person_ref = ?", params)


def do_invite_sweep(
    conn: sqlite3.Connection,
    backend: LinkedInBackend,
    account: sqlite3.Row,
    limit: int | None,
) -> dict:
    """One account's invite pass: send up to `limit` (or the remaining
    daily budget, whichever is smaller) connection requests. Backs off the
    rest of the pass on the first ACCOUNT_LIMITED or restricted-streak
    outcome -- those signal the ACCOUNT, not the current lead, so burning
    through the rest of the queue against the same wall wastes attempts and
    risks worsening the limit."""
    day_start = start_of_local_day_utc()
    sent_today = count_successful_invites_since(conn, account["name"], day_start)
    remaining = max(0, account["daily_invite_limit"] - sent_today)
    budget = min(limit, remaining) if limit is not None else remaining
    if budget <= 0:
        return {
            "account": account["name"],
            "sent_today": sent_today,
            "daily_limit": account["daily_invite_limit"],
            "processed": 0,
            "message": "daily invite limit reached",
        }

    leads = fetch_not_connected_leads(conn, account["name"], budget)
    summary = {
        "processed": 0, "pending": 0, "connected": 0, "transient": 0,
        "account_limited": 0, "restricted_backoff": 0, "restricted_closed": 0,
        "restricted_deferred": 0, "errors": 0, "aborted": False,
    }
    for lead in leads:
        run_id = record_run_start(conn, lead["person_ref"], account["name"], "invite")
        try:
            result = backend.send_connection_request(account["backend_ref"], lead["person_ref"])
        except Exception as exc:  # backend session/auth broken -- not a per-lead verdict
            record_run_finish(conn, run_id, success=False, outcome=None, error_message=str(exc))
            summary["aborted"] = True
            summary["abort_reason"] = f"backend raised: {exc}"
            break

        if result.outcome is Outcome.SENT or result.outcome is Outcome.ALREADY_PENDING:
            record_run_finish(conn, run_id, success=True, outcome=result.outcome.value, error_message=None)
            set_lead_status(conn, lead["person_ref"], "pending", sent_at=True, clear_error=True)
            summary["pending"] += 1
            summary["processed"] += 1
        elif result.outcome is Outcome.ALREADY_CONNECTED:
            record_run_finish(conn, run_id, success=True, outcome=result.outcome.value, error_message=None)
            set_lead_status(conn, lead["person_ref"], "connected", sent_at=True, clear_error=True)
            summary["connected"] += 1
            summary["processed"] += 1
        elif result.outcome is Outcome.ACCOUNT_LIMITED:
            record_run_finish(conn, run_id, success=False, outcome=result.outcome.value, error_message=result.message)
            summary["account_limited"] += 1
            summary["aborted"] = True
            summary["abort_reason"] = "account invite limit reached"
            break
        elif result.outcome is Outcome.PERSON_RESTRICTED:
            record_run_finish(conn, run_id, success=False, outcome=result.outcome.value, error_message=result.message)
            decision = classify_restricted(conn, account["name"], lead["person_ref"])
            summary["processed"] += 1
            if decision == "streak":
                summary["restricted_backoff"] += 1
                summary["aborted"] = True
                summary["abort_reason"] = "account restricted (pattern indicates account-level limit)"
                break
            if decision == "terminate":
                set_lead_status(
                    conn, lead["person_ref"], "exhausted",
                    error_type="person_restricted", error_message=result.message,
                )
                summary["restricted_closed"] += 1
            else:
                summary["restricted_deferred"] += 1
        elif result.outcome is Outcome.TRANSIENT:
            record_run_finish(conn, run_id, success=False, outcome=result.outcome.value, error_message=result.message)
            summary["transient"] += 1
            summary["processed"] += 1
        else:  # TERMINAL_ERROR
            record_run_finish(conn, run_id, success=False, outcome=result.outcome.value, error_message=result.message)
            set_lead_status(
                conn, lead["person_ref"], "error",
                error_type="terminal_error", error_message=result.message,
            )
            summary["errors"] += 1
            summary["processed"] += 1

    with conn:
        conn.execute(
            "UPDATE accounts SET last_action_at = datetime('now') WHERE name = ?",
            (account["name"],),
        )
    return {"account": account["name"], "daily_limit": account["daily_invite_limit"],
            "sent_today_before": sent_today, "budget": budget, **summary}


# ---------------------------------------------------------------------------
# Pending sweep (status check + withdraw stale pending -> retry policy)
# ---------------------------------------------------------------------------


def fetch_due_pending_leads(conn: sqlite3.Connection, account: str, max_pending_days: int, limit: int | None) -> list[sqlite3.Row]:
    sql = """
        SELECT person_ref, full_name, sent_at FROM leads
        WHERE owner_account = ? AND status = 'pending' AND sent_at IS NOT NULL
          AND sent_at < datetime('now', ?)
        ORDER BY sent_at ASC
    """
    params: list[Any] = [account, f"-{max_pending_days} days"]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def do_pending_sweep(
    conn: sqlite3.Connection,
    backend: LinkedInBackend,
    account: sqlite3.Row,
    limit: int | None,
) -> dict:
    leads = fetch_due_pending_leads(conn, account["name"], account["max_pending_days"], limit)
    summary = {"processed": 0, "connected": 0, "reassigned": 0, "exhausted": 0, "errors": 0, "aborted": False}

    for lead in leads:
        run_id = record_run_start(conn, lead["person_ref"], account["name"], "check_status")
        try:
            status = backend.check_connection_status(account["backend_ref"], lead["person_ref"])
        except Exception as exc:
            record_run_finish(conn, run_id, success=False, outcome=None, error_message=str(exc))
            summary["aborted"] = True
            summary["abort_reason"] = f"backend raised: {exc}"
            break

        if status is ConnectionStatus.CONNECTED:
            record_run_finish(conn, run_id, success=True, outcome=status.value, error_message=None)
            set_lead_status(conn, lead["person_ref"], "connected", clear_error=True)
            summary["connected"] += 1
            summary["processed"] += 1
        elif status is ConnectionStatus.NOT_CONNECTED:
            record_run_finish(conn, run_id, success=False, outcome=status.value, error_message="declined or expired")
            res = resolve_failed_attempt(conn, lead)
            summary["reassigned" if res["outcome"] == "reassigned" else "exhausted"] += 1
            summary["processed"] += 1
        elif status is ConnectionStatus.PENDING:
            record_run_finish(conn, run_id, success=True, outcome=status.value, error_message=None)
            withdraw_run_id = record_run_start(conn, lead["person_ref"], account["name"], "withdraw")
            try:
                withdrawn = backend.withdraw_connection_request(account["backend_ref"], lead["person_ref"])
            except Exception as exc:
                record_run_finish(conn, withdraw_run_id, success=False, outcome=None, error_message=str(exc))
                summary["aborted"] = True
                summary["abort_reason"] = f"backend raised on withdraw: {exc}"
                break
            record_run_finish(
                conn, withdraw_run_id, success=withdrawn, outcome=None,
                error_message=None if withdrawn else "withdraw failed",
            )
            if withdrawn:
                res = resolve_failed_attempt(conn, lead)
                summary["reassigned" if res["outcome"] == "reassigned" else "exhausted"] += 1
            else:
                summary["errors"] += 1
            summary["processed"] += 1
        elif status is ConnectionStatus.PERSON_NOT_FOUND:
            record_run_finish(conn, run_id, success=False, outcome=status.value, error_message="person not found")
            streak = count_trailing_person_not_found(conn, lead["person_ref"])
            if streak >= PERSON_NOT_FOUND_ATTEMPTS:
                set_lead_status(
                    conn, lead["person_ref"], "exhausted",
                    error_type="person_not_found", error_message="profile no longer resolves",
                )
                summary["exhausted"] += 1
            else:
                summary["errors"] += 1
            summary["processed"] += 1
        else:  # TRANSIENT
            record_run_finish(conn, run_id, success=False, outcome=status.value, error_message="transient check failure")
            summary["errors"] += 1
            summary["processed"] += 1

    return {"account": account["name"], "max_pending_days": account["max_pending_days"], **summary}


# ---------------------------------------------------------------------------
# Scheduler: dispatcher (never blocks, spawns detached workers) / worker
# (holds the per-account lock for its whole lifetime: invite first, then
# drain due pending checks).
# ---------------------------------------------------------------------------


def spawn_detached_worker(data_dir: Path, backend_spec: str, account: str, db_file: Path | None) -> None:
    args = [sys.executable, str(Path(__file__).resolve()), "tick",
            "--account", account, "--backend", backend_spec, "--data-dir", str(data_dir)]
    if db_file is not None:
        args += ["--db", str(db_file)]
    if os.name == "posix":
        subprocess.Popen(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    else:  # pragma: no cover -- exercised on Windows only, not this repo's CI
        subprocess.Popen(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,  # type: ignore[attr-defined]
        )


def tick_dispatch(data_dir: Path, backend_spec: str, db_file: Path | None) -> dict:
    """Spawn one detached worker per eligible account, then return
    immediately -- never waits on a worker. A slow or busy account can
    never hold up the tick for any other account."""
    with with_db(data_dir, db_file) as conn:
        accounts = conn.execute(
            "SELECT name, active_start, active_end FROM accounts WHERE paused = 0 ORDER BY name"
        ).fetchall()

    now_hhmm = local_hhmm()
    dispatched, skipped = [], {}
    for acc in accounts:
        if now_hhmm < acc["active_start"] or now_hhmm > acc["active_end"]:
            skipped[acc["name"]] = "outside_active_window"
        elif lock_held_by_live_process(data_dir, acc["name"]):
            skipped[acc["name"]] = "previous_run_still_active"
        else:
            spawn_detached_worker(data_dir, backend_spec, acc["name"], db_file)
            dispatched.append(acc["name"])

    result = {"now": datetime.now(timezone.utc).isoformat(), "local_time": now_hhmm, "dispatched": dispatched}
    if skipped:
        result["skipped"] = skipped
    return result


def tick_worker(data_dir: Path, backend_spec: str, account: str, db_file: Path | None) -> dict:
    if not acquire_lock(data_dir, account):
        return {"account": account, "skipped": "already_running"}
    try:
        backend = load_backend(backend_spec)
        with with_db(data_dir, db_file) as conn:
            acc = conn.execute("SELECT * FROM accounts WHERE name = ? AND paused = 0", (account,)).fetchone()
            if not acc:
                return {"account": account, "skipped": "not_active"}

            now_hhmm = local_hhmm()
            if now_hhmm < acc["active_start"] or now_hhmm > acc["active_end"]:
                return {"account": account, "skipped": "outside_active_window"}

            day_start = start_of_local_day_utc()
            sent_today = count_successful_invites_since(conn, account, day_start)
            not_connected = conn.execute(
                "SELECT COUNT(*) FROM leads WHERE owner_account = ? AND status = 'not_connected'", (account,)
            ).fetchone()[0]

            did: list[dict] = []
            skipped: dict[str, str] = {}

            # 1) INVITE -- highest priority, always attempted before pending
            #    work so a connect can never be delayed by a backlog drain.
            if not_connected == 0:
                skipped["invite"] = "no_not_connected_leads"
            elif sent_today >= acc["daily_invite_limit"]:
                skipped["invite"] = "daily_quota_reached"
            else:
                last_sent = parse_db_utc(last_successful_invite_at(conn, account, day_start))
                elapsed = minutes_since(last_sent)
                if elapsed >= acc["min_invite_interval_minutes"]:
                    result = do_invite_sweep(conn, backend, acc, limit=1)
                    did.append({"op": "invite", **result})
                else:
                    remaining = round(acc["min_invite_interval_minutes"] - elapsed)
                    skipped["invite"] = f"paced_waiting ({remaining}min left)"

            # 2) PENDING -- drain the whole due backlog in one go (each
            #    lead is one backend round trip; there is no artificial
            #    per-tick cap here beyond the account's own
            #    pending_batch_size, unlike the invite side which is
            #    capped at one per tick by the pacing interval above).
            due_before = conn.execute(
                """SELECT COUNT(*) FROM leads WHERE owner_account = ? AND status = 'pending'
                   AND sent_at IS NOT NULL AND sent_at < datetime('now', ?)""",
                (account, f"-{acc['max_pending_days']} days"),
            ).fetchone()[0]
            if due_before > 0:
                result = do_pending_sweep(conn, backend, acc, limit=acc["pending_batch_size"])
                did.append({"op": "pending", **result})
            else:
                skipped["pending"] = "no_due_pending"

            return {"account": account, "did": did, **({"skipped": skipped} if skipped else {})}
    finally:
        release_lock(data_dir, account)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-dir", default=None, help="override the default data directory")
    parser.add_argument("--db", default=None, help="override the DB file path directly (mainly for tests)")


def _resolve_dirs(args: argparse.Namespace) -> tuple[Path, Path | None]:
    data_dir = Path(args.data_dir) if args.data_dir else default_data_dir()
    db_file = Path(args.db) if args.db else None
    return data_dir, db_file


TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def cmd_account(args: argparse.Namespace) -> None:
    data_dir, db_file = _resolve_dirs(args)
    with with_db(data_dir, db_file) as conn:
        if args.account_cmd == "list":
            rows = conn.execute(
                """SELECT name, backend_ref, paused, daily_invite_limit, min_invite_interval_minutes,
                          active_start, active_end, max_pending_days, pending_batch_size,
                          last_action_at, created_at FROM accounts ORDER BY name"""
            ).fetchall()
            emit([dict(r) | {"paused": bool(r["paused"])} for r in rows])
        elif args.account_cmd == "add":
            if not TIME_RE.match(args.active_start) or not TIME_RE.match(args.active_end):
                raise PipelineError("--active-start/--active-end must be HH:MM (24h)")
            if args.active_start >= args.active_end:
                raise PipelineError("--active-start must be earlier than --active-end")
            try:
                with conn:
                    conn.execute(
                        """INSERT INTO accounts
                           (name, backend_ref, daily_invite_limit, min_invite_interval_minutes,
                            active_start, active_end, max_pending_days, pending_batch_size)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (args.name, args.backend_ref, args.daily_invite_limit, args.min_invite_interval,
                         args.active_start, args.active_end, args.max_pending_days, args.pending_batch_size),
                    )
            except sqlite3.IntegrityError as exc:
                raise PipelineError(f"account {args.name!r} already exists") from exc
            emit(dict(get_account_or_fail(conn, args.name)) | {"paused": False})
        elif args.account_cmd == "update":
            sets, params = [], []
            for flag, column, validator in (
                ("daily_invite_limit", "daily_invite_limit", lambda v: 1 <= v <= 500),
                ("min_invite_interval", "min_invite_interval_minutes", lambda v: 1 <= v <= 1440),
                ("max_pending_days", "max_pending_days", lambda v: 1 <= v <= 365),
                ("pending_batch_size", "pending_batch_size", lambda v: 1 <= v <= 200),
            ):
                value = getattr(args, flag)
                if value is not None:
                    if not validator(value):
                        raise PipelineError(f"--{flag.replace('_', '-')} out of range")
                    sets.append(f"{column} = ?")
                    params.append(value)
            current = get_account_or_fail(conn, args.name)
            start = args.active_start or current["active_start"]
            end = args.active_end or current["active_end"]
            if args.active_start:
                if not TIME_RE.match(args.active_start):
                    raise PipelineError("--active-start must be HH:MM")
                sets.append("active_start = ?")
                params.append(args.active_start)
            if args.active_end:
                if not TIME_RE.match(args.active_end):
                    raise PipelineError("--active-end must be HH:MM")
                sets.append("active_end = ?")
                params.append(args.active_end)
            if start >= end:
                raise PipelineError("active_start must be earlier than active_end")
            if args.backend_ref:
                sets.append("backend_ref = ?")
                params.append(args.backend_ref)
            if not sets:
                raise PipelineError("no fields to update")
            params.append(args.name)
            with conn:
                conn.execute(f"UPDATE accounts SET {', '.join(sets)} WHERE name = ?", params)
            emit(dict(get_account_or_fail(conn, args.name)) | {"paused": bool(get_account_or_fail(conn, args.name)["paused"])})
        elif args.account_cmd in ("pause", "resume"):
            paused = 1 if args.account_cmd == "pause" else 0
            with conn:
                cur = conn.execute("UPDATE accounts SET paused = ? WHERE name = ?", (paused, args.name))
            if cur.rowcount == 0:
                raise PipelineError(f"account {args.name!r} not found")
            emit({"name": args.name, "paused": bool(paused)})
        elif args.account_cmd == "rename":
            try:
                with conn:
                    cur = conn.execute("UPDATE accounts SET name = ? WHERE name = ?", (args.new_name, args.name))
            except sqlite3.IntegrityError as exc:
                raise PipelineError(f"account {args.new_name!r} already exists") from exc
            if cur.rowcount == 0:
                raise PipelineError(f"account {args.name!r} not found")
            emit({"renamed_from": args.name, "renamed_to": args.new_name})
        elif args.account_cmd == "remove":
            n = conn.execute("SELECT COUNT(*) FROM leads WHERE owner_account = ?", (args.name,)).fetchone()[0]
            if n > 0 and not args.force:
                raise PipelineError(
                    f"account {args.name!r} owns {n} lead(s) -- pass --force to delete it "
                    "and leave those leads orphaned"
                )
            with conn:
                cur = conn.execute("DELETE FROM accounts WHERE name = ?", (args.name,))
            if cur.rowcount == 0:
                raise PipelineError(f"account {args.name!r} not found")
            emit({"removed": args.name, "orphaned_leads": n})


def cmd_settings(args: argparse.Namespace) -> None:
    data_dir, db_file = _resolve_dirs(args)
    with with_db(data_dir, db_file) as conn:
        if args.settings_cmd == "list":
            emit(all_settings(conn))
        elif args.settings_cmd == "get":
            emit({"key": args.key, "value": get_setting(conn, args.key, None)})
        elif args.settings_cmd == "set":
            if args.key == "max_connect_attempts":
                if args.value != "all":
                    n = int(args.value)
                    if not (1 <= n <= 50):
                        raise PipelineError("max_connect_attempts must be 1-50 or 'all'")
            elif args.key == "restricted_lead_attempts":
                n = int(args.value)
                if not (1 <= n <= 50):
                    raise PipelineError("restricted_lead_attempts must be 1-50")
            set_setting(conn, args.key, args.value)
            emit({"key": args.key, "value": args.value})


def cmd_lead(args: argparse.Namespace) -> None:
    data_dir, db_file = _resolve_dirs(args)
    with with_db(data_dir, db_file) as conn:
        if args.lead_cmd == "add":
            get_account_or_fail(conn, args.owner_account)
            try:
                with conn:
                    conn.execute(
                        """INSERT INTO leads (person_ref, full_name, position, location, list_name, owner_account)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (args.person_ref, args.full_name, args.position, args.location, args.list, args.owner_account),
                    )
            except sqlite3.IntegrityError as exc:
                raise PipelineError(f"lead {args.person_ref!r} already exists") from exc
            emit(dict(conn.execute("SELECT * FROM leads WHERE person_ref = ?", (args.person_ref,)).fetchone()))
        elif args.lead_cmd == "list":
            sql = "SELECT * FROM leads WHERE 1=1"
            params: list[Any] = []
            if args.account:
                sql += " AND owner_account = ?"
                params.append(args.account)
            if args.status:
                sql += " AND status = ?"
                params.append(args.status)
            if args.list:
                sql += " AND list_name = ?"
                params.append(args.list)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(args.limit)
            rows = conn.execute(sql, params).fetchall()
            emit([dict(r) for r in rows])
        elif args.lead_cmd == "show":
            row = conn.execute("SELECT * FROM leads WHERE person_ref = ?", (args.person_ref,)).fetchone()
            if not row:
                raise PipelineError(f"lead {args.person_ref!r} not found")
            runs = conn.execute(
                "SELECT * FROM runs WHERE person_ref = ? ORDER BY started_at DESC, id DESC LIMIT 25",
                (args.person_ref,),
            ).fetchall()
            emit({"lead": dict(row), "recent_runs": [dict(r) for r in runs]})
        elif args.lead_cmd == "reset":
            with conn:
                cur = conn.execute(
                    """UPDATE leads SET status = 'not_connected', status_updated_at = datetime('now'),
                       error_type = NULL, error_message = NULL WHERE person_ref = ?""",
                    (args.person_ref,),
                )
            if cur.rowcount == 0:
                raise PipelineError(f"lead {args.person_ref!r} not found")
            emit({"reset": args.person_ref, "status": "not_connected"})


def cmd_import(args: argparse.Namespace) -> None:
    data_dir, db_file = _resolve_dirs(args)
    with with_db(data_dir, db_file) as conn:
        if args.import_cmd == "prepare":
            account = get_account_or_fail(conn, args.searcher_account)
            backend = load_backend(args.backend)
            candidates = backend.search_candidates(account["backend_ref"], args.query, args.limit)
            existing = {r["person_ref"] for r in conn.execute("SELECT person_ref FROM leads").fetchall()}
            new_candidates = [c for c in candidates if c.person_ref not in existing]

            batch_id = uuid.uuid4().hex[:12]
            candidates_file = ensure_dir(tmp_dir(data_dir)) / f"import-{batch_id}.json"
            candidates_file.write_text(
                json.dumps([dataclasses.asdict(c) for c in new_candidates], indent=2), encoding="utf-8"
            )
            with conn:
                conn.execute(
                    """INSERT INTO import_batches
                       (id, list_name, searcher_account, query, candidate_count, skipped_existing_count, state)
                       VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
                    (batch_id, args.list, args.searcher_account, args.query,
                     len(candidates), len(candidates) - len(new_candidates)),
                )
            emit({
                "batch_id": batch_id, "candidate_count": len(candidates),
                "new_count": len(new_candidates),
                "skipped_existing_count": len(candidates) - len(new_candidates),
                "candidates_file": str(candidates_file),
            })
        elif args.import_cmd == "commit":
            batch = conn.execute("SELECT * FROM import_batches WHERE id = ?", (args.batch,)).fetchone()
            if not batch:
                raise PipelineError(f"batch {args.batch!r} not found")
            if batch["state"] != "pending":
                raise PipelineError(f"batch is in state {batch['state']!r}, cannot commit")

            active = active_account_names(conn)
            if not active:
                raise PipelineError("no active (non-paused) accounts available for lead assignment")

            candidates_file = tmp_dir(data_dir) / f"import-{args.batch}.json"
            if not candidates_file.is_file():
                raise PipelineError(f"candidates file not found: {candidates_file}")
            candidates = json.loads(candidates_file.read_text(encoding="utf-8"))

            cursor_row = conn.execute("SELECT last_assigned_account FROM import_state WHERE id = 1").fetchone()
            rotation = round_robin_sequence(active, cursor_row["last_assigned_account"] if cursor_row else None)

            assigned = 0
            skipped_existing = 0
            last_assigned = None
            with conn:
                for cand in candidates:
                    owner = next(rotation)
                    cur = conn.execute(
                        """INSERT OR IGNORE INTO leads
                           (person_ref, full_name, position, location, list_name, owner_account)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (cand["person_ref"], cand["full_name"], cand.get("position"),
                         cand.get("location"), batch["list_name"], owner),
                    )
                    if cur.rowcount == 1:
                        assigned += 1
                        last_assigned = owner
                    else:
                        skipped_existing += 1
                if last_assigned is not None:
                    conn.execute(
                        "UPDATE import_state SET last_assigned_account = ? WHERE id = 1", (last_assigned,)
                    )
                conn.execute(
                    """UPDATE import_batches SET state = 'committed', committed_count = ?,
                       skipped_existing_count = COALESCE(skipped_existing_count, 0) + ?, committed_at = datetime('now')
                       WHERE id = ?""",
                    (assigned, skipped_existing, args.batch),
                )
            emit({"batch_id": args.batch, "assigned": assigned, "skipped_existing": skipped_existing})
        elif args.import_cmd == "list":
            sql = "SELECT * FROM import_batches"
            params: list[Any] = []
            if args.state:
                sql += " WHERE state = ?"
                params.append(args.state)
            sql += " ORDER BY created_at DESC"
            emit([dict(r) for r in conn.execute(sql, params).fetchall()])
        elif args.import_cmd == "show":
            row = conn.execute("SELECT * FROM import_batches WHERE id = ?", (args.batch,)).fetchone()
            if not row:
                raise PipelineError(f"batch {args.batch!r} not found")
            emit(dict(row))
        elif args.import_cmd == "abort":
            with conn:
                cur = conn.execute(
                    "UPDATE import_batches SET state = 'aborted' WHERE id = ? AND state = 'pending'",
                    (args.batch,),
                )
            if cur.rowcount == 0:
                raise PipelineError(f"batch {args.batch!r} not found or not in state 'pending'")
            emit({"aborted": args.batch})


def cmd_invite(args: argparse.Namespace) -> None:
    data_dir, db_file = _resolve_dirs(args)
    backend = load_backend(args.backend)
    with with_db(data_dir, db_file) as conn:
        account = get_account_or_fail(conn, args.account)
        if account["paused"]:
            emit({"account": args.account, "skipped": "paused"})
            return
        emit(do_invite_sweep(conn, backend, account, args.limit))


def cmd_pending(args: argparse.Namespace) -> None:
    data_dir, db_file = _resolve_dirs(args)
    backend = load_backend(args.backend)
    with with_db(data_dir, db_file) as conn:
        account = get_account_or_fail(conn, args.account)
        if account["paused"]:
            emit({"account": args.account, "skipped": "paused"})
            return
        emit(do_pending_sweep(conn, backend, account, args.limit))


def cmd_tick(args: argparse.Namespace) -> None:
    data_dir, db_file = _resolve_dirs(args)
    if args.account:
        emit(tick_worker(data_dir, args.backend, args.account, db_file))
    else:
        emit(tick_dispatch(data_dir, args.backend, db_file))


def cmd_status(args: argparse.Namespace) -> None:
    data_dir, db_file = _resolve_dirs(args)
    with with_db(data_dir, db_file) as conn:
        names = [args.account] if args.account else active_account_names(conn) + [
            r["name"] for r in conn.execute("SELECT name FROM accounts WHERE paused = 1").fetchall()
        ]
        day_start = start_of_local_day_utc()
        report = []
        for name in names:
            acc = conn.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
            if not acc:
                continue
            sent_today = count_successful_invites_since(conn, name, day_start)
            status_counts = {
                r["status"]: r["c"]
                for r in conn.execute(
                    "SELECT status, COUNT(*) AS c FROM leads WHERE owner_account = ? GROUP BY status", (name,)
                ).fetchall()
            }
            report.append({
                "account": name, "paused": bool(acc["paused"]),
                "daily_limit": acc["daily_invite_limit"], "sent_today": sent_today,
                "remaining_today": max(0, acc["daily_invite_limit"] - sent_today),
                "status_counts": status_counts, "last_action_at": acc["last_action_at"],
            })
        emit(report)


def cmd_schema(_args: argparse.Namespace) -> None:
    emit({
        "tables": {
            "accounts": "name PK, backend_ref, paused, daily_invite_limit, min_invite_interval_minutes, "
                         "active_start, active_end, max_pending_days, pending_batch_size, last_action_at, created_at",
            "leads": "person_ref PK, full_name, position, location, list_name, owner_account FK, "
                     "status [not_connected|pending|connected|exhausted|error], sent_at, status_updated_at, "
                     "error_type, error_message, created_at",
            "runs": "id PK, person_ref FK, account, action [invite|check_status|withdraw], outcome, "
                    "started_at, finished_at, success, error_message",
            "import_batches": "id PK, list_name, searcher_account, query, candidate_count, committed_count, "
                               "skipped_existing_count, state [pending|committed|aborted], created_at, committed_at",
            "import_state": "id=1 singleton, last_assigned_account -- round-robin cursor for import commit",
            "settings": "key PK, value -- e.g. max_connect_attempts ('1'|'N'|'all'), restricted_lead_attempts (int)",
        },
        "outcome_enum": [o.value for o in Outcome],
        "connection_status_enum": [s.value for s in ConnectionStatus],
        "timezone_notes": {
            "all_timestamps": "SQLite datetime('now'), naive UTC strings",
            "active_window_and_daily_quota": "computed against LOCAL time in Python, not UTC",
        },
    })


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    # NOTE: --data-dir/--db are added to each LEAF subparser (e.g. "account
    # add"), not the category parser ("account") -- argparse subparsers
    # consume the remaining argv once a subcommand name is matched, so a
    # flag attached only to the parent "account" parser would have to
    # appear BEFORE "add" on the command line. Attaching it to every leaf
    # instead lets every example in SKILL.md put --data-dir/--db at the end,
    # which reads naturally and matches how every other flag in this CLI is
    # written.
    p = sub.add_parser("account")
    acct_sub = p.add_subparsers(dest="account_cmd", required=True)

    pl = acct_sub.add_parser("list")
    _add_common(pl)
    pl.set_defaults(func=cmd_account)

    pa = acct_sub.add_parser("add")
    _add_common(pa)
    pa.add_argument("--name", required=True)
    pa.add_argument("--backend-ref", required=True)
    pa.add_argument("--daily-invite-limit", type=int, default=35)
    pa.add_argument("--min-invite-interval", type=int, default=15)
    pa.add_argument("--active-start", default="09:00")
    pa.add_argument("--active-end", default="18:00")
    pa.add_argument("--max-pending-days", type=int, default=10)
    pa.add_argument("--pending-batch-size", type=int, default=5)
    pa.set_defaults(func=cmd_account)

    pu = acct_sub.add_parser("update")
    _add_common(pu)
    pu.add_argument("--name", required=True)
    pu.add_argument("--backend-ref")
    pu.add_argument("--daily-invite-limit", type=int)
    pu.add_argument("--min-invite-interval", type=int)
    pu.add_argument("--active-start")
    pu.add_argument("--active-end")
    pu.add_argument("--max-pending-days", type=int)
    pu.add_argument("--pending-batch-size", type=int)
    pu.set_defaults(func=cmd_account)

    for name in ("pause", "resume"):
        pp = acct_sub.add_parser(name)
        _add_common(pp)
        pp.add_argument("--name", required=True)
        pp.set_defaults(func=cmd_account)

    pr = acct_sub.add_parser("rename")
    _add_common(pr)
    pr.add_argument("--name", required=True)
    pr.add_argument("--new-name", required=True)
    pr.set_defaults(func=cmd_account)

    prm = acct_sub.add_parser("remove")
    _add_common(prm)
    prm.add_argument("--name", required=True)
    prm.add_argument("--force", action="store_true")
    prm.set_defaults(func=cmd_account)

    p = sub.add_parser("settings")
    set_sub = p.add_subparsers(dest="settings_cmd", required=True)
    psl = set_sub.add_parser("list")
    _add_common(psl)
    psl.set_defaults(func=cmd_settings)
    pg = set_sub.add_parser("get")
    _add_common(pg)
    pg.add_argument("key")
    pg.set_defaults(func=cmd_settings)
    ps = set_sub.add_parser("set")
    _add_common(ps)
    ps.add_argument("key")
    ps.add_argument("value")
    ps.set_defaults(func=cmd_settings)

    p = sub.add_parser("lead")
    lead_sub = p.add_subparsers(dest="lead_cmd", required=True)
    la = lead_sub.add_parser("add")
    _add_common(la)
    la.add_argument("--person-ref", required=True)
    la.add_argument("--full-name", required=True)
    la.add_argument("--owner-account", required=True)
    la.add_argument("--list", dest="list", default=None)
    la.add_argument("--position", default=None)
    la.add_argument("--location", default=None)
    la.set_defaults(func=cmd_lead)
    ll = lead_sub.add_parser("list")
    _add_common(ll)
    ll.add_argument("--account")
    ll.add_argument("--status")
    ll.add_argument("--list", dest="list")
    ll.add_argument("--limit", type=int, default=100)
    ll.set_defaults(func=cmd_lead)
    lsh = lead_sub.add_parser("show")
    _add_common(lsh)
    lsh.add_argument("person_ref")
    lsh.set_defaults(func=cmd_lead)
    lr = lead_sub.add_parser("reset")
    _add_common(lr)
    lr.add_argument("person_ref")
    lr.set_defaults(func=cmd_lead)

    p = sub.add_parser("import")
    imp_sub = p.add_subparsers(dest="import_cmd", required=True)
    ip = imp_sub.add_parser("prepare")
    _add_common(ip)
    ip.add_argument("--backend", required=True)
    ip.add_argument("--searcher-account", required=True)
    ip.add_argument("--query", required=True)
    ip.add_argument("--list", required=True)
    ip.add_argument("--limit", type=int, default=100)
    ip.set_defaults(func=cmd_import)
    ic = imp_sub.add_parser("commit")
    _add_common(ic)
    ic.add_argument("--batch", required=True)
    ic.set_defaults(func=cmd_import)
    il = imp_sub.add_parser("list")
    _add_common(il)
    il.add_argument("--state", choices=["pending", "committed", "aborted"])
    il.set_defaults(func=cmd_import)
    ish = imp_sub.add_parser("show")
    _add_common(ish)
    ish.add_argument("--batch", required=True)
    ish.set_defaults(func=cmd_import)
    ia = imp_sub.add_parser("abort")
    _add_common(ia)
    ia.add_argument("--batch", required=True)
    ia.set_defaults(func=cmd_import)

    p = sub.add_parser("invite")
    _add_common(p)
    p.add_argument("--account", required=True)
    p.add_argument("--backend", required=True)
    p.add_argument("--limit", type=int, default=None)
    p.set_defaults(func=cmd_invite)

    p = sub.add_parser("pending")
    _add_common(p)
    p.add_argument("--account", required=True)
    p.add_argument("--backend", required=True)
    p.add_argument("--limit", type=int, default=None)
    p.set_defaults(func=cmd_pending)

    p = sub.add_parser("tick")
    _add_common(p)
    p.add_argument("--backend", required=True)
    p.add_argument("--account", default=None, help="worker mode for one account; omit for dispatcher mode")
    p.set_defaults(func=cmd_tick)

    p = sub.add_parser("status")
    _add_common(p)
    p.add_argument("--account")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("schema")
    _add_common(p)
    p.set_defaults(func=cmd_schema)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    # When run directly (`python3 pipeline.py ...`), this module's own
    # identity is `__main__`, so LinkedInBackend as defined here is
    # __main__.LinkedInBackend. load_backend() dynamically imports a
    # SEPARATE backend module that does `from pipeline import
    # LinkedInBackend` -- without this line, that triggers a second, fresh
    # import of this same file under the name `pipeline`, producing a
    # second, distinct LinkedInBackend class object. issubclass() against
    # __main__.LinkedInBackend then fails even for a perfectly correct
    # backend, because the two classes -- despite identical source -- are
    # not the same object. Pre-registering this module under the name
    # `pipeline` makes `from pipeline import LinkedInBackend` resolve to
    # this exact module instead of re-executing the file, so identity
    # matches. This is a standard, if easy-to-miss, gotcha of Python's
    # __main__-vs-imported-module split -- see SKILL.md's "Anti-patterns"
    # section for the failure this avoids.
    sys.modules.setdefault("pipeline", sys.modules[__name__])
    raise SystemExit(main())
