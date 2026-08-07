# Exit Code Conventions

An exit code is the only thing a caller can rely on without parsing text.
Getting it right is what makes a script usable from another script.

## The baseline

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | General failure |
| 2 | Usage error: bad, missing, or conflicting arguments |
| 3-125 | Application-specific, documented in `--help` |
| 126 | Command found but not executable (permission denied) |
| 127 | Command not found |
| 128 | Invalid argument to `exit` |
| 128+N | Terminated by signal N |
| 255 | Exit status out of range |

Only 0-255 are valid. `exit 256` becomes 0 and `exit -1` becomes 255, which is
a real source of silent bugs — never pass an unbounded value to `exit`.

## Signal codes

| Code | Signal | Common cause |
| --- | --- | --- |
| 130 | SIGINT (2) | Ctrl-C |
| 137 | SIGKILL (9) | OOM killer, `kill -9`, container limit exceeded |
| 139 | SIGSEGV (11) | Segmentation fault |
| 141 | SIGPIPE (13) | Writing to a closed pipe (`... \| head`) |
| 143 | SIGTERM (15) | `kill`, `systemctl stop`, `docker stop` |

In container logs, **137** almost always means the OOM killer or a `docker
stop` grace period expiring; **143** is a normal graceful shutdown. Treating
143 as a failure creates false alerts.

## sysexits.h

BSD defines a richer set in `/usr/include/sysexits.h`. Following it is
optional, but it is the closest thing to a standard for codes above 2:

| Code | Name | Meaning |
| --- | --- | --- |
| 64 | `EX_USAGE` | Command line usage error |
| 65 | `EX_DATAERR` | Input data was incorrect |
| 66 | `EX_NOINPUT` | Input file did not exist or was unreadable |
| 67 | `EX_NOUSER` | User did not exist |
| 68 | `EX_NOHOST` | Host did not exist |
| 69 | `EX_UNAVAILABLE` | A required service is unavailable |
| 70 | `EX_SOFTWARE` | Internal software error |
| 71 | `EX_OSERR` | System error (fork failed, etc.) |
| 73 | `EX_CANTCREAT` | Could not create an output file |
| 74 | `EX_IOERR` | I/O error |
| 75 | `EX_TEMPFAIL` | Temporary failure; the caller may retry |
| 76 | `EX_PROTOCOL` | Remote returned something invalid |
| 77 | `EX_NOPERM` | Permission denied |
| 78 | `EX_CONFIG` | Configuration error |

`EX_TEMPFAIL` (75) is genuinely useful: it tells a wrapper that retrying is
sensible, whereas 65 (bad data) will never succeed on retry.

Pick one scheme — plain 0/1/2 plus a few documented codes, or sysexits — and
apply it consistently. Mixing them is worse than either.

## Well-known tool codes

Knowing these avoids misreading CI failures:

| Tool | Code | Meaning |
| --- | --- | --- |
| `grep` | 0 / 1 / 2 | Match found / no match / error |
| `diff` | 0 / 1 / 2 | Identical / different / error |
| `curl` | 6 / 7 / 22 / 28 / 35 | DNS failure / connect failed / HTTP >= 400 with `-f` / timeout / TLS error |
| `rsync` | 23 / 24 | Partial transfer / files vanished during transfer |
| `ssh` | 255 | ssh's own error, as opposed to the remote command's status |
| `make` | 2 | Build failure |
| `test` / `[` | 0 / 1 / 2 | True / false / usage error |
| `timeout` | 124 / 125 / 126 / 127 | Timed out / timeout itself failed / not executable / not found |
| `xargs` | 123 / 124 / 125 | Some invocation exited 1-125 / a command exited 255 / a command was killed by a signal |

`grep` returning 1 is **not an error** — it means no match. Under `set -e`
this exits the script, which is why it needs a guard:

```bash
count="$(grep -c pattern file || true)"
if grep -q pattern file; then ...        # conditional context, exempt
```

`ssh` returning 255 is ambiguous with a remote command that genuinely exits
255, so treat 255 as a connection failure and have remote commands use a
narrower range.

## Capturing status correctly

```bash
cmd
status=$?              # must be the very next line; anything overwrites $?
```

For pipelines, `$?` is the last stage only. Use `PIPESTATUS` (immediately
after, before any other command):

```bash
a | b | c
statuses=("${PIPESTATUS[@]}")     # copy at once -- it is clobbered instantly
if (( statuses[0] != 0 )); then die "stage a failed"; fi
```

Or set `pipefail` so the pipeline reports the rightmost non-zero status.

## Propagating status through a trap

An `EXIT` trap whose last command succeeds turns a failure into success:

```bash
cleanup() {
    local rc=$?          # capture first
    rm -rf "$WORKDIR"
    exit "$rc"           # restore -- without this, exit is 0
}
trap cleanup EXIT
```

## Aggregating in a loop

Do not let the last iteration's status win:

```bash
rc=0
for item in "${items[@]}"; do
    process "$item" || rc=1        # remember any failure
done
exit "$rc"
```

To distinguish "all failed" from "some failed", count instead:

```bash
failed=0 total=0
for item in "${items[@]}"; do
    total=$(( total + 1 ))
    process "$item" || failed=$(( failed + 1 ))
done
(( failed == 0 )) && exit 0
(( failed == total )) && exit 1     # complete failure
exit 3                              # partial failure -- documented in --help
```

Partial success is common in batch tools and deserves its own code so callers
can decide whether to alert.

## Testing exit codes

```bash
./tool.sh; echo "no args -> $?"                 # expect 2
./tool.sh --bogus; echo "bad flag -> $?"        # expect 2
./tool.sh -i missing; echo "no input -> $?"     # expect 1 or 66
./tool.sh -i good; echo "success -> $?"         # expect 0
```

In `bats`:

```bash
@test "usage error is 2" {
    run ./tool.sh
    [ "$status" -eq 2 ]
}
```

Asserting on exit codes is the cheapest interface test there is, and it is the
contract other scripts actually depend on.
