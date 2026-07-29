---
name: linux-performance-analysis
description: "Diagnose CPU, memory, disk and network bottlenecks."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [performance, cpu, memory, iostat, vmstat, perf, load-average, psi]
    category: linux
    related_skills: [linux-process-management, linux-filesystem]
---
# Linux Performance Analysis

A systematic way to find which resource is actually the bottleneck — CPU,
memory, disk, or network — before reaching for a fix. Built around the USE
method (Utilization, Saturation, Errors) and the small set of tools that
answer each question quickly.

## When to Use

Use when a system feels slow and it's unclear why, when triaging "high load"
alerts, before scaling a service (to know which resource to scale), or when
validating that a fix actually resolved the bottleneck.

## The USE method

For every resource, ask three questions:

| Question | What it reveals |
| --- | --- |
| **Utilization** | How busy is it? (% time doing work) |
| **Saturation** | Is work queued waiting for it? |
| **Errors** | Are operations failing? |

High utilization alone is not a problem — a CPU at 100% doing useful work is
fine. **Saturation** is the signal that something is actually bottlenecked:
work is queued because the resource can't keep up.

## First 60 seconds

```bash
uptime                    # load average
vmstat 1 5                # CPU, memory, swap, I/O in one view, 5 samples
mpstat -P ALL 1 3         # per-CPU breakdown (is it one core, or all?)
free -h                   # memory and swap
iostat -xz 1 3            # per-disk utilization and queue depth
ss -s                     # socket summary
dmesg -T | tail -20       # anything the kernel logged (OOM, disk errors)
```

This sequence usually narrows the problem to one resource within a minute,
before opening any single-purpose tool.

## CPU

```bash
top                       # interactive; press 1 for per-core
mpstat -P ALL 1            # per-core %usr/%sys/%iowait/%steal
vmstat 1                   # `r` column: processes runnable, not just running
pidstat -u 1               # per-process CPU over time
```

The `r` column in `vmstat` is the queue length — runnable processes waiting
for a CPU. `r` consistently higher than the core count means genuine CPU
saturation, not just busy cores.

| `%` column | Meaning |
| --- | --- |
| `us` | User time — application code |
| `sy` | System time — kernel, syscalls |
| `wa` | Waiting on I/O (counted as idle CPU, not busy — but signals a *different* bottleneck) |
| `st` | Stolen by the hypervisor — a noisy-neighbor signal on shared cloud instances |
| `id` | Truly idle |

High `%steal` on a VM means other tenants are consuming the physical CPU;
no amount of tuning your own process fixes it — it needs a different
instance type or host.

**Load average** includes processes in uninterruptible I/O wait (`D` state),
not just CPU-runnable ones. High load with idle CPUs almost always means I/O
or lock contention, not a CPU shortage — check `iostat` and process states
before assuming more CPU will help.

## Memory

```bash
free -h
vmstat 1                  # `si`/`so` columns: swap in/out
cat /proc/meminfo | grep -E 'MemAvailable|Dirty|Writeback'
ps -eo rss,pid,cmd --sort=-rss | head -10
smem -tk 2>/dev/null       # accounts for shared memory correctly, if installed
```

**`MemAvailable`, not `MemFree`, is the number that matters.** Linux uses
spare RAM for page cache by design — a low `MemFree` with a healthy
`MemAvailable` is normal and not a problem. `free -h`'s `available` column is
the same estimate.

Any `si`/`so` (swap in/out) activity in `vmstat` under normal load is a
red flag — swapping is orders of magnitude slower than RAM and usually
means the workload has outgrown its memory budget. A small amount of used
swap with zero *activity* is harmless; it is the ongoing traffic that hurts.

## Disk / I/O

```bash
iostat -xz 1               # -x extended, -z skip idle devices
iotop -o                   # per-process I/O, only active processes
lsblk
df -h; df -i
```

Key `iostat -x` columns:

| Column | Meaning |
| --- | --- |
| `%util` | Percentage of time the device had an I/O in flight |
| `await` | Average time per I/O request, queue included (ms) |
| `svctm` | Device service time (deprecated in recent iostat, unreliable) |
| `avgqu-sz` / `aqu-sz` | Average queue depth |
| `r/s`, `w/s` | Reads/writes per second |

