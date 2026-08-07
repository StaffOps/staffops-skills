---
name: linkedin-connection-pipeline
description: "Use when building or extending a vendor-agnostic LinkedIn outreach pipeline — SQLite state machine, retry policies, account rotation, liveness scheduling, and abstract backend adapters. Ships a complete implementation with tests."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [linkedin, outreach, scheduler, sqlite, state-machine, backend-adapter]
    category: development
    related_skills: [python-scripting, python-testing, agent-platform-design]
---

# LinkedIn Connection Pipeline

A SQLite-backed state machine for a connection-request outreach pipeline
(accounts, leads, retry policy, a liveness-locked scheduler) sitting behind
one abstract interface, `LinkedInBackend`, that any automation vendor can
implement. This skill ships the interface, the engine, a test-only fake
implementation, and a real test suite. It does **not** ship a production
backend for any specific vendor, and does not depend on one.

## Vendor-agnostic by design

The design this skill generalizes comes from a real, working project
(`linkedin-growth` in Linked-API/linkedin-skills, MIT-licensed) that hard-codes
one commercial vendor's CLI and JSON error shapes throughout its retry logic
-- the classification code matches on strings like `alreadyPending`,
`limitExceeded`, `noteLimitExceeded`, and `requestNotAllowed`, and the setup
flow tells the user to `npm install -g @linkedapi/linkedin-cli`. That coupling
is exactly the anti-pattern this version fixes, the same way this catalog's
`skill-share` dropped its own source project's hardcoded Slack/Rube coupling
from its `announce` step. Every retry, pacing, and disambiguation decision in
that source project is genuinely well-designed -- see "Where this comes
from" below for what was kept -- but it is inseparable from one vendor's
response format as written.

This skill separates the two. `pipeline.py` defines a normalized outcome
vocabulary (`Outcome`, `ConnectionStatus`) and an abstract `LinkedInBackend`
interface; every piece of retry/backoff/pacing logic switches on that
vocabulary alone and never inspects a vendor-specific error string. No
concrete production backend ships here. To use this for real, write a
`LinkedInBackend` subclass against your own automation vendor (or your own
first-party API client) and point the CLI at it with
`--backend module_or_path:ClassName`. `scripts/testing/fake_backend.py`
ships one concrete implementation, `FakeBackend` -- an in-memory fake for
tests and demos, explicitly not a usable default (see its module docstring).

## When to Use

Reach for this when you are building (or reviewing) an outreach pipeline
that sends connection requests through a rate-limited account, on a
schedule, with retries across multiple accounts and a persistent local
state store -- and you want the retry/pacing/scheduler engineering done
once, correctly, independent of which automation vendor or in-house API
client actually sends the request. Also useful as a reference for two
narrower, reusable patterns even outside this exact domain: a liveness-
locked (PID-probe, never time-based) per-resource scheduler lock, and a
temporal-pattern trick for disambiguating an ambiguous API outcome by
looking at the pattern across recent attempts instead of trusting a single
response.

Do not use this as a drop-in production tool -- it has no default backend
and will refuse to run without `--backend` pointing at your own
implementation. Do not use it as a general CRM or campaign manager; the
schema is deliberately narrow (one connection-request lifecycle per lead,
no notes/sequences/multi-touch campaigns).

## The interface contract

```python
class LinkedInBackend(abc.ABC):
    def send_connection_request(self, account_ref: str, person_ref: str) -> InviteResult: ...
    def check_connection_status(self, account_ref: str, person_ref: str) -> ConnectionStatus: ...
    def withdraw_connection_request(self, account_ref: str, person_ref: str) -> bool: ...
    def search_candidates(self, account_ref: str, query: str, limit: int) -> list[Candidate]: ...
```

`account_ref` is the account's `backend_ref` column -- an opaque string this
pipeline never interprets, only passes through. `person_ref` is likewise
opaque: whatever your backend uses to address a person (a profile ID, a
stable member URL, a hashed reference).

**Why `abc.ABC` and not `typing.Protocol`.** The backend is loaded
dynamically by string (`--backend path/to/module.py:ClassName`), not
imported statically. `abc.ABC` gives an enforced base class: instantiating
a subclass missing an `@abstractmethod` raises `TypeError` immediately, at
load time, naming every missing method. A `Protocol` only checks
structurally at static-analysis time -- a dynamically loaded class that
happens to duck-type close enough would be silently accepted and fail
confusingly deep inside a scheduler tick instead of at the CLI boundary
where a human is looking. Real output from that failure mode:

