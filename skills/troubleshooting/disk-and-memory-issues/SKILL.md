---
name: disk-and-memory-issues
description: "Diagnose OOM kills, leaks, disk pressure and swap."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [oom, memory-leak, disk-full, swap, cgroup, inode, page-cache]
    category: troubleshooting
    related_skills: [linux-process-management, linux-filesystem, linux-performance-analysis]
---
# Disk and Memory Issues

The two resources that most commonly cause outright failures rather than
just slowness — memory (leaks, OOM kills) and disk (space and inode
exhaustion) — and the specific diagnostic sequences for each. This is the
condensed, incident-focused version; `linux-process-management` and
`linux-filesystem` have the full mechanism underneath.

## When to Use

Use when a process was killed unexpectedly, memory usage is climbing over
time, a disk is reporting full despite apparent free space, or triaging
which of these two resources is actually the cause of a broader symptom.

## Memory: is it actually the OOM killer?

```bash
dmesg -T | grep -i "killed process"
journalctl -k | grep -i "out of memory"
cat /sys/fs/cgroup/<path>/memory.events   # oom_kill counter, for a specific cgroup/container
```

A kernel OOM message names the victim directly:

```
Out of memory: Killed process 4242 (java) total-vm:8388608kB, anon-rss:6291456kB
```

Two distinct scopes, and confusing them wastes time:

- **Global OOM** (from `dmesg`) — the whole host ran out. The victim named
  might be an innocent bystander selected by `oom_score`, not necessarily
  the process that caused the pressure.
- **cgroup/container OOM** (`memory.events`, `oom_kill` counter) — one
  specific container/service hit its own limit. The victim is always
  something inside that cgroup.

Exit code **137** from a process (`128 + SIGKILL`) is consistent with an OOM
kill but not proof by itself — it's also what `docker kill` or a plain `kill
-9` produce. Confirm with `dmesg`/`memory.events`, don't infer from the exit
code alone.

## Distinguishing a leak from legitimate growth

```bash
ps -o rss,etime,cmd -p <pid>              # RSS now, and how long it's been running
grep VmRSS /proc/<pid>/status              # current resident memory precisely
```

A single snapshot cannot distinguish a leak from a workload that legitimately
needs more memory as it runs (a cache warming up, a batch job accumulating
results). **The distinguishing signal is the growth pattern over time**:

```bash
# Sample RSS every 60s and watch the trend.
while true; do
    date +%s
    grep VmRSS /proc/<pid>/status
    sleep 60
