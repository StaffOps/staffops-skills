# Every Place `set -e` Does Not Fire

`set -e` (`errexit`) is widely assumed to mean "abort on any error". It does
not. Every case below is specified behavior, not a bug. Each is reproducible
by pasting the snippet into a file and running it.

The practical conclusion: `set -e` is a safety net for *unanticipated*
failures. Anything you actually care about should be checked explicitly.

## 1. Commands in a condition

Any command whose status is being *tested* is exempt, because testing a status
is the whole point.

```bash
#!/usr/bin/env bash
set -e
if false; then :; fi          # no exit
while false; do :; done       # no exit
until true; do :; done        # no exit
false && echo unreachable     # no exit -- `false` is not the last command
false || echo "handled"       # no exit -- overall status is 0
! false                       # no exit
echo "reached the end"
```

Only the **final** command of an `&&`/`||` chain is checked:

```bash
set -e
cmd_a && cmd_b        # cmd_a failing => chain returns non-zero => exits
cmd_a || cmd_b        # cmd_a failing is fine; cmd_b failing => exits
```

## 2. Functions invoked in a conditional context

The exemption is inherited by the entire call tree. This is the most dangerous
case because it silently disables strict mode across a large body of code.

```bash
#!/usr/bin/env bash
set -e

risky() {
    false
    echo "THIS RUNS -- set -e is suppressed inside risky()"
    false
    echo "AND THIS TOO"
}

if risky; then
    echo "branch taken"
fi
```

Output shows both `echo`s. The function's status is that of its last command.

**Workarounds:**

```bash
# a) Don't call it conditionally; check afterwards.
risky
status=$?

# b) Make the function explicit about failure.
risky() {
    false || return 1
    echo "not reached"
}

# c) Run it in a subshell with its own errexit (status still checkable).
if ( set -e; risky ); then ...
```

## 3. Assignments that capture command substitution

An assignment's exit status is the assignment's own, which is always 0 unless
the variable is readonly.

```bash
#!/usr/bin/env bash
set -e
value=$(false)
echo "reached, value='${value}', \$?=$?"     # prints, $? is 0
```

`local`, `declare`, `export`, and `readonly` are **commands**, so they mask the
substitution's status even more thoroughly:

```bash
f() {
    local v=$(false)       # local returns 0; failure invisible
    echo "reached"
}
```

This is shellcheck **SC2155**. The fix is always to split:

```bash
local v
v=$(false) || die "generation failed"
```

Bash 4.4+ with `shopt -s inherit_errexit` makes `set -e` apply *inside* the
`$(...)` subshell, but the assignment's own status is still 0 — so this only
helps for multi-command substitutions, not for the case above.

## 4. Pipelines without `pipefail`

A pipeline's status is that of its **last** command only.

```bash
#!/usr/bin/env bash
set -e
false | true
echo "reached -- pipeline status was 0"
```

`set -o pipefail` fixes it, but introduces a `SIGPIPE` interaction. When a
downstream command exits early, upstream commands are killed with signal 13
(status 141):

```bash
set -eo pipefail
grep something very-large.log | head -1     # may exit 141
```

Guard the upstream side:

```bash
{ grep something very-large.log || true; } | head -1
```

`PIPESTATUS` holds every stage's status when you need them individually:

```bash
set +e
a | b | c
statuses=("${PIPESTATUS[@]}")
set -e
printf 'stage statuses: %s\n' "${statuses[*]}"
```

## 5. Arithmetic that evaluates to zero

`(( expr ))` returns 1 when the expression's value is 0 — modeling C's truth
semantics, not success semantics.

```bash
#!/usr/bin/env bash
set -e
count=0
(( count++ ))            # post-increment yields 0 (the old value) -> status 1
echo "never reached"
```

Safe forms:

```bash
count=$(( count + 1 ))   # assignment always succeeds
(( ++count ))            # pre-increment yields 1 here, but breaks at -1 -> 0
(( count++ )) || true    # explicit
```

The general rule: never use `(( ))` as a statement under `set -e` unless the
result is guaranteed non-zero. Use it only in conditions.

## 6. Subshells

A failing subshell exits the *subshell*. The parent only reacts if the status
is checked in a non-exempt position.

```bash
set -e
( false; echo "subshell continues? no" )   # subshell exits here
echo "parent status: $?"                    # parent DOES exit at the subshell
```

But in an exempt position, both layers are suppressed:

```bash
set -e
if ( false; echo "runs" ); then :; fi      # prints "runs"
```

Background jobs are never checked at all:

```bash
set -e
false &
wait          # `wait` returns the job's status -- check it explicitly
```

## 7. `set -u` and empty `$@`

On Bash before 4.4, expanding `"$@"` with no positional parameters under
`set -u` is an "unbound variable" error:

```bash
set -u
f() { echo "$@"; }
f            # Bash < 4.4: error; Bash >= 4.4: fine
```

Portable form: `"${@:-}"`, or guard with `(( $# ))`.

Similarly, an empty array under `set -u` on Bash < 4.4:

```bash
arr=()
echo "${arr[@]}"      # older Bash: unbound variable
echo "${arr[@]:-}"    # safe everywhere
```

## 8. `set -e` does not survive `source` boundaries the way you expect

`source`d files run in the current shell, so a `set -e` inside a library
changes the caller's behavior globally — usually unwanted:

```bash
# lib.sh
set -e          # BAD: mutates the caller's shell
```

Libraries should never set shell options. If a library function needs strict
behavior, enforce it locally:

```bash
strict_thing() (       # note: parentheses -- runs in a subshell
    set -e
    ...
)
```

## Summary table

| Context | `set -e` fires? | Safe alternative |
| --- | --- | --- |
| `if cmd; then` | No | Check `$?` after an unconditional call |
| `while cmd` / `until cmd` | No | — |
| `cmd && other` (non-final) | No | Split into separate statements |
| `cmd \|\| fallback` | No | Intentional; fine |
| `! cmd` | No | — |
| Function called in `if` | No (whole tree) | Don't; or `( set -e; f )` |
| `v=$(false)` | No | `v=$(...) \|\| die` |
| `local v=$(false)` | No | Split declaration and assignment |
| `false \| true` | No (without pipefail) | `set -o pipefail` |
| `(( 0 ))` | **Yes**, exits | `x=$(( ... ))` or `\|\| true` |
| `cmd &` | No | `wait "$!"` and check |
| Inside `$(...)` | No (pre-4.4) | `shopt -s inherit_errexit` |

## The defensive posture

Given all of the above, treat `set -e` as a backstop rather than a guarantee:

```bash
set -Eeuo pipefail
shopt -s inherit_errexit 2>/dev/null || true

# Check anything that matters, explicitly.
if ! output=$(fetch_config); then
    die "could not fetch config"
fi

# Make intent visible when ignoring a failure.
optional_step || true
```

Explicit checks document intent; `set -e` catches what you forgot.