```
$ python3 pipeline.py invite --account work --backend broken_backend.py:BrokenBackend
error: could not construct backend broken_backend.py:BrokenBackend: Can't instantiate abstract
class BrokenBackend without an implementation for abstract methods 'check_connection_status',
'search_candidates', 'send_connection_request', 'withdraw_connection_request'
```

### The normalized outcome vocabulary

```python
class Outcome(str, enum.Enum):
    SENT = "sent"
    ALREADY_PENDING = "already_pending"
    ALREADY_CONNECTED = "already_connected"
    ACCOUNT_LIMITED = "account_limited"      # not the lead's fault; back off the account
    PERSON_RESTRICTED = "person_restricted"  # ambiguous; see temporal disambiguation below
    TRANSIENT = "transient"                  # infra/session hiccup; retry later
    TERMINAL_ERROR = "terminal_error"        # definite, permanent per-lead failure

class ConnectionStatus(str, enum.Enum):
    CONNECTED = "connected"
    PENDING = "pending"
    NOT_CONNECTED = "not_connected"      # declined, or the request expired
    PERSON_NOT_FOUND = "person_not_found"
    TRANSIENT = "transient"
```

Every concrete backend translates its own vendor's response shapes -- HTTP
status, a JSON error `type` string, a CLI exit code, whatever -- into
exactly one of these values. This is a concrete improvement over the source
design, not just a port of it: the source's restricted-outcome
disambiguation matched `error_message LIKE '%restricted sending a
connection request%'`, a fragile substring match against one vendor's
human-readable text. Here the same disambiguation matches
`outcome == Outcome.PERSON_RESTRICTED`, a value every backend must supply
regardless of what its vendor's message text actually says. A backend
raising an exception (instead of returning an `Outcome`) is treated as
fatal for the current sweep -- see "Backend exceptions are fatal" in
Anti-patterns.

## State machine and schema

```
accounts(name PK, backend_ref, paused, daily_invite_limit, min_invite_interval_minutes,
         active_start, active_end, max_pending_days, pending_batch_size,
         last_action_at, created_at)

leads(person_ref PK, full_name, position, location, list_name,
      owner_account FK accounts.name,
      status [not_connected|pending|connected|exhausted|error],
      sent_at, status_updated_at, error_type, error_message, created_at)

runs(id PK, person_ref FK, account, action [invite|check_status|withdraw],
     outcome, started_at, finished_at, success, error_message)

import_batches(id PK, list_name, searcher_account, query, candidate_count,
               committed_count, skipped_existing_count,
               state [pending|committed|aborted], created_at, committed_at)

import_state(id=1 singleton, last_assigned_account)  -- round-robin cursor

settings(key PK, value)  -- max_connect_attempts ('1'|'N'|'all'), restricted_lead_attempts (int)
```

Run it yourself: `python3 pipeline.py schema --data-dir <dir>` dumps this
table (plus the `Outcome`/`ConnectionStatus` enum values) as JSON, so an
agent can refresh its schema knowledge without reading this file.

A lead's `status` lifecycle: `not_connected` (ready for an invite from
`owner_account`, whether that's attempt 1 or a retry under a reassigned
account) `-> pending` (invite sent, awaiting a response) `-> connected`
(terminal success) or `-> exhausted` (retries used up, no acceptance) or
`-> error` (a definite per-lead failure; reset with `lead reset` to retry).

**Round-robin account assignment.** `import commit` assigns each new lead
to the next account in alphabetical rotation, resuming from
`import_state.last_assigned_account` -- a real, literal round robin (not a
load-heuristic), matching what the `import_state` table's single cursor
column implies. Real output committing 5 candidates across two accounts
with no prior cursor:

```
$ python3 pipeline.py lead list --data-dir demo | jq -r '.[] | "\(.person_ref) -> \(.owner_account)"'
person-1 -> side
person-2 -> work
person-3 -> side
person-4 -> work
person-5 -> side
```

(`side` sorts before `work` alphabetically, so with no persisted cursor the
rotation starts there.) A second `import commit` call resumes from
wherever the cursor was left, verified in `test_pipeline.py`'s
`TestImportCommitRoundRobin` -- it asserts the exact owner sequence across
two separate commit calls, not just that the assignment "looks even".

