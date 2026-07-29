# cgroups v2

Control groups bound and account for the resources a set of processes may use.
They are the mechanism behind container limits, systemd resource control, and
the per-container OOM killer.

## v1 vs v2

| | v1 | v2 |
| --- | --- | --- |
| Hierarchy | One per controller | **Single unified tree** |
| Mount point | `/sys/fs/cgroup/<controller>/` | `/sys/fs/cgroup/` |
| Memory limit file | `memory.limit_in_bytes` | `memory.max` |
| CPU limit | `cpu.cfs_quota_us` + period | `cpu.max` (both values) |
| Soft limit | `memory.soft_limit_in_bytes` (advisory) | `memory.high` (throttles) |
| PSI per cgroup | No | Yes |

Detect which is in use:

```bash
stat -fc %T /sys/fs/cgroup    # cgroup2fs = v2, tmpfs = v1 (or hybrid)
mount | grep cgroup
```

Modern distributions (Ubuntu 22.04+, RHEL 9+, Debian 11+) default to v2.

## Layout

```
/sys/fs/cgroup/
├── cgroup.controllers          controllers available here
├── cgroup.subtree_control      controllers delegated to children
├── system.slice/               systemd system services
│   └── nginx.service/
│       ├── cgroup.procs        PIDs in this cgroup
│       ├── memory.current
│       ├── memory.max
│       ├── memory.events
│       ├── cpu.stat
│       └── pids.current
├── user.slice/                 user sessions
└── init.scope/                 PID 1
```

Find a process's cgroup:

```bash
cat /proc/1234/cgroup
# 0::/system.slice/nginx.service
```

The `0::` prefix marks v2. Append the path to `/sys/fs/cgroup` to reach its
directory.

## Memory controller

| File | Meaning |
| --- | --- |
| `memory.current` | Bytes charged to this cgroup right now |
| `memory.max` | Hard limit — exceeding it triggers the cgroup OOM killer |
| `memory.high` | Soft limit — throttles allocation and forces reclaim |
| `memory.low` | Reclaim protection — best effort |
| `memory.min` | Reclaim protection — guaranteed |
| `memory.swap.max` | Swap limit |
| `memory.events` | Counters: `low`, `high`, `max`, `oom`, `oom_kill` |
| `memory.stat` | Detailed breakdown (anon, file, slab, ...) |
| `memory.pressure` | PSI for this cgroup |

```bash
cd /sys/fs/cgroup/system.slice/myapp.service
cat memory.current memory.max
cat memory.events
grep -E '^(anon|file|slab) ' memory.stat
```

`memory.events` is the authoritative answer to "was my container OOM-killed":

```
low 0
high 1523
max 12
oom 3
oom_kill 3
```

`oom_kill > 0` confirms it. A large and growing `high` count means the
workload is being throttled — it is alive but slow, which often presents as
latency rather than an obvious failure.

**`memory.high` is usually the better knob.** `max` kills; `high` applies
back-pressure and reclaims. Setting `high` slightly below `max` converts a
cliff into a warning band:

```ini
[Service]
MemoryHigh=1800M
MemoryMax=2G
```

## CPU controller

| File | Meaning |
| --- | --- |
| `cpu.max` | `QUOTA PERIOD` in microseconds; `max` means unlimited |
| `cpu.weight` | Relative share, 1-10000 (default 100) |
| `cpu.stat` | Usage and **throttling** counters |
| `cpu.pressure` | PSI |

```bash
cat cpu.max        # "200000 100000" = 2 CPUs
echo "50000 100000" > cpu.max   # 0.5 CPU
cat cpu.stat
```

`cpu.stat` throttling fields are what to alert on:

```
nr_periods 1000
nr_throttled 250        # periods where the quota ran out
throttled_usec 5000000  # time spent throttled
```

`nr_throttled / nr_periods` above a few percent means the quota is too low.
This is the single most common cause of unexplained latency in containers:
average CPU looks low, but the workload is repeatedly stopped at period
boundaries.

Prefer `cpu.weight` (shares) over `cpu.max` (hard quota) unless you genuinely
need a ceiling — weights allow bursting into idle capacity.

## PIDs and I/O

```bash
cat pids.current pids.max     # guard against fork bombs
cat io.max                    # per-device limits
cat io.stat                   # per-device counters
cat io.pressure
```

```
# io.max format: MAJ:MIN rbps=... wbps=... riops=... wiops=...
echo "8:0 wbps=10485760" > io.max     # 10 MB/s writes to device 8:0
```

I/O limits only work reliably on cgroup v2 with the `blk-mq` layer and a
direct block device — they do not apply cleanly to page-cache writeback.

## systemd mapping

Never write to `/sys/fs/cgroup` directly for a managed service: the change is
lost on restart and on reboot. Set properties on the unit instead.

| systemd directive | cgroup file |
| --- | --- |
| `MemoryMax=2G` | `memory.max` |
| `MemoryHigh=1800M` | `memory.high` |
| `MemoryMin=256M` | `memory.min` |
| `CPUQuota=200%` | `cpu.max` |
| `CPUWeight=100` | `cpu.weight` |
| `TasksMax=512` | `pids.max` |
| `IOWeight=50` | `io.weight` |
| `IOReadBandwidthMax=` | `io.max` |

```ini
[Service]
MemoryMax=2G
MemoryHigh=1800M
CPUQuota=200%
TasksMax=512
OOMScoreAdjust=-500
```

Apply without a restart:

```bash
systemctl set-property myapp.service MemoryMax=4G          # persistent
systemctl set-property --runtime myapp.service CPUQuota=50% # until reboot
systemctl show myapp -p MemoryMax -p MemoryCurrent -p CPUQuota
```

## Inspection

```bash
systemd-cgls                       # the tree with process names
systemd-cgtop                      # live per-cgroup resource use
systemd-cgtop -m --order=memory

# Every cgroup over 1 GiB.
find /sys/fs/cgroup -name memory.current -exec sh -c '
    v=$(cat "$1"); [ "$v" -gt 1073741824 ] && printf "%s %s\n" "$((v/1024/1024))MiB" "${1%/memory.current}"
' _ {} \; 2>/dev/null | sort -rn
```

## Containers

Docker and Kubernetes create cgroups per container:

```bash
# Docker
cat /sys/fs/cgroup/system.slice/docker-<id>.scope/memory.max

# Kubernetes (path varies with the cgroup driver)
find /sys/fs/cgroup/kubepods.slice -name memory.max | head
```

Kubernetes resource fields map directly:

| Kubernetes | cgroup |
| --- | --- |
| `resources.limits.memory` | `memory.max` |
| `resources.requests.memory` | `memory.min` (via QoS class) |
| `resources.limits.cpu` | `cpu.max` |
| `resources.requests.cpu` | `cpu.weight` |

A container exiting with **137** and `oom_kill` incrementing in
`memory.events` is a limit that is too low — or a genuine leak. Distinguish
them by whether `memory.current` climbs steadily between restarts.

Inside a container, `/proc/meminfo` shows **host** memory unless `lxcfs` is
mounted. Runtimes that read it will size their heap against the host and get
OOM-killed. Java 10+ and Go 1.19+ read cgroup limits correctly; older runtimes
need explicit flags (`-XX:MaxRAMPercentage`, `GOMEMLIMIT`).

## Delegation

For an unprivileged process to manage its own sub-cgroups:

```ini
[Service]
Delegate=yes
```

This is what lets rootless Podman and nested systemd work. Without it, writes
to child cgroup files are denied.
