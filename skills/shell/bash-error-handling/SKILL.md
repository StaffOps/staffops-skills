---
name: bash-error-handling
description: "Make shell scripts fail fast, loudly, and cleanly."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [bash, errexit, trap, retry, cleanup, reliability]
    category: shell
    related_skills: [bash-scripting, shell-cli-design, shell-testing-linting]
---
# Bash Error Handling

Strict mode, traps, cleanup, and retries — and the substantial list of cases
where `set -e` silently does not do what people assume. A script that exits 0
after failing is worse than one that never ran.

## When to Use

Use when a script swallowed an error and reported success, when writing
anything that creates temp files or acquires locks, when adding retries around
flaky network calls, or when reviewing a script for production readiness.

## Quick Reference

| Directive | Effect |
| --- | --- |
| `set -e` | Exit when a command returns non-zero |
| `set -u` | Exit when an unset variable is expanded |
| `set -o pipefail` | A pipeline fails if **any** stage fails, not just the last |
| `set -E` | `ERR` traps are inherited by functions and subshells |
| `shopt -s inherit_errexit` | `set -e` applies inside `$(...)` (Bash 4.4+) |

The standard preamble:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
shopt -s inherit_errexit 2>/dev/null || true
```

`set -E` is the one most often forgotten, and without it an `ERR` trap never
fires inside a function — which is where most real code lives.

## Where `set -e` does not fire

This is the critical part. `set -e` is not a general exception mechanism, and
these exemptions cause the "script reported success but did nothing" class of
bug.

**1. Any command in a condition.** The entire point of `if` is to test a
status, so nothing inside the condition triggers an exit:

```bash
if grep -q pattern file; then ...   # non-zero here is normal
while ! ready; do ...               # same
```

Less obviously, this extends to `&&` and `||` chains — only the **last**
command in the chain is checked:

```bash
false && true      # no exit: `false` is not last
false || true      # no exit: status is 0
cmd1 && cmd2       # if cmd1 fails, the whole thing returns non-zero -> exits
```

**2. Functions called in a condition.** `set -e` is disabled for the *entire
call tree* of a function invoked in a conditional context:

```bash
deploy() {
    rm /nonexistent      # fails
    echo "still running" # set -e does NOT stop this
}

if deploy; then ...      # every command inside deploy is now unguarded
```

This is the single most dangerous exemption. If a function must fail fast, do
not call it from an `if`; check `$?` afterwards or restructure.

**3. Assignments capturing a substitution.** The assignment's status is what
counts, and an assignment always succeeds:

```bash
output=$(false)          # no exit; $? of the assignment is 0
echo "reached"

