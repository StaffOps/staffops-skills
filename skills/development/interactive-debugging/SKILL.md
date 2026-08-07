---
name: interactive-debugging
description: "Use when you need live process state (locals, call stack, breakpoints) that logs/traces can't answer — via DAP CLI. Covers Python debugpy, Go dlv, .NET, Node, Kubernetes remote debug, and the dap command cheat sheet."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [debugging, dap, breakpoints, go, python, dotnet, kubernetes]
    category: development
    related_skills: [systematic-debugging, go-patterns, dotnet-async-patterns, python-fastapi-patterns, eks-management]
---
# Interactive Debugging

How to set breakpoints, step through execution, inspect live variable state,
and evaluate expressions against a running process from the shell, using
`dap` -- a third-party open-source CLI (`AlmogBaku/debug-skill` on GitHub,
MIT licensed) that wraps the Debug Adapter Protocol (DAP). This catalog does
not ship, fork, or maintain `dap` -- treat it like `kubectl` or `yt-dlp`: an
external binary you install and invoke, with its own release cadence outside
this org's control. This skill also does not replace
[systematic-debugging](../../troubleshooting/systematic-debugging/SKILL.md)'s
four-phase root-cause discipline; it is the tool you reach for inside that
discipline's Phase 1 ("reproduce it") and Phase 3 (hypothesis testing) when
trace/log/metric correlation cannot answer "what is the actual value here
right now" and you need live process state instead.

## When to Use

- A program crashes, exits with the wrong code, or produces wrong output and
  reading the source isn't enough to confirm *why*.
- You need live locals or the exact call stack at the moment something goes
  wrong, not an inference from logs.
- You want to test a hypothesis against a running process (`dap eval`)
  without adding a log line and redeploying to see it.
- You've already walked trace -> log -> metric per `systematic-debugging`
  Phase 1 and the signal still doesn't answer the question -- this is the
  next tool, not the first one.

**Do not use this against a pod serving live production traffic** outside an
isolated ephemeral container (see Kubernetes section below). A blocking
breakpoint stalls every in-flight request on that process for as long as
it's paused. Restrict live interactive sessions to DEV/HML, a local
reproduction, or a PRD ephemeral container taken deliberately out of the
traffic path.

## What `dap` Is (and Is Not)

`dap <command>` is a stateless CLI. The first `dap debug` call for a given
`--session` name spawns (or reuses) a background daemon listening on a
per-session Unix socket at `~/.dap-cli/<session>.sock`; the daemon holds the
live DAP connection to a real debug adapter (`debugpy`, `dlv dap`,
`js-debug`, or `lldb-dap`, auto-selected from the file extension or forced
with `--backend`) and exits on its own after an idle timeout (10 minutes by
default -- see Session Hygiene below). Everything after the first call is
just another short-lived `dap <command>` process talking to that daemon over
the socket.

The one design decision worth internalizing: **every blocking execution
command (`dap debug`, `dap continue`, `dap step`) returns full context the
instant execution stops** -- current `file:line`, a few lines of source
around it, the locals for the target frame, the call stack, and any buffered
stdout/stderr collected since the last stop. You do not issue a follow-up
"where am I" or "what are the variables" call; it's already in the response.
That single property is what makes this worth using over a hand-rolled
`pdb`/`gdb` batch script, where every one of those questions is a separate
round trip.

### What to expect truncated

| What | Cap | Behavior when exceeded |
| --- | --- | --- |
| String variable values | ~200 characters | Truncated with a trailing `...` |
| Stack frames | 20 | Deeper frames omitted from the auto-context; still reachable via lower-level DAP calls if the backend supports it |
| Source context around the stop line | +/-2 lines | Override with the context-lines flag on the relevant command (`dap --help`) |
| Buffered stdout/stderr | 200 lines | Oldest lines dropped first (ring buffer) |
| `dap inspect --depth N` node expansion | ~100 nodes total across the whole tree | Expansion stops even if `--depth` hasn't been reached |

These numbers are grounded in the `dap` source reviewed while writing this
skill; they document behavior you should *expect*, not a contract this org
guarantees, since `dap` is an external project that can change them in a
future release. If a truncated string or a capped stack frame hides the
answer, don't trust the cap dropped nothing -- run a narrower `dap eval`
(`obj.field[:50]`, `--frame 5`) instead of assuming the visible slice is the
whole picture.

## Installing `dap`

Check first: `command -v dap`. If missing, ask the user before installing --
this puts a new binary on the box.

