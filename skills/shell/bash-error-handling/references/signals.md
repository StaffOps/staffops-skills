# Signals and Trap Semantics

## Signal table

| Signal | Number | Default action | Catchable | Typical source |
| --- | --- | --- | --- | --- |
| `SIGHUP` | 1 | Terminate | Yes | Terminal closed; conventionally "reload config" for daemons |
| `SIGINT` | 2 | Terminate | Yes | Ctrl-C |
| `SIGQUIT` | 3 | Core dump | Yes | Ctrl-\ |
| `SIGKILL` | 9 | Terminate | **No** | `kill -9`; cannot be trapped or ignored |
| `SIGTERM` | 15 | Terminate | Yes | `kill`, `systemctl stop`, `docker stop` |
| `SIGSTOP` | 19 | Stop | **No** | Cannot be trapped |
| `SIGTSTP` | 20 | Stop | Yes | Ctrl-Z |
| `SIGCONT` | 18 | Continue | Yes | `fg`, `bg` |
| `SIGPIPE` | 13 | Terminate | Yes | Writing to a closed pipe (`... \| head`) |
| `SIGUSR1` | 10 | Terminate | Yes | Application-defined |
| `SIGUSR2` | 12 | Terminate | Yes | Application-defined |
| `SIGALRM` | 14 | Terminate | Yes | `timeout`, alarm(2) |
| `SIGCHLD` | 17 | Ignore | Yes | A child process exited |

Exit status for a signal-terminated process is `128 + signal number`:

| Status | Meaning |
| --- | --- |
| 130 | 128 + 2 → Ctrl-C (SIGINT) |
| 137 | 128 + 9 → SIGKILL (often the OOM killer or `docker kill`) |
| 141 | 128 + 13 → SIGPIPE |
| 143 | 128 + 15 → SIGTERM (normal container/systemd shutdown) |

Seeing **137** in container logs almost always means the OOM killer or an
exceeded `docker stop` grace period. **143** is a normal shutdown.

## Bash pseudo-signals

These are not OS signals; Bash synthesizes them.

| Pseudo-signal | Fires |
| --- | --- |
| `EXIT` | On any shell exit, including from a trapped signal |
| `ERR` | When a command fails under the conditions `set -e` would act on |
| `DEBUG` | Before every simple command |
| `RETURN` | When a function or sourced script returns |

`EXIT` is the only one guaranteed to run on every path (except `SIGKILL`),
which is why cleanup belongs there rather than duplicated across signals.

## Trap syntax and scope

```bash
trap 'handler_code' SIGNAL [SIGNAL ...]
trap function_name EXIT
trap - SIGNAL          # reset to default
trap '' SIGNAL         # ignore the signal entirely
trap -p                # list current traps
```

Quoting matters. Single quotes defer expansion until the trap fires, which is
almost always what you want:

```bash
trap 'rm -rf "$WORKDIR"' EXIT     # $WORKDIR read at trap time -- correct
trap "rm -rf $WORKDIR" EXIT       # expanded NOW; empty if set later -- bug
```

Traps are **not** inherited by subshells or functions by default. `set -E`
(`errtrace`) makes `ERR` inherited; `set -T` (`functrace`) does the same for
`DEBUG` and `RETURN`.

## Preserving exit status

A trap handler's own last command determines the final status unless you
re-exit explicitly. Capture `$?` on the handler's **first** line:

```bash
cleanup() {
    local rc=$?          # must be first -- any command overwrites $?
    rm -rf -- "${WORKDIR:-}" || true
    exit "$rc"
}
trap cleanup EXIT
```

Without `exit "$rc"`, a successful `rm` turns a failed script into exit 0.

## Signals while waiting

Bash does not run a trap in the middle of a foreign foreign command; it waits
for the current command to finish first. A long `sleep` therefore delays
handling:

```bash
sleep 300 &            # background it
wait $!                # `wait` IS interruptible -- trap fires immediately
```

This pattern matters for scripts that must respond promptly to `SIGTERM`, such
as container entrypoints.

## Container and systemd shutdown

`docker stop` sends `SIGTERM`, waits (default 10s), then `SIGKILL`.
`systemctl stop` follows `TimeoutStopSec`. A script that ignores `SIGTERM`
will be killed hard and skip cleanup.

An entrypoint that forwards signals to its child:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

child=0
forward() {
    [[ "$child" -ne 0 ]] && kill -TERM "$child" 2>/dev/null || true
    wait "$child" 2>/dev/null || true
    exit 143
}
trap forward INT TERM

"$@" &
child=$!
wait "$child"
```

Without forwarding, the shell dies and the real workload is orphaned then
`SIGKILL`ed — losing in-flight work and skipping graceful shutdown.

Note that a shell running as **PID 1** does not get default signal handling:
the kernel only delivers signals PID 1 has explicitly trapped. Either trap
`TERM` as above, use `exec` so the real process becomes PID 1, or run an init
shim such as `tini` (`docker run --init`).

```bash
exec "$@"     # replaces the shell; the workload becomes PID 1 directly
```

`exec` is the simplest correct answer whenever the script does no work after
launching the child.

## Ignoring signals deliberately

```bash
trap '' INT               # Ctrl-C does nothing during a critical section
critical_operation
trap - INT                # restore default
```

Use sparingly and always restore. A script that permanently ignores `SIGINT`
is hostile to whoever runs it.

`nohup` sets `SIGHUP` to ignore so a process survives terminal disconnect;
`disown` removes a job from the shell's table so no `SIGHUP` is sent at exit.

## Sending signals

```bash
kill -TERM "$pid"          # polite
kill -KILL "$pid"          # unconditional; no cleanup possible
kill -0 "$pid"             # send nothing; just test whether it exists
pkill -TERM -f 'pattern'   # by command-line pattern
timeout 30 cmd             # SIGTERM after 30s
timeout -k 5 30 cmd        # SIGTERM at 30s, SIGKILL 5s later
```

`kill -0` is the idiomatic liveness check — it tests permission and existence
without delivering a signal.

Always try `SIGTERM` first and give the process time. `kill -9` skips every
cleanup handler: temp files remain, locks are not released, buffered writes
are lost.
