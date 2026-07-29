# Unit Directive Reference

Verified against systemd 255 (Ubuntu 24.04). Directives are grouped by
section; putting one in the wrong section is a silent no-op that
`systemd-analyze verify` reports as "Unknown key name", not a hard error —
always run `verify` after editing a unit.

## [Unit] — present in every unit type

| Directive | Meaning |
| --- | --- |
| `Description=` | Shown in `status` and logs |
| `Documentation=` | URI(s), shown in `status` |
| `After=` / `Before=` | Ordering only |
| `Requires=` | Hard dependency — this unit fails if that one does |
| `Wants=` | Soft dependency — failure tolerated |
| `BindsTo=` | Hard dependency that also stops this unit when that one stops |
| `PartOf=` | Propagates stop/restart, not start |
| `Conflicts=` | Mutually exclusive units |
| `Condition*=` | Skip (not fail) if false — e.g. `ConditionPathExists=` |
| `Assert*=` | Fail (not skip) if false |
| `StartLimitIntervalSec=` | Window for counting restart attempts |
| `StartLimitBurst=` | Restarts allowed within that window before giving up |
| `OnFailure=` | Unit(s) to start when this one fails |
| `RefuseManualStart=` / `RefuseManualStop=` | Block `systemctl start/stop` |

`StartLimit*` lives here, not in `[Service]` — the most common misplacement.

## [Service]

### Process

| Directive | Meaning |
| --- | --- |
| `Type=` | `simple`, `exec`, `forking`, `oneshot`, `notify`, `dbus` |
| `ExecStartPre=` / `ExecStartPost=` | Run before/after the main start |
| `ExecStart=` | The main command; repeat for `oneshot` to run several |
| `ExecReload=` | Command for `systemctl reload` |
| `ExecStop=` | Custom stop command (rarely needed — `KillSignal` usually suffices) |
| `ExecStopPost=` | Runs even if the start failed |
| `RemainAfterExit=` | For `oneshot`: stay "active" after the process exits |
| `PIDFile=` | Required for `Type=forking` |
| `WorkingDirectory=` | cwd for all `Exec*` |
| `User=` / `Group=` | Drop privileges |
| `UMask=` | Default file creation mask |

An `ExecStart=` prefixed with `-` tolerates a non-zero exit; `+` runs with
full privileges even if `User=` is set (rare, used for a setup step).

### Restart

| Directive | Meaning |
| --- | --- |
| `Restart=` | `no`, `on-success`, `on-failure`, `on-abnormal`, `on-abort`, `on-watchdog`, `always` |
| `RestartSec=` | Delay before restarting |
| `RestartPreventExitStatus=` | Exit codes that suppress restart even under `Restart=always` |
| `SuccessExitStatus=` | Additional codes/signals treated as success |

### Timeouts and watchdog

| Directive | Meaning |
| --- | --- |
| `TimeoutStartSec=` | Max time to reach "started" |
| `TimeoutStopSec=` | Max time to stop before `SIGKILL` |
| `TimeoutSec=` | Sets both at once |
| `WatchdogSec=` | App must `sd_notify(WATCHDOG=1)` within this interval |
| `KillMode=` | `control-group` (default), `process`, `mixed`, `none` |
| `KillSignal=` | Default `SIGTERM` |
| `FinalKillSignal=` | Sent after `TimeoutStopSec` if still alive; default `SIGKILL` |

`KillMode=control-group` sends the signal to every process in the unit's
cgroup — this is what lets systemd reliably clean up a process that forked
children the way `Restart=` alone cannot.

### Resource control (cgroup v2)

| Directive | cgroup file |
| --- | --- |
| `MemoryMax=` | `memory.max` — hard limit, triggers OOM kill |
| `MemoryHigh=` | `memory.high` — soft limit, throttles and reclaims |
| `MemoryMin=` / `MemoryLow=` | `memory.min` / `memory.low` — reclaim protection |
| `CPUQuota=` | `cpu.max` — e.g. `200%` = 2 cores |
| `CPUWeight=` | `cpu.weight` — relative share, 1-10000 |
| `TasksMax=` | `pids.max` — fork-bomb guard |
| `IOWeight=` | `io.weight` |
| `IOReadBandwidthMax=` / `IOWriteBandwidthMax=` | `io.max` |
| `OOMScoreAdjust=` | `/proc/<pid>/oom_score_adj` — not a cgroup file |
| `OOMPolicy=` | What happens to the unit when a member is OOM-killed |