# Fix: declare and assign separately.
local output
output=$(false) || die "command failed"
```

`local x=$(false)` has the same problem — `local` is a command that returns 0.
This is shellcheck SC2155.

**4. Pipelines, without `pipefail`.** Only the last stage's status is used:

```bash
set -e
false | true      # status 0, no exit
```

With `set -o pipefail` the pipeline returns the rightmost non-zero status.
Note the interaction with `head`, which exits early and gives upstream
commands `SIGPIPE`:

```bash
set -o pipefail
grep pattern huge.log | head -1     # grep dies with SIGPIPE -> 141 -> exit
```

Guard it: `{ grep pattern huge.log || true; } | head -1`.

**5. Arithmetic evaluating to zero.** `(( expr ))` returns 1 when the result
is 0:

```bash
count=0
(( count++ ))     # returns 1 (post-increment yields the OLD value) -> exits
```

Use `count=$(( count + 1 ))`, or append `|| true`.

The full list, with reproductions, is in `references/errexit-pitfalls.md`.

## Traps

`trap` runs a handler on a signal or pseudo-signal.

| Signal | Fires when |
| --- | --- |
| `EXIT` | Any exit — success, failure, or signal. Use for cleanup. |
| `ERR` | A command fails under `set -e`. Use for diagnostics. |
| `INT` | Ctrl-C |
| `TERM` | `kill` |

```bash
cleanup() {
    local rc=$?                      # capture BEFORE anything else
    [[ -n "${WORKDIR:-}" ]] && rm -rf -- "$WORKDIR"
    exit "$rc"                       # preserve the original status
}
trap cleanup EXIT
```

Two rules: capture `$?` on the trap's first line, and re-`exit` with it. A
handler that ends on a successful command turns a failure into success.

An `ERR` trap that prints a stack trace turns "it broke" into "it broke at
line 87 in deploy()":

```bash
on_error() {
    local rc=$? line=$1
    printf 'error: exit %d at line %d\n' "$rc" "$line" >&2
    local frame=0 l f s
    while read -r l f s < <(caller "$frame"); do
        printf '  at %s() %s:%s\n' "$f" "$s" "$l" >&2
        ((frame++))
    done
    exit "$rc"
}
trap 'on_error $LINENO' ERR
```

## Cleanup patterns

**Temp directories.** Create once, register the trap immediately:

```bash
WORKDIR="$(mktemp -d)"
trap 'rm -rf -- "$WORKDIR"' EXIT
```

**Atomic writes.** Never leave a half-written file where a reader can see it:

```bash
tmp="${target}.tmp.$$"
generate > "$tmp"
mv -- "$tmp" "$target"      # rename is atomic within a filesystem
```

**Locking.** `flock` prevents concurrent runs without a stale-PID-file race:

```bash
exec 9>"/var/lock/${SCRIPT_NAME}.lock"
flock -n 9 || die "another instance is running"
# lock is released automatically when the process exits
```

**Stacked handlers.** A single `EXIT` trap replaces any previous one. To
accumulate cleanup actions, push onto an array:

```bash
declare -a CLEANUP=()
add_cleanup() { CLEANUP+=("$1"); }
run_cleanup() {
    local rc=$? i
    for (( i=${#CLEANUP[@]}-1; i>=0; i-- )); do
        eval "${CLEANUP[i]}" || true      # reverse order, never abort cleanup
    done
    exit "$rc"
}
trap run_cleanup EXIT
```

## Retries

Retry only *idempotent* operations, only on *transient* failures, and always
with a bounded ceiling and jitter. `scripts/retry.sh` is a drop-in
implementation:

```bash
retry --attempts 5 --delay 1 --max-delay 30 -- curl -fsS "$url"
```

Exponential backoff with jitter, inline:

```bash
attempt=1 delay=1
until curl -fsS "$url" -o out.json; do
    (( attempt++ >= 5 )) && die "giving up after 5 attempts"
    sleep "$(( delay + RANDOM % delay ))"
    (( delay = delay * 2 > 30 ? 30 : delay * 2 ))
done
```

Retrying a non-idempotent call (a POST that creates a resource) turns one
timeout into duplicate records. If retry is required, make the operation
idempotent first with an idempotency key.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | General error |
| 2 | Usage error (bad arguments) |
| 126 | Found but not executable |
| 127 | Command not found |
| 128+N | Killed by signal N (130 = Ctrl-C, 137 = SIGKILL, 143 = SIGTERM) |

Reserve 3-125 for meaningful application-specific codes and document them in
`--help`. Callers can then branch on the reason for failure.

## Pitfalls

- **`trap cleanup EXIT` before `WORKDIR` is set** — the handler runs with an
  unset variable under `set -u` and fails. Use `"${WORKDIR:-}"`.
- **Cleanup that itself fails** — under `set -e` the handler aborts partway,
  leaving resources behind. Append `|| true` to each cleanup step.
- **`set -e` in a sourced file** — it applies to the *calling* shell. Library
  files should not set shell options.
- **Checking `$?` after anything else** — even `echo` overwrites it. Capture
  it on the very next line.
- **`set -u` with `"$@"` on Bash < 4.4** — empty `$@` triggers "unbound
  variable". Use `"${@:-}"` for portability.
- **Assuming `set -e` in a subshell propagates** — `( cmd )` failing does not
  exit the parent unless the subshell's status is checked.

## Verification

```bash
shellcheck -x script.sh          # flags SC2155, SC2164, missing quotes
bash -n script.sh                # syntax only
```

Test the failure paths explicitly — inject a failing command and confirm the
script exits non-zero and cleans up:

```bash
./script.sh --input /nonexistent; echo "exit=$?"
ls /tmp/scriptname.* 2>/dev/null && echo "LEAK: temp files remain"
```

## Reference

- `references/errexit-pitfalls.md` — every `set -e` exemption with repros
- `references/signals.md` — signal table and trap semantics
- `scripts/retry.sh` — retry with exponential backoff and jitter
- `scripts/strict-preamble.sh` — sourceable strict-mode + trap boilerplate
- `examples/atomic-deploy.sh` — locking, staging, rollback on failure

## When NOT to use

- **Writing the script itself** (functions, loops, arrays) — see [bash-scripting](../shell/bash-scripting/SKILL.md).
- **Argument parsing and CLI UX** — see [shell-cli-design](../shell/shell-cli-design/SKILL.md).
- **Complex error recovery** that needs retry logic across services — consider Python or a proper orchestrator.


## Decision tree

```
What failure mode are you handling?
├── Exit code from a command?
│   ├── Single command → if ! cmd; then handle; fi
│   └── Pipeline → set -o pipefail + check $?
├── Subshell swallowing errors?
│   ├── $() substitution → assign + check: out=$(cmd) || die
│   └── Piped subshell → use process substitution or temp file
├── Need cleanup on ANY exit?
│   ├── Single resource → trap cleanup EXIT
│   └── Multiple resources → trap with stack pattern
└── Script-wide strictness?
    ├── New script → set -euo pipefail (strict mode)
    └── Legacy script → add guards incrementally, test each
```

## Related skills

- [bash-scripting](../shell/bash-scripting/SKILL.md) — script structure, quoting, parameter expansion.
- [shell-cli-design](../shell/shell-cli-design/SKILL.md) — argument parsing, help text, exit codes.
- [shell-testing-linting](../shell/shell-testing-linting/SKILL.md) — shellcheck, bats, validating error paths.
- [systematic-debugging](../troubleshooting/systematic-debugging/SKILL.md) — structured approach to finding root cause.