**Retry policy.** `settings.max_connect_attempts` (default `'1'`, meaning
no retry) caps how many *distinct* accounts may attempt one lead. On a
failed attempt (a stale pending withdrawn, or the person declined/let it
expire), `resolve_failed_attempt()` either reassigns the lead to the
least-loaded active account that has not yet tried it, or marks it
`exhausted` once the cap is reached. `'all'` resolves to the current count
of active (non-paused) accounts.

## Scheduler design

`tick` is one entry point with two roles, selected by `--account`:

- **Dispatcher** (`tick --backend SPEC`, no `--account`): for every active
  account inside its active window and not already locked by a live
  process, spawns a **detached** worker subprocess and returns immediately.
  It never waits on a worker -- a slow or busy account can never hold up
  any other account's tick.
- **Worker** (`tick --account NAME --backend SPEC`): does the work for one
  account, holding that account's lock for its whole lifetime. Invite
  (highest priority, always attempted before pending work) runs first, then
  the due-pending backlog drains.

**The per-account lock is reclaimed only by a PID-liveness probe, never on
a timer.** This is the single most safety-critical piece of logic here --
get it wrong and you either double-start a worker against the same account
(duplicate sends) or leave an account permanently stuck behind a stale
lock file from a crashed process. On POSIX, `is_process_alive()` is
`os.kill(pid, 0)`, catching `ProcessLookupError` (dead) vs `PermissionError`
(alive, owned by another user) -- the same technique the source project
uses in Node. On Windows, `os.kill(pid, 0)` is not a liveness probe (it
maps to `CTRL_C_EVENT`), so a separate `ctypes`-based `OpenProcess` +
`GetExitCodeProcess` path is used there instead; see the code comment on
`is_process_alive()` for why, and "Untested on Windows" in Anti-patterns
for what that means for this skill's test coverage.

This is tested against a **real subprocess**, not an inspection of the
code -- `test_pipeline.py`'s `TestPidLivenessLock` spawns
`scripts/testing/hold_lock.py` as an actual child process, confirms a
second `acquire_lock()` from the test process is refused while it is
alive, sends it `SIGKILL`, and confirms `acquire_lock()` then succeeds:

```
$ python3 -m unittest test_pipeline.TestPidLivenessLock -v
test_lock_refused_while_live_then_reclaimed_after_kill ... ok
test_release_only_removes_own_pid ... ok
```

Real dispatcher output, one account paused and one whose active window
excludes the current time:

```
$ python3 pipeline.py account pause --name work --data-dir demo
{"name": "work", "paused": true}
$ python3 pipeline.py tick --backend demo_backend.py:DemoBackend --data-dir demo
{"now": "2026-08-04T17:16:09.595970+00:00", "local_time": "14:16", "dispatched": []}

$ python3 pipeline.py account resume --name work --data-dir demo
$ python3 pipeline.py account update --name work --active-start 03:00 --active-end 04:00 --data-dir demo
$ python3 pipeline.py tick --backend demo_backend.py:DemoBackend --data-dir demo
{"now": "2026-08-04T17:16:09.805033+00:00", "local_time": "14:16", "dispatched": [],
 "skipped": {"work": "outside_active_window"}}
```

And a worker refusing to start a second time while the lock is held by a
live process (`hold_lock.py` run manually to hold the lock, then `tick
--account work` invoked against the same data directory):

```
$ python3 pipeline.py tick --account work --backend demo_backend.py:DemoBackend --data-dir demo
{"account": "work", "skipped": "already_running"}
```

**Invite pacing keys off the last SUCCESSFUL send only, never the last
attempt.** `last_successful_invite_at()` queries
`WHERE action='invite' AND success=1`. A failed or transient attempt did
not send a request, so it must not consume the pacing interval -- get this
wrong and a cold account (zero successful sends yet) stalls for a full
interval before its first-ever send, for no reason. Verified directly:

```
$ python3 -m unittest test_pipeline.TestInvitePacing -v
test_cold_account_with_only_failed_attempts_does_not_stall ... ok
test_successful_send_does_start_the_pacing_clock ... ok
```

The query is also bounded to the start of the current local day
(`start_of_local_day_utc()`), so at local-midnight rollover the pacing
state resets along with the daily quota -- an account is immediately
eligible again at the start of its window each day, rather than still
serving out an interval computed against a send made late the previous
day. That boundary is local time, not UTC, because `active_start`/
`active_end`/daily quotas are all defined in the account's local calendar
day; SQLite has no notion of the machine's local timezone, so that
computation happens in Python (`start_of_local_day_utc()`,
`local_hhmm()`), not in SQL.