```bash
# macOS, via the maintainer's Homebrew tap
brew install AlmogBaku/tap/dap

# Any platform with a Go toolchain available
go install github.com/AlmogBaku/debug-skill/cmd/dap@latest

# Prebuilt binaries (no local Go toolchain required)
# https://github.com/AlmogBaku/debug-skill/releases/latest
```

Per `dev-environment` steering, this org doesn't assume a local Go SDK on
the host -- prefer the Homebrew tap or a prebuilt release binary over
`go install` unless you're already inside a container/devbox that has Go.

`dap` itself is an independent open-source project (MIT license, Almog
Baku), not affiliated with or maintained by this organization. Pin a
released version if a reproducible debugging environment matters (CI,
onboarding docs); nothing here guarantees future `dap` releases keep the
same flags, defaults, or truncation numbers documented above.

## Starting a Session

`dap debug <file>` auto-detects the backend from the extension. Pick a
starting strategy based on what you already know:

```bash
# Have a hypothesis: break where you expect the bug
dap debug script.py --break script.py:42

# Conditional breakpoint (always quote specs with a condition)
dap debug script.py --break "script.py:42:x > 5"

# Exception, location unknown
dap debug script.py --break-on-exception raised   # Python
dap debug main.go --break-on-exception all         # Go

# Already-running process, same host
dap debug --pid <PID> --backend <name>

# Remote / containerized debug adapter already listening
dap debug --attach host:port --backend <name>
```

**Session isolation:** always pass `--session <name>` for anything beyond a
one-off local check. Each session gets its own socket and daemon; two
agents (or two investigations) sharing the default session will stomp on
each other's breakpoints and state. Using the current session/conversation
id as the session name is a reasonable default when one is available.

## Per-Language Decision Trees

These are the runtimes actually in use in this org's stack. `dap` also
supports Node.js/TypeScript and Rust/C/C++ generically -- see
`references/backend-install.md` for those and for the full install/check
commands behind every backend named below.

### Go services

Backend: Delve (`dlv dap`). Check with `dlv version`.

