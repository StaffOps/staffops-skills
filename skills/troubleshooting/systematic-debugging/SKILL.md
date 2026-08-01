---
name: systematic-debugging
description: "Investigate root cause before proposing any fix."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [debugging, root-cause, rca, methodology, incident-response]
    category: troubleshooting
    related_skills: [linux-troubleshooting-methodology, root-cause-analysis, incident-response-runbook, post-mortem-templates, tempo-traceql-patterns, loki-logql-patterns, grafana-cross-signal-correlation, trace-derived-metrics, go-patterns, dotnet-async-patterns]
---
# Systematic Debugging

A four-phase discipline for finding the root cause of a bug, test failure, or
incident before changing any code, plus an auditable trail and a
severity-aware exception that make it survive real production pressure. This
covers the technical investigate-then-fix loop only. It deliberately does not
cover incident roles and comms (`incident-response-runbook`), the RCA
write-up format (`root-cause-analysis`, `post-mortem-templates`), or general
Linux-layer triage (`linux-troubleshooting-methodology`) -- those own what
happens before and after this loop.

## When to Use

Use for any bug, test failure, unexpected behavior, performance regression,
or build/integration failure -- before proposing a fix, not after one is
already half-written. Use it *especially* when:

- Time pressure makes a guess feel faster than an investigation
- A fix "obviously" looks correct on sight
- You have already tried two fixes that did not stick
- A senior engineer or the ticket reporter is confident about the cause
- You do not yet fully understand the failure