**Daily quota is recomputed from the `runs` table on every tick**, bounded
to the local calendar day -- never a cached counter. This is what lets it
self-correct across restarts and interruptions with no separate reset job;
verified in `TestDailyQuota`.

## Temporal-pattern disambiguation: a real worked example

`Outcome.PERSON_RESTRICTED` is genuinely ambiguous from a single response:
LinkedIn-style platforms return the same signal both when the **account**
has hit its own request-sending limit and when the **person** themselves
restricts incoming requests. Neither the backend nor a single `runs` row
can tell these apart -- only the *pattern* across recent attempts can.
`classify_restricted()` implements that pattern:

- **2+ restricted outcomes for the account since its last successful
  send** (regardless of which lead) -> `'streak'`: the account is limited.
  Not the lead's fault -- back off the whole account for this cycle.
- **An isolated restricted hit** (the account is otherwise sending fine)
  -> counted against that lead specifically; after
  `restricted_lead_attempts` (default 2, a settable value --
  `settings set restricted_lead_attempts N`) isolated hits on the *same*
  lead, close it as `exhausted` so it never hangs forever waiting on
  someone who will never accept.

Real fixture and real output (`test_pipeline.py`'s
`TestRestrictedDisambiguation`, run directly against a temp SQLite DB, not
a mock):

```
$ python3 -m unittest test_pipeline.TestRestrictedDisambiguation -v
test_cold_account_cannot_distinguish_streak_from_repeated_isolated_hit ... ok
test_isolated_hit_defers_then_terminates_at_cap ... ok
test_streak_without_intervening_success_is_account_level ... ok
test_success_between_hits_resets_the_streak ... ok
test_via_full_invite_sweep_end_to_end ... ok
```

Walking `test_via_full_invite_sweep_end_to_end` by hand shows the real
before/after state. Setup: one account, one lead (`person-x`), a
`FakeBackend` scripted to return `PERSON_RESTRICTED` on the next two
invite attempts, after one prior successful send to a different lead
(`person-warmup`) establishes a baseline:

```python
backend.queue_invite_outcome("person-warmup", Outcome.SENT)
backend.queue_invite_outcome("person-x", Outcome.PERSON_RESTRICTED, "restricted")
backend.queue_invite_outcome("person-x", Outcome.PERSON_RESTRICTED, "restricted")
```

First restricted hit on `person-x` -- isolated, since the account's most
recent invite (to `person-warmup`) succeeded:

```python
result_1 = do_invite_sweep(conn, backend, account, limit=1)
# result_1["restricted_deferred"] == 1
# leads.status for person-x is still 'not_connected' -- NOT closed
```

Second restricted hit on `person-x` -- now at the cap (`restricted_lead_attempts=2`):

```python
result_2 = do_invite_sweep(conn, backend, account, limit=1)
# result_2["restricted_closed"] == 1
# leads.status for person-x is now 'exhausted'
# leads.error_type for person-x is 'person_restricted'
```

**A real edge case, not a bug**: with **zero** successful sends ever
recorded for the account, the account-level streak check and the per-lead
check can both be satisfied by the exact same two rows -- if the account's
very first two attempts, against the *same* lead, both come back
restricted, the streak check (which runs first and does not filter by
lead) classifies it as `'streak'`, not `'terminate'`. `classify_restricted`
literally cannot tell "this one lead is unlucky twice" from "this cold
account is limited" without a successful baseline to compare against, and
biases toward the safer assumption (back off the account) rather than
closing a lead it cannot yet prove is the problem:

```python
# acct1 has NEVER successfully sent an invite. Two isolated restricted
# hits on the SAME lead, back to back:
classify_restricted(conn, "acct1", "person-a")  # -> 'streak', not 'terminate'
```

In real operation this usually resolves itself: `fetch_not_connected_leads()`
orders never-tried leads first, then least-recently-attempted, so a lead
that was just attempted rotates to the back of the account's queue. Other
leads -- and typically at least one success among them -- land in between
before the same lead comes up again, which is exactly what establishes the
baseline the disambiguation needs.

