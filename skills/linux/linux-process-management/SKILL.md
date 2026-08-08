---
name: linux-process-management
description: "Inspect processes, signals, limits and cgroups."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [process, ps, signals, cgroups, oom, limits, proc, nice, zombie]
    category: linux
    related_skills: [linux-command-line, linux-filesystem]
---
# Linux Process Management

Finding what a process is doing, why it will not die, why the kernel killed
it, and how to bound what it can consume. Covers `/proc`, signals, `nice`,
`ulimit`, and cgroup v2 — the mechanism behind every container memory limit.

## When to Use

Use when a process will not terminate, a service is being OOM-killed, you need
to know what a hung process is blocked on, when setting resource limits, or
when explaining why a container was killed with exit 137.

## Listing processes

```bash
ps aux                    # BSD syntax: every process, user-oriented
ps -ef                    # System V syntax: equivalent, different columns
ps -eLf                   # include THREADS (one row per thread)
ps auxf                   # ASCII process tree
ps -eo pid,ppid,user,%cpu,%mem,rss,stat,etime,cmd --sort=-%mem | head
ps -p 1234 -o lstart,etime,cmd     # exact start time and elapsed
pstree -p 1234                     # tree from a process
pgrep -af nginx                    # PIDs plus full command line
pgrep -u www-data -f worker        # by user and pattern
```

Custom `-o` output is what makes `ps` useful in scripts — the default columns
rarely match what you need:

```bash
# Top memory consumers, RSS in MiB.
ps -eo rss,pid,user,cmd --sort=-rss | awk 'NR<=11 { $1=int($1/1024)"M"; print }'
```

### Process states (the `STAT` column)

| Code | Meaning |
| --- | --- |
| `R` | Running or runnable |
| `S` | Interruptible sleep — waiting for an event (normal idle state) |
| `D` | **Uninterruptible sleep** — blocked in the kernel, usually on I/O |
| `Z` | Zombie — exited, parent has not reaped it |
| `T` | Stopped (SIGSTOP / SIGTSTP) |
| `t` | Stopped by a debugger |
| `I` | Idle kernel thread |

Modifiers: `s` session leader, `l` multi-threaded, `+` foreground group,
`<` high priority, `N` low priority.

**`D` state matters.** A process in `D` cannot be killed, not even with
`SIGKILL`, because it is inside a kernel call that does not check for signals.
It usually means blocked I/O — a hung NFS mount, a failing disk, or a stuck
device. The fix is to resolve the I/O, not to escalate the signal:

```bash
ps -eo pid,stat,wchan:30,cmd | awk '$2 ~ /D/'   # what kernel function is it in?
cat /proc/<pid>/stack                            # kernel stack (needs root)
```

**Zombies** are already dead; they occupy only a process table entry. You
cannot kill a zombie — you fix the *parent*, which is failing to call `wait()`.
Killing or restarting the parent reparents the zombie to PID 1, which reaps it.

```bash
ps -eo pid,ppid,stat,cmd | awk '$3 ~ /Z/'
```

A handful of zombies is harmless; thousands mean a broken parent, and they can
exhaust the PID space.

## Signals

```bash
kill -TERM 1234          # polite: the process can clean up
kill -KILL 1234          # unconditional: no cleanup, no handler
kill -HUP 1234           # conventionally "reload config"
kill -0 1234             # send nothing; test existence and permission
kill -l                  # list signal names
pkill -TERM -f 'pattern' # by command-line pattern
pkill -u deploy          # by user
killall nginx            # by exact process name
```

Always try `SIGTERM` first and give the process time. `kill -9` skips every
cleanup path: temp files remain, locks are not released, buffered writes are
lost, and databases may need recovery.

An escalation that respects that:

```bash
kill -TERM "$pid"
for _ in {1..10}; do
    kill -0 "$pid" 2>/dev/null || exit 0
    sleep 1
done
kill -KILL "$pid"
```

| Signal | Number | Default | Catchable |
| --- | --- | --- | --- |
| `SIGHUP` | 1 | Terminate | Yes |
| `SIGINT` | 2 | Terminate | Yes |
| `SIGKILL` | 9 | Terminate | **No** |
| `SIGTERM` | 15 | Terminate | Yes |
| `SIGSTOP` | 19 | Stop | **No** |
| `SIGCONT` | 18 | Continue | Yes |
| `SIGUSR1/2` | 10/12 | Terminate | Yes |

Exit status is `128 + signal`, so **137** is SIGKILL (frequently the OOM
killer) and **143** is SIGTERM (normal shutdown).

## /proc

Every process has a directory under `/proc/<pid>` that answers most questions
without any tooling:

