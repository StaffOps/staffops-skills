# The /proc Filesystem

`/proc` is a kernel-generated view of the running system. Files are produced
on read, so `cat` always shows current state and sizes are meaningless.

## Per-process entries

Everything below lives under `/proc/<pid>/`. Reading another user's entries
requires root.

| Entry | Contents |
| --- | --- |
| `cmdline` | Argument vector, NUL-separated |
| `comm` | Short process name (max 15 chars, what `ps` shows in `COMMAND`) |
| `environ` | Environment **as the process was launched**, NUL-separated |
| `exe` | Symlink to the executable |
| `cwd` | Symlink to the current working directory |
| `root` | Symlink to the process's root (differs under chroot/containers) |
| `fd/` | One symlink per open descriptor |
| `fdinfo/` | Per-descriptor position and flags |
| `status` | Human-readable state, memory, UIDs, capabilities |
| `stat` | The same data, machine-readable single line |
| `statm` | Memory in pages |
| `smaps` | Per-mapping memory detail |
| `smaps_rollup` | Aggregated `smaps` — much cheaper to read |
| `limits` | Effective soft and hard limits |
| `io` | Bytes and syscalls, read and written |
| `wchan` | Kernel function the process is sleeping in |
| `stack` | Kernel stack trace (root) |
| `cgroup` | cgroup membership |
| `oom_score` / `oom_score_adj` | OOM killer weighting |
| `task/` | One subdirectory per thread |
| `net/` | Network stack **as seen from this process's namespace** |

### Reading NUL-separated files

```bash
tr '\0' ' ' < /proc/1234/cmdline; echo
tr '\0' '\n' < /proc/1234/environ
xargs -0 printf '%s\n' < /proc/1234/cmdline
```

`environ` is a snapshot from `execve` time. A variable exported into the
process later by other means will not appear, and changing it there is
impossible.

### Key fields in `status`

```bash
grep -E 'Name|State|PPid|Uid|Gid|Threads|VmRSS|RssAnon|RssFile|VmSwap' /proc/1234/status
```

| Field | Meaning |
| --- | --- |
| `State` | Same codes as `ps` (`R`, `S`, `D`, `Z`, `T`) |
| `PPid` | Parent PID — `1` means it was reparented (its parent died) |
| `Uid` / `Gid` | Real, effective, saved, filesystem IDs |
| `Threads` | Thread count |
| `VmSize` | Virtual address space — not physical memory |
| `VmRSS` | Resident set: `RssAnon + RssFile + RssShmem` |
| `RssAnon` | Heap and stack — **the number that matters for OOM** |
| `RssFile` | Page cache mappings — reclaimable |
| `VmSwap` | Swapped out |
| `voluntary_ctxt_switches` | Yielded (waiting on I/O or a lock) |
| `nonvoluntary_ctxt_switches` | Preempted (CPU contention) |

A high **nonvoluntary** switch count means the process is fighting for CPU; a
high **voluntary** count means it is waiting on something.

### Memory detail

```bash
cat /proc/1234/smaps_rollup           # totals, one cheap read
awk '/^Rss/ { s += $2 } END { print s " kB" }' /proc/1234/smaps
grep -A2 heap /proc/1234/smaps        # heap mapping only
pmap -x 1234                          # friendlier mapping view
```

Prefer `smaps_rollup` in monitoring — parsing full `smaps` on a process with
thousands of mappings is expensive enough to distort what you are measuring.

### I/O

```bash
cat /proc/1234/io
```

| Field | Meaning |
| --- | --- |
| `rchar` / `wchar` | Bytes through read/write syscalls (may be cache hits) |
| `syscr` / `syscw` | Syscall counts |
| `read_bytes` / `write_bytes` | Bytes actually going to the block device |
| `cancelled_write_bytes` | Written then truncated before flush |

The gap between `wchar` and `write_bytes` is absorbed by the page cache. If
`read_bytes` is near zero while `rchar` is large, the workload is served from
cache.

### File descriptors

```bash
ls -l /proc/1234/fd/                      # what each fd points to
ls /proc/1234/fd | wc -l                  # current count
grep 'Max open files' /proc/1234/limits   # the limit it is measured against
```

Sockets and pipes appear as `socket:[12345]` and `pipe:[12345]`; correlate the
inode with `ss -tanp` output. Steadily growing counts indicate a descriptor
leak — the precursor to `EMFILE` / "Too many open files".

## System-wide entries