**But this is not a structural guarantee, and it is worth being precise
about the difference.** The streak check's lookback is unbounded when there
is no prior success (`COALESCE(last_ok, '0')` spans all of history, not
just "the first two attempts"): for an account that has **never** landed a
single successful send, every subsequent `PERSON_RESTRICTED` hit --
against any lead, in any order -- keeps re-satisfying the streak condition,
because the streak counter only resets on an actual success. Concretely,
if every lead assigned to a never-succeeding account happens to come back
`PERSON_RESTRICTED` (a real automation vendor genuinely refusing every
request, say), `classify_restricted` classifies every single one of them
as `'streak'` forever -- `'terminate'` is unreachable for any lead on that
account until it lands at least one success somewhere. This was confirmed
directly: simulating an account whose every attempt returns
`PERSON_RESTRICTED` across several ticks and several leads never produces
a single `exhausted` lead, only a repeating account-level backoff. That
behavior is not unsafe -- no double-send, no silent data loss, the backoff
is visible in `restricted_backoff` counts -- but it is a standing property
of a chronically-failing account, not a one-time coincidence that later
attempts wash out. If an account is going to sit at zero successes for an
extended period, expect its restricted leads to accumulate in
`not_connected` rather than ever closing as `exhausted`, and treat that
pattern (many restricted hits, zero closures) as a signal to investigate
the account itself rather than assuming the leads will eventually resolve
on their own.

## Idempotency

- `schema`, `account list`, `settings list/get`, `lead list/show`,
  `status`, `tick --account X` when the account is already locked --  all
  safe to call repeatedly; none mutate state on a no-op path.
- `import prepare` creates a new batch every call -- call it once per
  intended import, not per retry.
- `import commit` refuses to run twice on the same batch (its `state` must
  be `'pending'`; a second commit attempt errors with the batch's actual
  state).
- `tick` (dispatcher mode) is safe to run on every scheduler wake-up --
  accounts already locked by a live worker are skipped, not double-started.
- Each backend call result is persisted to the `runs`/`leads` tables the
  moment it completes. If the process is killed mid-sweep, the next tick
  resumes from whatever the DB already recorded -- there is no batch to
  resume and nothing to roll back.

## Anti-patterns

- **Hardcoding a specific automation vendor's CLI, JSON error `type`
  strings, or exit codes anywhere in the retry/pacing/scheduler logic.**
  That is precisely the coupling this skill exists to avoid -- see "Vendor-
  agnostic by design" above. If you find yourself pattern-matching a
  vendor's error message text outside your own `LinkedInBackend`
  implementation, the abstraction has leaked.
- **Presenting `FakeBackend` as a usable default.** It is a deterministic,
  scripted, in-memory fixture for tests and demos only -- see its module
  docstring. Never wire it into a CLI default or a "just get started"
  example; a reader could reasonably mistake it for a working integration.
- **Backend exceptions are fatal, and that's intentional.** A
  `LinkedInBackend` method should never raise for anything representable
  in `Outcome`/`ConnectionStatus` -- return `Outcome.TRANSIENT` or
  `Outcome.TERMINAL_ERROR` instead. An exception means the backend's own
  session or auth is broken, and `do_invite_sweep`/`do_pending_sweep`
  correctly treat that as fatal for the current sweep (abort, don't keep
  burning attempts against a backend that cannot function) rather than
  quietly recording it as a per-lead failure.
- **Reclaiming the scheduler lock on a timeout or file age instead of a
  liveness probe.** A long-but-legitimately-slow worker (the account is
  busy with something else) is not a crashed worker; killing or
  double-starting it on an age heuristic is the exact bug class the
  liveness probe exists to prevent. See "Scheduler design" above.
- **Keying invite pacing off the last *attempt* instead of the last
  *successful* send.** A transient failure did not send a request; if
  pacing counts it anyway, a cold account with a few early failures stalls
  needlessly. See the dedicated test class `TestInvitePacing`.
- **Caching the daily quota instead of recomputing it from `runs` every
  tick.** A cached counter drifts the moment the process restarts mid-day
  or a tick is interrupted; recomputing from the source of truth is what
  makes the quota self-correcting for free.