```bash
cat /proc/1234/cmdline | tr '\0' ' '   # full command line (NUL-separated)
cat /proc/1234/environ | tr '\0' '\n'  # environment as launched
ls -l /proc/1234/cwd                   # current working directory
ls -l /proc/1234/exe                   # the binary (even if deleted)
ls -l /proc/1234/fd/                   # every open file descriptor
cat /proc/1234/status                  # state, threads, memory, UID, capabilities
cat /proc/1234/limits                  # effective ulimits
cat /proc/1234/io                      # bytes read/written
cat /proc/1234/wchan                   # kernel function it is sleeping in
cat /proc/1234/stack                   # kernel stack trace (root)
cat /proc/1234/cgroup                  # which cgroup it belongs to
```

`/proc/<pid>/exe` pointing at `(deleted)` means the binary was replaced after
the process started — the running code is the old version. This is why a
package upgrade requires a restart to take effect:

```bash
ls -l /proc/*/exe 2>/dev/null | grep deleted
# Debian/Ubuntu has a purpose-built tool:
needrestart -b
```

Memory fields in `/proc/<pid>/status` worth knowing:

| Field | Meaning |
| --- | --- |
| `VmRSS` | Resident set — physical RAM in use |
| `VmSize` | Virtual size — address space, mostly meaningless as a limit |
| `VmSwap` | Swapped out |
| `RssAnon` | Anonymous (heap/stack) — the part that cannot be evicted |
| `RssFile` | File-backed — page cache, reclaimable |
| `Threads` | Thread count |

Alert on `RssAnon`, not `VmSize`. A JVM or Go runtime reserves enormous
virtual address space that is never backed by RAM.

## Open files and sockets

```bash
lsof -p 1234                # everything the process has open
lsof -i :8080               # who is listening on a port
lsof -i -P -n               # all network connections, numeric
lsof /var/log/app.log       # who holds this file
lsof +L1                    # deleted files still held open
fuser -v /mnt/data          # who is using a mount (blocks umount)
fuser -k /mnt/data          # kill them

ss -tlnp                    # listening TCP sockets with the owning process
ss -tanp state established  # established connections
```

`lsof +L1` and `lsof | grep deleted` are the diagnostic for "disk full but
`du` shows nothing" — see the `linux-filesystem` skill.

## Priority

```bash
nice -n 10 command          # start with lower priority (higher nice = nicer)
renice -n 5 -p 1234         # change a running process
renice -n 5 -u backup       # every process of a user

ionice -c 3 command         # I/O class 3 = idle
ionice -c 2 -n 7 -p 1234    # best-effort, lowest priority
```

Nice ranges from -20 (highest priority) to 19 (lowest). Only root can lower
the nice value. `nice` affects **CPU** scheduling only — for I/O contention,
`ionice` is the relevant knob, and it only works with the CFQ/BFQ schedulers.

## Resource limits

```bash
ulimit -a                   # all current limits
ulimit -n                   # open file descriptors (soft)
ulimit -Hn                  # hard limit
ulimit -n 65536             # raise the soft limit up to the hard limit
cat /proc/1234/limits       # a RUNNING process's actual limits
```

Persistent limits in `/etc/security/limits.conf` apply to **login sessions**
via PAM:

```
deploy  soft  nofile  65536
deploy  hard  nofile  65536
*       soft  nproc   4096
```

They do **not** apply to systemd services. That is a frequent surprise — for
services, set them in the unit:

```ini
[Service]
LimitNOFILE=65536
LimitNPROC=4096
LimitCORE=0
```

`Too many open files` in a service log means `LimitNOFILE`, not
`limits.conf`. Verify against the running process with `/proc/<pid>/limits`,
never against your shell's `ulimit`.

## cgroups v2

cgroups are the kernel mechanism behind container limits and systemd resource
control. On a v2 system everything lives under `/sys/fs/cgroup`.

```bash
cat /proc/1234/cgroup                            # which cgroup a process is in
systemd-cgls                                     # cgroup tree
systemd-cgtop                                    # live resource use per cgroup

cd /sys/fs/cgroup/system.slice/myapp.service
cat memory.current      # bytes in use now
cat memory.max          # hard limit; exceeding it triggers the OOM killer
cat memory.high         # soft limit; triggers reclaim and throttling
cat memory.events       # counters, including `oom_kill`
cat cpu.stat            # usage and throttling counters
cat pids.current pids.max
```

Set limits declaratively through systemd rather than writing to the
filesystem, which does not survive a reboot:

```ini
[Service]
MemoryMax=2G
MemoryHigh=1800M
CPUQuota=200%          # 2 cores
TasksMax=512
IOWeight=50
```

`MemoryHigh` is the more useful knob: it throttles and reclaims under
pressure, whereas `MemoryMax` kills. Setting `High` slightly below `Max` gives
a warning band instead of a cliff.