None of these are reasons to skip a phase. They are the exact conditions
this process exists to survive -- see
[Signals You're Doing It Wrong](#signals-youre-doing-it-wrong) below.

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If Phase 1 is not complete, you cannot propose a fix. There is exactly one
narrow exception, and it is not "propose a fix anyway" -- see below.

## The One Exception: Mitigation During an Active Incident

A live SEV1/SEV2 changes *when* you are allowed to act, not *whether* you
must eventually find the root cause. Narrowed from `incident-response-runbook`'s
Phase 3 (Mitigate) options to only its Low/Medium-risk, fast actions, a
symptom-level mitigation is allowed before Phase 1 completes -- but only
from this pre-approved, reversible, blast-radius-bounded set:

| Allowed as a stopgap | Not allowed as a substitute for Phase 1 |
| --- | --- |
| Rollback via Argo Rollouts / ArgoCD to the last known-good revision | A code patch guessed under pressure and shipped as "the fix" |
| Feature flag off | A config change nobody can explain the mechanism of |
| Scale up | Any change you cannot revert within the incident's time budget |
| Restart pods | `incident-response-runbook`'s High-risk options (hotfix deploy, failover to DR) -- those need IC sign-off, not this exception |
| Redirect traffic (single cluster/AZ issue) | |

What keeps this an exception instead of a loophole:

1. **Track the mitigation separately from the fix.** Log it in the incident
   timeline as a stopgap ("rolled back to v1.2.2, error rate recovered") --
   never write it up as "root cause: fixed". `post-mortem-templates` has a
   dedicated Timeline field for exactly this.
2. **Phase 1 resumes immediately, same shift.** The service recovering
   removes the time pressure, not the obligation to investigate -- restart
   before the next incident, not "next sprint".
3. **The exception is scoped to SEV1/SEV2 with active customer impact.**
   For SEV3/SEV4, or once the service is stable, there is no exception: the
   Iron Law applies in full before any change lands.
4. **A rollback is not a hypothesis test.** It buys time; it does not
   explain *why* the prior version broke. Phase 1 still owes that answer,
   or the same regression ships again next release.

## The Four Phases

Each phase gates the next. You cannot skip ahead.

### Phase 1: Root Cause Investigation

1. **Read the error completely.** Stack trace, exit code, every line -- the
   fix is often stated in the message you skimmed past.
2. **Reproduce it on demand.** If you cannot trigger it reliably, you do not
   yet have enough data to hypothesize -- gather more, do not guess.
3. **Check what changed.** `git diff` against the last known-good state,
   ArgoCD sync history, a recent Helm release, a dependency bump, an env
   var edited in Helm values.
4. **Correlate signals before writing a single ad hoc print or echo
   statement.** Assume the evidence you need is already emitted and already
   correlated in the observability stack -- a fresh `console.log` /
   `fmt.Println` is usually a step backward from what already exists:

   | Question | Tool |
   | --- | --- |
   | Where in the request did it fail? | `tempo-traceql-patterns` -- TraceQL search by `service.name`, `status = error`, `duration > Nms` to find the failing span |
   | What did that component log at that moment? | `grafana-cross-signal-correlation`'s `tracesToLogsV2` datasource config, or `loki-logql-patterns` filtered directly by `trace_id` (the reverse direction, log-to-trace via derived fields, is not wired up in this org yet -- do not assume it works) |
   | Did a metric move in the same window? | `trace-derived-metrics` (service graph RED per edge, catches cascading failures) plus the runtime's APM metrics skill (`dotnet-apm-metrics`, `go-apm-metrics`, `python-apm-metrics`) |
   | Is this one request or a pattern? | `loki-logql-patterns` aggregation (`count_over_time`, `rate`) across the incident window |

   Walk trace -> log -> metric, in that order: the trace shows *which*
   span/service/edge failed, the correlated logs show *what* it was doing,
   the metric shows whether the failure is isolated or systemic. Add manual
   instrumentation only at a component boundary you genuinely cannot
   observe this way, and treat it as temporary -- remove it once Phase 4
   confirms the fix, or promote it to permanent debug instrumentation under
   Defense-in-Depth Layer 4 below.

5. **Trace data flow backward when the error surfaces deep in the call
   stack.** Do not fix where the error appears -- find where the bad value
   originated:

   ```
   Symptom: nil pointer dereference in OrderProcessor.Charge()
     <- what called Charge() with a nil Customer?
       <- OrderService.Process(order) -- order.Customer was never set
         <- where was `order` constructed?
           <- Repository.Load() returns a zero-value Order on a cache
              miss, instead of an error -- THIS is the source
   ```

   Fix at the source -- make the cache-miss path return an error -- not at
   the symptom (add a nil check in `Charge()` and call it done). The nil
   check may still belong there too, as one layer of Defense-in-Depth (see
   Phase 4).

### Phase 2: Pattern Analysis

1. Find a working example of the same pattern elsewhere in the codebase.
2. If implementing against a reference (a library's documented pattern,
   another service's proto contract), read it completely -- skimming and
   adapting "the gist" guarantees a mismatch.
3. List every difference between the working and the broken case, however
   small -- do not discard one because "that can't matter".
4. Confirm the dependencies and assumptions the pattern requires: config,
   environment, ordering, what else must already be initialized.

### Phase 3: Hypothesis and Testing

Scientific method, made auditable instead of self-reported:

1. **Write the hypothesis down before testing it, in a running log** --
   not in your head. Copy `references/hypothesis-log-template.md` into your
   scratch space (or the ticket) and append one entry per hypothesis:

   ```markdown
   ## Hypothesis 2 -- 2026-07-31 14:20
   **Statement**: I think the retry wrapper is swallowing the 5xx and
   returning the cached value, because the trace shows the retry span as a
   child of the failed call, and the response body in the log matches the
   stale cache entry.
   **Test**: disable the retry wrapper for this one route, rerun the
   failing request.
   **Outcome**: REFUTED -- same stale value returned with retry disabled.
   ```

2. **Test the smallest possible change** -- one variable, not a bundle of
   fixes.
3. **Read the log before writing the next hypothesis; do not estimate the
   count from memory:**

   ```bash
   grep -c '^\*\*Outcome\*\*: REFUTED' hypothesis-log.md
   ```

   Two `REFUTED` entries is a signal to slow down and re-read Phase 1/2.
   **Three `REFUTED` entries means STOP -- do not write hypothesis 4.**
   Move to Phase 4, step 5 (question the architecture) instead. The log
   exists specifically so this is not a number that gets rounded down under
   pressure.
4. If you do not understand something, write "I don't understand X" in the
   log and go find out -- do not paper over it with a hypothesis you do not
   actually believe.

### Phase 4: Implementation

1. **Write a failing test first** -- the smallest reproduction, automated
   if the codebase has a framework for it, a one-off script if not. No fix
   lands without one.
2. **Implement exactly one fix**, at the root cause identified in Phase 1
   -- no bundled refactor, no "while I'm here".
3. **Verify**: does the new test pass, do the existing tests still pass,
   is the original symptom actually gone (not merely quieter)?
4. **If the fix does not work: stop, log the outcome, check the count**
   (Phase 3, step 3). Under 3 `REFUTED` fixes -- form a new hypothesis, back
   to Phase 1 with what you just learned. At 3, do not attempt a 4th fix.
5. **3+ failed fixes means the architecture is the problem, not the
   hypothesis.** Signs this is happening: each fix uncovers new shared
   state or coupling somewhere else, every fix is described as needing "a
   bigger refactor" to actually work, or each fix creates a new symptom in
   a different place. This is not "try one more angle" -- stop and raise it
   explicitly with whoever owns the design (tech lead, ticket reporter,
   reviewing engineer) before touching the code again.

#### Defense-in-Depth: Make the Bug Structurally Impossible

Once the root cause is fixed, a single validation point can still be
bypassed by a different code path, a mock, or the next refactor. Validate
at every layer the bad data passes through:

| Layer | Purpose |
| --- | --- |
| 1. Entry validation | Reject invalid input at the API/handler boundary |
| 2. Business logic validation | Confirm the value makes sense for *this* operation, not just any operation |
| 3. Environment guards | Block dangerous operations in specific contexts (e.g., never run a destructive op outside a scratch path in tests) |
| 4. Debug instrumentation | Log context -- never secrets -- at the point of failure, for when layers 1-3 miss it |

Go (layers 1 and 3):

```go
// Layer 1 -- entry validation
func NewOrderProcessor(customer *Customer) (*OrderProcessor, error) {
    if customer == nil {
        return nil, fmt.Errorf("order processor: customer is required")
    }
    return &OrderProcessor{customer: customer}, nil
}

// Layer 3 -- environment guard: a cache miss must be an error, not a
// zero-value that looks like a valid, empty order.
func (r *Repository) Load(ctx context.Context, id string) (*Order, error) {
    order, ok := r.cache.Get(id)
    if !ok {
        return nil, fmt.Errorf("order %s: cache miss, refusing zero-value result", id)
    }
    return order, nil
}
```

Python (layers 1 and 3):

```python
# Layer 1 -- entry validation
def charge(customer: Customer | None) -> Receipt:
    if customer is None:
        raise ValueError("charge() requires a customer, got None")
    ...

# Layer 3 -- environment guard
def git_init(directory: Path) -> None:
    if os.environ.get("APP_ENV") == "test":
        scratch = Path(tempfile.gettempdir()).resolve()
        resolved = directory.resolve()
        if resolved != scratch and scratch not in resolved.parents:
            raise RuntimeError(
                f"refusing git init outside scratch dir during tests: {directory}"
            )
    subprocess.run(["git", "init"], cwd=directory, check=True)
```

.NET (layers 1 and 4):

```csharp
// Layer 1 -- entry validation
public OrderProcessor(Customer customer)
{
    ArgumentNullException.ThrowIfNull(customer);
    _customer = customer;
}

// Layer 4 -- debug instrumentation via ILogger, never Console.WriteLine,
// so it flows through the same OTel pipeline as everything else.
public async Task ChargeAsync(Order order, CancellationToken ct)
{
    _logger.LogDebug(
        "Charging order {OrderId} for customer {CustomerId}",
        order.Id, order.Customer?.Id);
    await _gateway.ChargeAsync(order, ct);
}
```

All four layers matter because different bugs bypass different layers -- a
different code path skips entry validation, a mock skips business logic, a
new deployment target needs its own environment guard. One validation point
means "we fixed the bug"; four means "we made the bug impossible".

#### Condition-Based Waiting: Stop Guessing at Timing

A specific, very common Phase 4 mistake: "fixing" a flaky test or race by
inserting a longer sleep. That is a symptom fix wearing a fix costume -- the
underlying race is still there, just less likely to lose. Wait for the
condition you actually care about instead:

Go:

```go
func waitFor(t *testing.T, timeout time.Duration, cond func() bool) {
    t.Helper()
    deadline := time.Now().Add(timeout)
    for {
        if cond() {
            return
        }
        if time.Now().After(deadline) {
            t.Fatalf("condition not met within %s", timeout)
        }
        time.Sleep(10 * time.Millisecond)
    }
}

// waitFor(t, 5*time.Second, func() bool { return len(results) >= 2 })
```

Python:

```python
def wait_for(condition, timeout=5.0, interval=0.01, description="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if (value := condition()):
            return value
        time.sleep(interval)
    raise TimeoutError(f"timed out waiting for {description} after {timeout}s")

# wait_for(lambda: len(results) >= 2, description="2 results")
```

.NET:

```csharp
public static async Task<T> WaitForAsync<T>(
    Func<T?> condition, TimeSpan timeout, CancellationToken ct = default)
{
    var deadline = DateTime.UtcNow + timeout;
    while (DateTime.UtcNow < deadline)
    {
        if (condition() is { } value) return value;
        await Task.Delay(10, ct);
    }
    throw new TimeoutException($"condition not met within {timeout}");
}
```

Full runnable versions with domain-specific helpers (waiting on an event
stream, a channel's item count, a gRPC health status) are in `examples/`.

An arbitrary sleep is legitimate only when deliberately testing timed
behavior itself -- a debounce interval, a retry backoff -- and only after
first waiting for the triggering condition, with a comment stating the
exact interval and why.

## Red Flags -- Stop and Return to Phase 1

If you catch yourself thinking any of these, stop:

- "Quick fix now, investigate properly later"
- "Let me just try changing X and see"
- "I'll change a few things and rerun"
- "I'll skip the failing test, I can verify by hand"
- "It's probably X" (without having traced to X)
- "I don't fully understand this but it might work"
- "The reference does it differently but I'll adapt the idea"
- "Here's my list of fixes" (with no investigation preceding it)
- "One more attempt" (already tried 2+)
- Each fix keeps revealing a new problem in a different place

All of these mean: stop, return to Phase 1 (or, past two fixes, to Phase 4
step 5).

## Signals You're Doing It Wrong

Watch for these from whoever you are working with -- they are usually right
before you are:

| Signal | What it means |
| --- | --- |
| "Is that actually happening, or are you assuming?" | You proposed a cause without verifying it |
| "What would that show us?" | You should have gathered evidence, not opinions |
| "Stop guessing" | You are proposing fixes without understanding |
| "Think about this from first principles" | Question the architecture, not just the latest symptom |
| "Are we stuck?" (said with frustration) | The current approach is not converging -- change it, do not push harder on it |

## Common Rationalizations

| Excuse | Reality |
| --- | --- |
| "This one's simple, skip the process" | Simple bugs have root causes too; the process is fast for simple bugs precisely because there is little to trace |
| "It's an emergency, no time to investigate" | Guess-and-check under pressure is slower than one focused pass through Phase 1 -- see the mitigation exception above for what to do instead |
| "Try this first, investigate if it doesn't work" | The first attempt sets the pattern for the rest of the session -- start it right |
| "I'll add the test after confirming the fix works" | A fix without a preceding failing test is unverified by construction |
| "A few fixes at once saves a round trip" | You lose the ability to tell which change mattered, and often introduce a second bug |
| "The reference is long, I'll adapt the shape of it" | Partial understanding of a pattern reproduces its bugs, not its guarantees |
| "I see what's wrong, let me just fix it" | Recognizing a symptom is not the same as knowing why it happens |
| "One more fix attempt" (after 2 failures) | 3 failed fixes is the architecture talking, not a hypothesis waiting to be found |

## Feeding the Investigation Forward

Phase 1-3 already produce the structured evidence that `root-cause-analysis`
and `post-mortem-templates` need. Port it in directly rather than
reconstructing it from memory afterward:

| What Phase 1-3 produced | Where it goes |
| --- | --- |
| Hypothesis log, confirmed entry | `post-mortem-templates` -> Root Cause Analysis (5 Whys / category) |
| Timestamps from trace/log/metric correlation | `root-cause-analysis` -> Timeline Construction; `post-mortem-templates` -> Timeline |
| Trace + log + metric agreeing (or disagreeing) | `root-cause-analysis` -> Cross-Signal Correlation validation ("3 signals agree") |
| Mitigation actions taken under the SEV1/SEV2 exception | `incident-response-runbook` Phase 3 log; `post-mortem-templates` -> What Went Well/Wrong |
| Refuted hypotheses | Contributing Factors / What Went Wrong -- they document what was ruled out, and why, which is real information |

A post-mortem written from a hypothesis log is a transcription. A
post-mortem written from memory after the incident is a reconstruction --
and reconstructions lose exactly the signal disagreements that mattered
most during triage.

## Quick Reference

| Phase | Key activity | Exit criteria |
| --- | --- | --- |
| 1. Root Cause | Read errors, reproduce, check changes, correlate trace/log/metric | You can state WHAT is happening and WHY |
| 2. Pattern | Find a working example, list every difference | Differences are enumerated, not assumed irrelevant |
| 3. Hypothesis | Log a specific, falsifiable statement; test the smallest change | Hypothesis confirmed, or logged as REFUTED |
| 4. Implementation | Failing test first, one fix, verify, defense-in-depth | Bug gone, tests green, bug made structurally hard to reintroduce |

## Anti-patterns

- Adding print/echo/console-log instrumentation before checking whether the
  trace, log, and metric already answer the question (`tempo-traceql-patterns`,
  `loki-logql-patterns`, `grafana-cross-signal-correlation`)
- Treating a rollback, feature flag flip, or restart as "the fix" instead
  of a logged stopgap -- see the incident exception above
- Applying the SEV1/SEV2 mitigation exception outside an active incident, or
  after service has already stabilized
- Skipping the hypothesis log and self-reporting "I've only tried two
  things" from memory
- A fourth fix attempt after three `REFUTED` log entries, instead of
  raising the architecture question
- Fixing at the point the error surfaced instead of tracing back to where
  the bad value originated
- One validation layer and calling the bug "impossible" -- different code
  paths, mocks, and platforms bypass different layers
- Widening a sleep instead of waiting for the actual condition
- Bundling a fix with an unrelated refactor, so a regression cannot be
  bisected to either one
- Reconstructing a post-mortem timeline from memory instead of porting it
  from the hypothesis log and the trace/log/metric timestamps gathered
  during Phase 1

## Reference

- `root-cause-analysis` -- RCA techniques (5 Whys, fault tree, cross-signal
  correlation) that this skill's evidence feeds into
- `post-mortem-templates` -- where Phase 1-3 output lands for SEV1-2
  writeups
- `incident-response-runbook` -- incident roles, comms, and the Mitigate
  phase referenced by the SEV1/SEV2 exception
- `linux-troubleshooting-methodology` -- the general hypothesis-before-action
  framework this skill specializes for code-level fixes
- `tempo-traceql-patterns`, `loki-logql-patterns`,
  `grafana-cross-signal-correlation`, `trace-derived-metrics` -- the
  cross-signal tools Phase 1 uses before ad hoc instrumentation
- `go-patterns`, `dotnet-async-patterns` -- language idioms behind the
  defense-in-depth and condition-based-waiting examples (no equivalent
  general Python-idiom skill exists in this catalog yet -- the Python
  example below follows stdlib/asyncio convention directly instead)
- `references/hypothesis-log-template.md` -- copy into a scratch file per
  investigation
- `scripts/find-polluter.sh` -- bisect which test creates an unwanted
  artifact, runner-agnostic
- `examples/` -- full condition-based-waiting implementations in Go,
  Python, and C#