`%util` near 100% with high `await` is saturation — the device cannot keep
up. `%util` near 100% with **low** `await` can be normal for a single fast
NVMe device doing sequential work; the interpretation depends on the device.
A queue depth (`aqu-sz`) consistently above 1 means requests are queuing.

Distinguish disk I/O from network-backed storage (NFS, EBS, a network
filesystem): the same symptoms (high `await`, processes in `D` state) can
originate on the network path instead, so also check for saturation there
before concluding it's the local disk.

## Network

```bash
ss -tunap                  # sockets with process ownership
ss -s                       # summary counts
ip -s link show eth0        # errors/drops per interface
sar -n DEV 1                # throughput per interface over time
ethtool -S eth0 | grep -i drop  # driver-level drop counters
```

Watch the error and drop counters specifically — a link running well below
its bandwidth cap but with rising drops points at a different problem
(buffer exhaustion, a duplex mismatch, a saturated upstream link) than pure
throughput would suggest.

```bash
ss -tn state established | wc -l    # connection count, a scaling limit in itself
cat /proc/net/sockstat               # socket usage vs system limits
```

## Pressure Stall Information (PSI)

The most direct saturation signal available on modern kernels (5.2+) — it
measures time actually lost to contention, per resource:

```bash
cat /proc/pressure/cpu
cat /proc/pressure/memory
cat /proc/pressure/io
```

```
some avg10=2.15 avg60=1.80 avg300=0.95 total=182933841
full avg10=0.30 avg60=0.20 avg300=0.05 total=8391029
```

- `some` — at least one task was stalled on this resource.
- `full` — **every** runnable task was stalled; the whole system made zero
  progress on anything else during that time.

Sustained `some avg10` in the low double digits or higher on memory or I/O
is a real, current bottleneck — more reliable than load average, because it
isolates which resource is actually causing the stall.

## perf — when the bottleneck is inside the code

```bash
perf top                              # live view of hottest functions, system-wide
perf record -F 99 -p <pid> -g -- sleep 30
perf report                            # analyze the recording
perf stat -p <pid> sleep 10            # instructions, cache misses, branch mispredicts
```

`perf top`/`perf record -g` (call graph) is what turns "CPU is at 100%" into
"80% of that CPU is spent in this one function" — the next step after the
USE method identifies CPU as the resource, when the fix requires knowing
*which code path*.

Requires `CAP_PERFMON` or root, and on some hardened kernels
`/proc/sys/kernel/perf_event_paranoid` must be lowered.

## Putting it together: a decision flow

```
High load, unclear cause
│
├─ vmstat: high `r`, CPU %us/%sy high, low %wa → CPU-bound
│   └─ perf top / perf record -g → find the hot function
│
├─ vmstat: high `r`, CPU %wa high → I/O-bound
│   └─ iostat -x → which device, %util and await
│
├─ free: MemAvailable low, vmstat si/so active → memory-bound
│   └─ ps --sort=-rss → which process; check for a leak over time
│
├─ load high but ALL CPUs idle → processes in D state
│   └─ ps -eo stat,wchan,cmd | grep ^D → what they're blocked on
│
└─ throughput low despite idle CPU/disk → network-bound
    └─ ss -s, ip -s link → error/drop counters, connection counts
```

## Pitfalls

- **Reading `%util` in `iostat` as "disk is the bottleneck"** without also
  checking `await` — a busy-but-fast device is not saturated.
- **Alerting on load average alone** — it conflates CPU and I/O wait; check
  which one before acting.
- **Treating `MemFree` as available memory** — page cache is meant to be
  reclaimed; use `MemAvailable`.
- **Chasing CPU% without `perf`** — knowing CPU is the bottleneck doesn't
  say *why*; profiling does.
- **Ignoring `%steal`** — on a VM, this is an infrastructure problem, not
  something application tuning fixes.
- **Comparing `iostat` numbers across different disk types** — an NVMe and a
  network-backed volume have very different normal `await` baselines.

## Verification

```bash
vmstat 1 5                  # confirm the resource, before AND after a fix
iostat -xz 1 3
cat /proc/pressure/{cpu,memory,io}
perf stat -p <pid> sleep 10 # compare instructions/cycles before and after
```

Always take a "before" measurement — without it, "the fix worked" is a
guess rather than a comparison.

## Reference

- `linux-process-management` — per-process `/proc` detail, cgroup limits
- `linux-filesystem` — disk space and inode exhaustion specifically