- **Forgetting the `sys.modules` identity fix when running `pipeline.py`
  directly as a script.** When invoked as `python3 pipeline.py ...`, this
  module's own identity is `__main__`, so `LinkedInBackend` as defined
  there is `__main__.LinkedInBackend`. A dynamically loaded backend module
  doing `from pipeline import LinkedInBackend` would otherwise trigger a
  *second*, fresh import of the same file under the name `pipeline`,
  producing a second, distinct class object that fails `issubclass()`
  against `__main__`'s version even for a perfectly correct backend. This
  was a real bug caught while writing this skill's own worked examples
  (a correct `DemoBackend` was rejected as "not a `LinkedInBackend`
  subclass"), fixed by pre-registering
  `sys.modules.setdefault("pipeline", sys.modules[__name__])` before
  dispatch. If you refactor `pipeline.py`'s entry point, keep this line or
  reintroduce the bug.
- **Untested on Windows.** The POSIX liveness probe
  (`os.kill(pid, 0)`) is exercised by a real subprocess test in this
  skill's own CI environment (macOS/Linux); the Windows `ctypes`-based
  `OpenProcess`/`GetExitCodeProcess` path and the `CREATE_NEW_PROCESS_GROUP`
  detached-spawn path are implemented and code-reviewed but not exercised
  by an automated test in this repository. Treat that path as
  reviewed-not-verified until it runs on real Windows CI.

## Where this comes from

Adapted from `linkedin-growth` in Linked-API/linkedin-skills (MIT-licensed,
Copyright 2025 Linked API), specifically its Node.js scheduler
(`linkedin-growth/scripts/tick.mjs`) and retry engine
(`linkedin-growth/scripts/lib/retry.mjs`,
`linkedin-growth/scripts/network-invite.mjs`).

**Kept, ported faithfully:**
- The dispatcher/worker split and the never-block-the-dispatcher design.
- The PID-liveness lock, reclaimed only when the owning process is
  verifiably dead -- including the exact `os.kill(pid, 0)` /
  `ProcessLookupError` vs `PermissionError` technique the source uses in
  Node's `process.kill(pid, 0)`.
- Round-robin account assignment with a persisted cursor.
- The retry policy shape: `max_connect_attempts` (`'1'`/`N`/`'all'`),
  reassignment to the least-loaded untried account.
- The temporal-pattern trick for disambiguating an ambiguous "restricted"
  outcome by streak-vs-isolated pattern, including the specific insight
  that invite pacing must key off the last *successful* send, not the
  last attempt.
- The daily quota's local-calendar-day boundary and its "recompute from
  the source table every time" design.

**Deliberately dropped:**
- The hard dependency on Linked API's `linkedin-cli` binary and its exact
  JSON error shapes (`alreadyPending`, `limitExceeded`, `noteLimitExceeded`,
  `requestNotAllowed`, etc.) -- see "Vendor-agnostic by design" above.
- Phase A's LLM-judged lead qualification against a user-supplied ICP
  (Ideal Customer Profile). That is a product/orchestration concern (which
  model judges candidates, how the ICP is captured and stored) orthogonal
  to the backend-adapter and state-machine engineering this skill is
  about; `import prepare`/`import commit` here cover the mechanical
  search-candidates-then-assign flow without the qualification step.
- Per-lead `basic_info_json`/`reasoning` storage tied to one vendor's
  profile payload shape and the qualification step's output format.

**Generalized:**
- The source's vendor-specific JSON error `type` strings became the
  `Outcome`/`ConnectionStatus` enums -- every backend must map into this
  vocabulary, and the orchestrator's retry/backoff/disambiguation logic
  reads only the enum, never a vendor's message text (a strictly more
  robust match than the source's `error_message LIKE '%...%'` substring
  search for the exact same disambiguation).
- `hashed_url`/`public_url` (Sales-Navigator-specific and
  regular-search-specific LinkedIn identifiers) became a single opaque
  `person_ref`, meaningful only to the concrete backend that produced it.
- `cli_account` (a `linkedin-cli`-specific account name) became
  `backend_ref`, an opaque string passed through to whichever concrete
  backend is loaded.

## When NOT to Use

- Need a full CRM / multi-touch campaign manager → use HubSpot, Apollo, etc.
- Just sending a few manual connections → no pipeline needed
- Need email sequences / LinkedIn messaging sequences → out of scope (this is connection-request only)
- Already locked into a vendor SDK that handles retries internally → adapt rather than replace

## Related Skills

- `python-scripting` — the patterns used in pipeline.py (argparse, logging, pathlib)
- `python-testing` — the test suite ships pytest fixtures and parametrize patterns
- `agent-platform-design` — for wrapping this as an autonomous scheduled agent