done
```

| Pattern | Likely cause |
| --- | --- |
| Grows, then plateaus at a stable level | Normal — cache/pool reached its intended size |
| Grows, drops periodically (sawtooth) | Normal — garbage collection cycles |
| Grows without bound, no drops | A genuine leak |
| Grows in step-changes correlated with specific requests | A leak triggered by a specific code path — correlate with request logs |

A language runtime with a garbage collector (Java, Go, Node, Python)
legitimately holds memory it isn't actively using between GC cycles — a
sawtooth pattern in RSS is normal, not a leak. What actually indicates a
problem is the *floor* of that sawtooth rising over successive cycles.

## Finding what's consuming memory

```bash
ps -eo rss,pid,user,cmd --sort=-rss | head -20
smem -tk 2>/dev/null                          # accounts for shared memory correctly, if installed
cat /proc/<pid>/smaps_rollup                  # detailed breakdown for one process
grep -E "RssAnon|RssFile|VmSwap" /proc/<pid>/status
```

`RssAnon` (heap and stack — genuinely "owned" memory) versus `RssFile`
(memory-mapped files, largely page cache and reclaimable under pressure) is
the distinction that matters — a process showing high total RSS but mostly
`RssFile` is not necessarily a memory problem; the kernel can reclaim that
under pressure. High and climbing `RssAnon` is the real signal for a leak.

## Swap

```bash
free -h
vmstat 1                       # si/so columns: swap IN/OUT activity, not just usage
swapon --show
```

**Swap *usage* (a nonzero number) is not itself alarming** — the kernel may
have swapped out genuinely idle pages that haven't been touched in a long
time, which is a reasonable use of swap space. **Swap *activity*** (nonzero
`si`/`so` in `vmstat`, meaning pages are actively being moved in and out
right now) is the real problem — it means the working set no longer fits in
RAM and the system is thrashing, which is orders of magnitude slower than
RAM and typically the actual cause of severe, sudden slowness that looks
disconnected from any CPU or disk signal.

## Disk: space exhaustion

```bash
df -h                # per-filesystem usage
df -i                # per-filesystem INODE usage -- a completely separate limit
```

**"No space left on device" with `df -h` showing free space** has a short
list of usual causes, roughly in order of frequency:

1. **Inodes exhausted** (`df -i` at 100%, `df -h` not) — huge numbers of
   small files; check with `find /path -xdev | wc -l` per candidate
   directory.
2. **A deleted file still held open by a process** — `du` can't see it
   (it's unlinked from any directory), but `df` still counts its blocks as
   used until the holding process closes it or exits:
   ```bash
   lsof +L1 2>/dev/null | head       # files with a link count of 0
   ```
3. **Reserved blocks** — ext4 reserves ~5% for root by default; a non-root
   process can hit "full" while `df` still shows a small amount free (that
   reserved margin).

## Finding what's actually consuming disk space

```bash
du -xh --max-depth=2 /var 2>/dev/null | sort -rh | head -20
find /var/log -type f -size +100M -exec ls -lh {} \;
journalctl --disk-usage                          # the systemd journal specifically, often larger than expected
docker system df 2>/dev/null                      # if Docker is in use, frequently the largest single consumer
```

The journal and Docker's layer/volume/build-cache storage are two of the
most commonly overlooked large consumers — a `du` sweep of `/var/log` and
application directories alone can miss both entirely.

## Disk performance vs disk space — a different problem entirely

A full disk and a *slow* disk produce overlapping symptoms (application
errors, timeouts) but need different diagnosis:

```bash
df -h                    # space
iostat -xz 1 3            # performance: %util, await, queue depth
```

High `%util` with high `await` in `iostat` is a saturated device — different
root cause and different fix than exhausted space, even though both can
manifest as "writes are failing" or "the application is timing out." Always
check both before assuming which one it is.

## The combined triage sequence

```
Something failed / process died / app is erroring
│
├─ dmesg -T | tail -30              -- kernel-level events: OOM, disk errors, hardware
├─ free -h ; vmstat 1                -- memory pressure and swap ACTIVITY
├─ df -h ; df -i                     -- disk space AND inodes
├─ journalctl -p err --since "-15m" -- recent errors across the system
└─ if a specific process is implicated:
    ├─ /proc/<pid>/status            -- RssAnon vs RssFile, current state
    └─ /sys/fs/cgroup/.../memory.events   -- cgroup-specific OOM history
```

This is the disk/memory-specific instance of the layered approach in
`linux-troubleshooting-methodology` — check the cheap, broad signals first
(a handful of commands) before diving into any single process or file in
depth.

## Pitfalls

- **Treating any nonzero swap usage as a problem** — check `si`/`so`
  *activity* instead; idle swapped pages are normal.
- **Assuming exit 137 proves an OOM kill** — confirm via `dmesg` or
  `memory.events`; other things also send SIGKILL.
- **Diagnosing a leak from a single memory snapshot** — a growth *pattern*
  over time is what distinguishes a leak from normal, bounded growth.
- **`du` not finding what's filling the disk** — a deleted-but-open file is
  invisible to `du` but still counted by `df`; check `lsof +L1`.
- **Confusing `df -h` (space) with `df -i` (inodes)** — they're independent
  limits and need separate checks.
- **Diagnosing disk-full and disk-slow as the same problem** — space
  exhaustion and I/O saturation have overlapping symptoms but different
  root causes.
- **Not checking journal/Docker storage** when sweeping for large disk
  consumers — both are frequently the actual largest contributor and easy
  to overlook in a manual `du` pass.

## Reference

- `linux-process-management` — `/proc`, cgroups, and OOM mechanics in full depth
- `linux-filesystem` — the complete disk-full decision tree and permission model
- `linux-performance-analysis` — the broader USE-method resource triage this fits into

## When NOT to use

- **Kubernetes eviction / OOMKill** — use K8s resource metrics and pod events, not host-level tools.
- **Application memory leaks** (heap profiling, GC analysis) — use language-specific profilers or Pyroscope.
- **Network storage latency** (EBS, NFS) — those are I/O issues but require cloud-specific diagnosis.

## Related skills

- [linux-performance-analysis](../linux/linux-performance-analysis/SKILL.md) — broader perf toolkit (CPU, scheduler, IO).
- [linux-filesystem](../linux/linux-filesystem/SKILL.md) — permissions, mounts, inodes.
- [log-analysis](../troubleshooting/log-analysis/SKILL.md) — finding OOM/disk errors in system logs.
- [incident-triage-linux](../troubleshooting/incident-triage-linux/SKILL.md) — when disk/memory triggers an outage.