- **Panic already printed, origin unclear** -- `dap debug ./cmd/server
  --break-on-exception all`, rerun the trigger. If the panic unwound through
  a `defer`/`recover`, frame 0 is the recover site, not the origin -- walk
  `dap eval <expr> --frame 1`, `--frame 2`, ... until the values stop making
  sense; that boundary is where the bad state actually originated (same
  principle as `systematic-debugging`'s "trace data flow backward").
- **Goroutine leak or suspected deadlock** -- `dap pause` while it's hung,
  then `dap threads` to enumerate goroutines and `dap thread <id>` on each
  one blocked at the same call site. Two or more goroutines each waiting on
  a resource the other holds confirms a deadlock; one goroutine parked on a
  channel or lock nobody will ever release is a leak, not a deadlock.
- **Binary runs inside a container** -- do not try `--pid` across a
  container boundary from the host; it won't see the process. Either start
  the binary under `dlv --headless --listen=:2345` as the container's
  entrypoint and `--attach` after a `kubectl port-forward` (see below), or
  use `kubectl debug` to get a debugger into the pod's process namespace
  without changing the shipped image.
- **macOS + `--pid` on the bare host** -- requires SIP disabled (`csrutil
  disable`). Almost never worth the trade-off; prefer attaching to a
  container/remote process instead of debugging directly on a
  developer machine with reduced OS protections.

### Python services (FastAPI / uvicorn)

Backend: `debugpy`. Check with `python3 -m debugpy --version`.

- **Virtualenv** -- `dap` resolves the interpreter from `$VIRTUAL_ENV`.
  Activate the venv before `dap debug`, or pass `--python
  /path/to/venv/bin/python` explicitly. Skip both and it silently falls back
  to whatever `python3` is on `PATH`, which may not have `debugpy` installed
  or may be a different interpreter version than the one the service
  actually runs under.
- **The `--reload` reloader is a real trap.** `uvicorn app:app --reload`
  forks a supervisor process that itself execs the actual worker process.
  The supervisor is the PID you'll find first with `ps`, but breakpoints
  only ever fire in the worker -- attaching to the supervisor looks like
  `dap` silently "not working". Either drop `--reload` and run uvicorn
  directly under the debugger (`dap debug -m uvicorn -- app:app`), or find
  the worker's PID (child of the reloader) and `dap debug --pid
  <worker-pid> --backend debugpy`.
- **Stepping across `await`** -- stepping over an `await` can land you on
  whatever coroutine the event loop scheduled next, not back inside your
  handler; the call stack right after such a step can look unrelated to
  where you were. Prefer `dap continue --break <file>:<line>` at the next
  line you actually care about over single-stepping through async code.

### .NET services -- documented extension point, not shipped today

Be precise about what is and isn't verified: `dap`'s backend list
(`debugpy`, `dlv`, `js-debug`, `lldb-dap`) has **no .NET adapter** in the
version reviewed for this skill. There is no working `dap debug
service.dll` today -- do not tell a user otherwise.

What *would* plug into the same architecture, if this org or the upstream
project ever adds the backend:

- **`netcoredbg`** (Samsung, open source, speaks DAP natively over
  stdio/socket -- the same transport `dap` already drives for `debugpy` and
  `dlv dap`).
- **`vsdbg`** (Microsoft, DAP-native, ships with the VS/VS Code C#
  extensions; redistribution is restricted to Microsoft's own tooling, which
  makes it a worse fit for a standalone CLI than `netcoredbg`).

`dap`'s own `Backend` interface (`Spawn`, `LaunchArgs`, `RemoteAttachArgs`,
`PIDAttachArgs`) is exactly the seam a `netcoredbg` backend would implement
-- the daemon and Unix-socket protocol layer this skill describes above
don't change per backend, only the adapter being spawned does.

Until that backend exists, debug .NET services one of these ways instead:

1. Attach an IDE's own remote debugger (Rider or VS Remote Debugger over
   SSH or into a container) -- entirely outside `dap`.
2. Lean on `dotnet-otel-patterns`' `DebugTraceStateProcessor` and
   structured `ILogger` output rather than a live debugger for anything
   that observability can already answer.
3. If you build or vendor a `netcoredbg`-backed `dap` fork yourself, the
   `--attach host:port` flow and the Kubernetes workflow below apply
   unchanged -- only the backend name differs.

## Kubernetes Remote Debugging

This org's workloads are container-native (see `eks-management`); the
generic "attach to `host:port`" flag needs a concrete path to get that port
reachable from your shell. Full walkthrough, including the PRD-safe
ephemeral-container pattern, is in
`references/kubernetes-remote-debugging.md`. The short version for a DEV/HML
pod that already listens for a debugger on request:

```bash
kubectl config current-context
kubectl get pods -n <namespace> -l app=<service>
kubectl port-forward pod/<pod-name> -n <namespace> <local-port>:<remote-port>

# In another shell:
dap debug --attach localhost:<local-port> --backend <name> --session <pod-name>
```

`kubectl port-forward` is read-only under this org's `k8s-safety` rules and
needs no approval; the step that usually does need approval is whatever put
a debug listener into the pod in the first place (a rebuilt image, or
`kubectl debug` adding an ephemeral container) -- see the reference for the
distinction and for why a hardened golden image typically has no debugger
baked in.

## Session Hygiene: Reap Orphans Before Starting

The daemon's 10-minute idle timeout (`DAP_IDLE_TIMEOUT` env var to override)
is a ceiling, not a guarantee your next session starts clean. A killed
terminal, a killed IDE, or a reused `--session` name from an earlier run can
leave a live daemon holding stale breakpoints on the socket you're about to
reuse. Check before starting a new investigation:

```bash
for pidfile in ~/.dap-cli/*.sock.pid; do
  [ -f "$pidfile" ] || continue
  sock="${pidfile%.pid}"
  pid=$(cat "$pidfile" 2>/dev/null || true)
  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    echo "stale: $sock (pid $pid not running) -- removing"
    rm -f "$sock" "$pidfile"
  else
    echo "live:  $sock (pid $pid) -- pick a different --session name, or"
    echo "       run: dap stop --session \"\$(basename \"$sock\" .sock)\""
    echo "       if this is actually yours and abandoned"
  fi
done
```

If you're about to reuse a session name that's still live, `dap stop
--session <name>` first rather than debugging on top of someone else's (or
your own earlier) stale breakpoints and half-finished state. For CI or
other ephemeral runs where waiting out a 10-minute default is wasteful, set
`DAP_IDLE_TIMEOUT=60s` in the environment before the first `dap debug`.

## The Debugging Mindset

- **Two strikes, rethink.** If two breakpoints at the same location both
  come back with state that doesn't explain the bug, don't set a third one
  nearby -- your model of what's happening is wrong. Re-read the calling
  code and form a hypothesis at a genuinely different location, the same
  way `systematic-debugging` treats a second `REFUTED` hypothesis as a
  signal to slow down.
- **Escalate gradually.** Test a one-line hypothesis with `dap eval` before
  committing to a breakpoint-and-step session. Use conditional breakpoints
  to filter noise before falling back to unconditional breakpoints plus
  manual stepping.
- **Trace causation upward, not just at the symptom.** A value wrong at
  frame 0 was passed in wrong by the caller, or the caller's caller. Walk
  `dap eval <expr> --frame 1`, `--frame 2`, ... until you find the frame
  where it was still correct -- that boundary, not where the error
  surfaced, is the fix location.
- **Break at boundaries and state transitions**, not inside library code
  and not unconditionally inside a tight loop. A breakpoint on every
  iteration of a hot loop just re-creates print-statement noise with extra
  steps.
- **Conditional breakpoints as runtime assertions.** `"file:line:condition"`
  stops the moment an invariant breaks (`balance < 0`, `len(items) == 0`,
  `type(val) != int`) -- catching the cause, not the downstream symptom two
  function calls later.
- **Wolf-fence bisection for loops.** A loop goes wrong at an unknown
  iteration: set a conditional breakpoint at the midpoint index, check
  whether the result is already wrong there, move the condition to the
  midpoint of whichever half is bad, repeat. About 10 checks covers 1,000
  iterations -- not 1,000 step commands. Full walkthrough in
  `references/advanced-techniques.md`.
- **Three steps in a row without new information means you needed a
  breakpoint further ahead**, not a fourth step.

## When NOT to use

- Debugging from logs/traces/metrics (no live process needed) — use `container-runtime-debugging`
- Investigating distributed trace gaps — use `grpc-distributed-tracing` or `tempo-trace-investigation`
- Profiling CPU/memory without breakpoints — use `pyroscope-profiling-patterns`

## Related skills

- `container-runtime-debugging` — when `docker exec` or `kubectl debug` is enough
- `python-otel-patterns` — when traces reveal the issue without live debugging
- `dotnet-otel-patterns` — .NET diagnostic tools (dumps, counters) before attaching debugger
- `go-patterns` — Go `dlv` patterns referenced in this skill

## Anti-patterns

- Attaching (`--pid`, `--attach`) to a pod serving live production traffic
  outside an isolated ephemeral container -- a paused breakpoint stalls
  every in-flight request on that process.
- Reaching for `dap` before trace/log/metric correlation
  (`systematic-debugging` Phase 1) has been ruled out -- a live session that
  duplicates what Tempo/Loki/VictoriaMetrics already show is wasted setup.
- Assuming the daemon's 10-minute idle timeout means your next `dap debug`
  starts on a clean socket -- check for orphans first (Session Hygiene).
- Debugging a `uvicorn --reload` supervisor PID instead of its worker child
  and concluding breakpoints "don't work" in that service.
- Single-stepping through a Python `await` and expecting to land back in
  the same coroutine.
- `dlv --pid` on a bare macOS host as a first move -- it requires SIP
  disabled; attach to a container or remote process instead.
- Trusting a truncated 200-character string or a 20-frame stack as the
  complete value instead of narrowing the `dap eval` expression.
- Telling a user `dap debug service.dll` works today -- no .NET backend is
  shipped; it's a documented extension point, not a working feature.
- Vendoring or forking `dap`'s source into this repository instead of
  installing a released binary -- it's a third-party project with its own
  release cadence and this org doesn't maintain a copy of it.

## Reference

- `systematic-debugging` -- the four-phase root-cause discipline this
  skill's live-state inspection feeds into; start there, land here for
  Phase 1/3 when static signals run out.
- `go-patterns`, `dotnet-async-patterns`, `python-fastapi-patterns` --
  language idioms behind the per-runtime decision trees above.
- `eks-management` -- cluster and pod context behind the Kubernetes
  remote-debugging workflow.
- `references/backend-install.md` -- install/check commands for every
  backend (Python, Go, Node/TypeScript, Rust/C/C++), plus the .NET
  extension-point detail in full.
- `references/kubernetes-remote-debugging.md` -- `kubectl port-forward` and
  `kubectl debug` ephemeral-container workflows, per-language notes, and
  which of the two needs approval under `k8s-safety`.
- `references/advanced-techniques.md` -- hangs and deadlocks, concurrency
  bugs, and loop bisection walked through in full.
- Upstream project: `github.com/AlmogBaku/debug-skill` (MIT license, Almog
  Baku) -- source of the `dap` CLI and the DAP-based architecture this
  skill documents. Not maintained by this organization.