## The OOM killer

When memory is exhausted the kernel kills a process. The victim is chosen by
`oom_score`, weighted by memory use and adjustable per process.

```bash
dmesg -T | grep -i -E 'oom|killed process'
journalctl -k | grep -i oom
cat /proc/1234/oom_score        # current score
cat /proc/1234/oom_score_adj    # -1000 (never) .. 1000 (kill first)
echo -500 > /proc/1234/oom_score_adj
```

A kernel OOM message names the victim, its RSS, and the cgroup:

```
Out of memory: Killed process 4242 (java) total-vm:8G, anon-rss:6G, ...
```

Two distinct cases, often confused:

- **Global OOM** — the machine ran out. `dmesg` shows it; the victim may be
  an innocent bystander rather than the process that caused it.
- **cgroup OOM** — one container or service hit `memory.max`. The victim is
  always inside that cgroup. Check `memory.events` for `oom_kill`.

For a service, exit code 137 plus `oom_kill` incrementing in
`memory.events` is conclusive.

Protect a critical process:

```ini
[Service]
OOMScoreAdjust=-500
```

## Pitfalls

- **`kill -9` as the first response** — skips cleanup and can corrupt state.
  Escalate from `SIGTERM`.
- **Trying to kill a `D`-state process** — impossible by design; fix the I/O.
- **Trying to kill a zombie** — it is already dead; fix the parent.
- **`ulimit` in a shell to diagnose a service** — services get limits from the
  unit, not from `limits.conf`. Read `/proc/<pid>/limits`.
- **Alerting on `VmSize`** — use `VmRSS` or `RssAnon`.
- **Assuming exit 137 is always the OOM killer** — it is SIGKILL, which also
  comes from `docker kill` or an expired stop timeout.
- **`nice` for I/O problems** — `nice` is CPU only; use `ionice`.
- **Background jobs killed when the shell exits** — `nohup`, `setsid`, or
  `systemd-run`.

## Verification

```bash
ps -p "$pid" -o pid,stat,wchan:30,etime,cmd
cat /proc/"$pid"/limits | grep -i 'open files'
cat /proc/"$pid"/status | grep -E 'VmRSS|RssAnon|Threads'
systemctl show myapp -p MemoryMax -p MemoryCurrent -p TasksCurrent
cat /sys/fs/cgroup/system.slice/myapp.service/memory.events
```

`scripts/proc-inspect.sh` gathers all of the above for a PID in one report.

## Reference

- `references/proc-filesystem.md` — `/proc` entries and how to read them
- `references/cgroups-v2.md` — controllers, limits, and systemd mapping
- `scripts/proc-inspect.sh` — one-shot diagnostic report for a PID
- `examples/graceful-kill.sh` — SIGTERM-then-SIGKILL escalation with timeout

## When NOT to use

- **Systemd unit lifecycle** (enable/disable/restart services) — see [systemd-services](../linux/systemd-services/SKILL.md).
- **Container process namespaces** — use container runtime docs or Kubernetes debugging tools.
- **Performance root-cause analysis** (CPU flamegraphs, scheduler latency) — see [linux-performance-analysis](../linux/linux-performance-analysis/SKILL.md).


## Decision tree

```
What's wrong with the process?
├── Process stuck / unresponsive?
│   ├── State D (uninterruptible sleep) → blocked on I/O, check disk/NFS
│   ├── State S but not responding → strace -p PID to see what it's waiting on
│   └── State T (stopped) → someone sent SIGSTOP; kill -CONT PID
├── Too much CPU?
│   ├── Legitimate load → renice / cpulimit / cgroups
│   ├── Runaway loop → strace / perf top to identify hot path
│   └── Fork bomb → kill process group: kill -9 -PGID
├── Zombie (Z state)?
│   ├── Parent alive → parent isn't calling wait(); fix or restart parent
│   └── Parent dead → init should reap; if stuck, only reboot clears
├── Can't kill it (kill -9 doesn't work)?
│   ├── State D → kernel-level block; fix underlying I/O (unmount, etc.)
│   └── Kernel thread → cannot kill; address root cause
└── Too many open files?
    └── Check → ls /proc/PID/fd | wc -l; raise via ulimit or systemd LimitNOFILE
```

## Related skills

- [systemd-services](../linux/systemd-services/SKILL.md) — managing services, timers, journald.
- [linux-performance-analysis](../linux/linux-performance-analysis/SKILL.md) — CPU/mem/IO profiling.
- [bash-scripting](../shell/bash-scripting/SKILL.md) — automating process management in scripts.
- [incident-triage-linux](../troubleshooting/incident-triage-linux/SKILL.md) — when a runaway process causes an outage.