See the `linux-process-management` skill for the underlying cgroup mechanics.

### Sandboxing

| Directive | Effect |
| --- | --- |
| `NoNewPrivileges=` | Blocks privilege escalation via `execve` |
| `PrivateTmp=` | Private `/tmp`, `/var/tmp` |
| `PrivateDevices=` | Minimal `/dev`, no raw device access |
| `PrivateNetwork=` | Own network namespace (loopback only) |
| `ProtectSystem=` | `true` (`/usr`, `/boot` read-only), `full` (+`/etc`), `strict` (everything) |
| `ProtectHome=` | `true`, `false`, or `read-only` |
| `ProtectKernelTunables=` | `/proc/sys`, `/sys` read-only |
| `ProtectKernelModules=` | Blocks module loading |
| `ProtectControlGroups=` | cgroup filesystem read-only |
| `ProtectClock=` | Blocks changing the system clock |
| `RestrictAddressFamilies=` | Allowlist, e.g. `AF_INET AF_INET6 AF_UNIX` |
| `RestrictNamespaces=` | Blocks creating new namespaces |
| `RestrictRealtime=` | Blocks realtime scheduling |
| `SystemCallFilter=` | Seccomp allow/deny list, e.g. `@system-service` |
| `CapabilityBoundingSet=` | Restrict available capabilities |
| `ReadOnlyPaths=` / `ReadWritePaths=` / `InaccessiblePaths=` | Fine-grained filesystem exceptions |
| `IPAddressAllow=` / `IPAddressDeny=` | Network-layer allow/deny list |

`systemd-analyze security UNIT` scores a unit and lists exactly which of
these to add next — use it instead of guessing.

### Environment and credentials

| Directive | Meaning |
| --- | --- |
| `Environment=` | `KEY=VALUE`, repeatable |
| `EnvironmentFile=` | Load from a file; prefix `-` makes it optional |
| `LoadCredential=` | `name:path` — exposed under `$CREDENTIALS_DIRECTORY`, root-owned, torn down at stop |
| `SetCredential=` | Inline credential value |
| `PassEnvironment=` | Pass specific variables from the manager's own environment |

## [Install]

| Directive | Meaning |
| --- | --- |
| `WantedBy=` | Target(s) that pull this unit in; creates the `enable` symlink |
| `RequiredBy=` | Same, but as a hard dependency |
| `Also=` | Additional units to enable/disable together |
| `Alias=` | Alternate name(s) |

`[Install]` only matters to `systemctl enable`/`disable`; it has no effect on
`start`/`stop`.

## [Timer]

| Directive | Meaning |
| --- | --- |
| `OnCalendar=` | Systemd calendar expression |
| `OnBootSec=` / `OnStartupSec=` | Relative to boot / manager start |
| `OnActiveSec=` | Relative to the timer's own activation |
| `OnUnitActiveSec=` / `OnUnitInactiveSec=` | Relative to the triggered unit's last transition |
| `Persistent=` | Catch up a missed run after downtime |
| `RandomizedDelaySec=` | Jitter, to avoid a thundering herd |
| `AccuracySec=` | Batching window (default 1 min) — coarser saves wakeups |
| `Unit=` | Override which unit to trigger (default: same basename `.service`) |

## Special variables available in Exec lines

| Variable | Expands to |
| --- | --- |
| `%n` | Full unit name |
| `%N` | Unit name, unescaped |
| `%i` | Instance name (template units, `name@instance.service`) |
| `%t` | Runtime directory (`/run`, or `$XDG_RUNTIME_DIR` for `--user`) |
| `%h` | User's home directory |
| `%d` | Credentials directory (with `LoadCredential=`) |
| `$MAINPID` | PID of the main process, for `ExecReload=`/`ExecStop=` |

## Verifying section placement

When unsure which section a directive belongs to:

```bash
man systemd.unit      # [Unit] and [Install] — common to every unit type
man systemd.service   # [Service]
man systemd.timer     # [Timer]
man systemd.exec      # Exec*, sandboxing, resource control (shared)
man systemd.resource-control   # cgroup directives specifically
systemd-analyze verify unit.service   # catches misplacement immediately
```

`systemd-analyze verify` is authoritative and costs nothing to run — prefer
it over recalling the table from memory when precision matters.