| Path | Contents |
| --- | --- |
| `/proc/cpuinfo` | Per-core CPU details |
| `/proc/meminfo` | System memory breakdown |
| `/proc/loadavg` | Load averages, running/total tasks, last PID |
| `/proc/uptime` | Uptime and cumulative idle seconds |
| `/proc/stat` | Cumulative CPU counters since boot |
| `/proc/vmstat` | Virtual memory event counters |
| `/proc/diskstats` | Per-device I/O counters |
| `/proc/net/dev` | Per-interface byte and packet counters |
| `/proc/net/tcp` | TCP sockets (hex; prefer `ss`) |
| `/proc/mounts` | Active mounts (authoritative, unlike `/etc/mtab`) |
| `/proc/swaps` | Swap devices in use |
| `/proc/pressure/{cpu,memory,io}` | PSI stall metrics |
| `/proc/sys/` | Tunables, same tree as `sysctl` |

### meminfo

```bash
grep -E 'MemTotal|MemFree|MemAvailable|Buffers|^Cached|Dirty|Writeback|Slab' /proc/meminfo
```

**`MemAvailable` is the number to use** — it estimates what a new workload can
get, accounting for reclaimable cache. `MemFree` looks alarmingly low on a
healthy system because Linux uses free RAM for page cache by design.

A large and growing `Dirty` means writeback is not keeping up with the storage
device.

### Pressure Stall Information

```bash
cat /proc/pressure/cpu
cat /proc/pressure/memory
cat /proc/pressure/io
```

```
some avg10=1.23 avg60=0.95 avg300=0.40 total=123456789
full avg10=0.10 avg60=0.05 avg300=0.02 total=9876543
```

- `some` — at least one task was stalled waiting for the resource.
- `full` — **every** runnable task was stalled; nothing productive happened.

PSI is a far better saturation signal than load average, because it measures
time lost to contention directly. Sustained `some avg10` above ~10 on memory
or io indicates real pressure. Per-cgroup PSI exists at
`/sys/fs/cgroup/<path>/{cpu,memory,io}.pressure`.

### Load average

```bash
cat /proc/loadavg
# 0.52 0.58 0.59 2/1234 56789
```

Fields: 1/5/15-minute averages, running/total tasks, last PID.

On Linux, load includes tasks in **uninterruptible sleep (`D`)**, not just
runnable ones. A machine with load 50 and idle CPUs is blocked on I/O, not
short of CPU. This is why load average alone is a poor CPU metric — use PSI or
`vmstat`'s `r` column.

## Namespaces

```bash
ls -l /proc/1234/ns/
readlink /proc/1234/ns/net
```

Two processes sharing a namespace inode are in the same namespace. Comparing
`/proc/1/ns/net` with `/proc/<pid>/ns/net` tells you whether a process is in
the host network namespace or a container's.

```bash
nsenter -t 1234 -n ss -tlnp        # run ss inside that process's netns
nsenter -t 1234 -m -p -- ls /      # enter mount and PID namespaces
```

`nsenter` is how you debug a container that has no shell or no tooling: run
the host's binaries inside the container's namespaces.

## Useful one-liners

```bash
# Top 10 by RSS, without ps.
for p in /proc/[0-9]*; do
    printf '%s %s\n' "$(awk '/VmRSS/ {print $2}' "$p/status" 2>/dev/null)" "${p##*/}"
done | sort -rn | head

# Every process in D state, with the kernel function it is blocked in.
for p in /proc/[0-9]*; do
    read -r _ comm state _ < "$p/stat" 2>/dev/null || continue
    [[ "$state" == D ]] && printf '%s %s %s\n' "${p##*/}" "$comm" "$(cat "$p/wchan")"
done

# Processes running a deleted binary (need a restart after an upgrade).
ls -l /proc/*/exe 2>/dev/null | grep deleted

# Descriptor counts, highest first.
for p in /proc/[0-9]*; do
    printf '%s %s\n' "$(ls "$p/fd" 2>/dev/null | wc -l)" "${p##*/}"
done | sort -rn | head

# Which cgroup every container process belongs to.
grep -H '' /proc/*/cgroup 2>/dev/null | grep docker | head
```

## Caveats

- Reading `/proc` is not atomic. A PID can be reused between two reads; verify
  with `starttime` from `/proc/<pid>/stat` if precision matters.
- `/proc/<pid>/stack` and other root-only entries return `EPERM` otherwise.
- Inside a container, `/proc/meminfo` and `/proc/cpuinfo` usually show **host**
  values unless `lxcfs` is present. Read cgroup files for container limits.
- `/proc/net/*` reflects the reading process's network namespace.
- Parsing `/proc/<pid>/stat` by whitespace breaks when `comm` contains spaces
  or parentheses; split on the last `)` instead.
