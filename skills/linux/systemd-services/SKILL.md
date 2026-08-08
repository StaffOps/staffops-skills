---
name: systemd-services
description: "Write, debug and manage systemd units and timers."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [systemd, systemctl, journalctl, unit, timer, service, cgroup]
    category: linux
    related_skills: [linux-process-management, linux-filesystem]
---
# systemd Services

Writing unit files that restart correctly, debugging one that will not start,
and reading `journalctl` output that actually explains the failure. Covers
service units, timers as a cron replacement, and the resource controls that
map directly onto the cgroups described in `linux-process-management`.

## When to Use

Use when packaging a daemon as a service, debugging why a unit failed to
start or keeps restarting, replacing a cron job with a timer, or setting
memory/CPU limits on a service.

## Anatomy of a service unit

```ini
# /etc/systemd/system/myapp.service
[Unit]
Description=My Application
Documentation=https://example.com/docs
After=network-online.target postgresql.service
Wants=network-online.target
Requires=postgresql.service
# StartLimit* belongs here, in [Unit] -- NOT in [Service]. Putting it in
# [Service] is a common mistake that systemd silently ignores rather than
# rejecting; `systemd-analyze verify` reports it as "Unknown key name".
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=notify
User=myapp
Group=myapp
WorkingDirectory=/opt/myapp
ExecStartPre=/opt/myapp/bin/check-config.sh
ExecStart=/opt/myapp/bin/server --config /etc/myapp/config.yaml
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=2
TimeoutStartSec=30
TimeoutStopSec=15

# Resource control -- maps to cgroup v2 controllers.
MemoryMax=1G
MemoryHigh=900M
CPUQuota=150%
TasksMax=256

# Hardening.
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/myapp

[Install]
WantedBy=multi-user.target
```

## [Unit] section — dependencies

| Directive | Effect |
| --- | --- |
| `After=` / `Before=` | Ordering only — does **not** imply a dependency |
| `Requires=` | Hard dependency; this unit fails if that one fails |
| `Wants=` | Soft dependency; failure is tolerated |
| `BindsTo=` | Like `Requires=`, but also **stops** this unit when that one stops |
| `Conflicts=` | Mutually exclusive; starting one stops the other |
| `PartOf=` | Propagates stop/restart, not start |

**`After=` without `Requires=`/`Wants=` only orders, it does not pull the
dependency in.** A unit with `After=postgresql.service` but no `Requires=`
will start even if PostgreSQL is not enabled — it just waits its turn if
PostgreSQL happens to also be starting.

`network-online.target` needs `Wants=` **and** `After=` together; the target
itself does nothing without a provider like `systemd-networkd-wait-online` or
`NetworkManager-wait-online` enabled.

## [Service] section — Type

| Type | Meaning | Use when |
| --- | --- | --- |
| `simple` (default) | The `ExecStart` process **is** the service | Foreground process, no daemonizing |
| `exec` | Like `simple`, but waits for the exec syscall itself to succeed | Same, with earlier failure detection |
| `forking` | The process forks and the parent exits; needs `PIDFile=` | Traditional daemons |
| `oneshot` | Runs to completion, then exits; pairs with `RemainAfterExit=` | Setup scripts, one-off tasks |
| `notify` | Waits for `sdnotify` `READY=1` before considering it started | Well-behaved modern daemons |
| `dbus` | Waits for a D-Bus name to appear | Historical |

Getting `Type` wrong is the single most common cause of "the service says
active but is not actually ready" — with `simple`, systemd considers the unit
started the instant the process exists, not when it can serve traffic. Use
`notify` and have the application call `sd_notify(READY=1)`, or use
`ExecStartPost=` with a readiness check.

## Restart behavior

```ini
[Service]
Restart=on-failure       # not on: success, SIGTERM/SIGINT, or manual stop
RestartSec=2

[Unit]
StartLimitIntervalSec=60   # these two belong in [Unit], not [Service]
StartLimitBurst=5
```

| Value | Restarts after |
| --- | --- |
| `no` (default) | Never |
| `on-failure` | Non-zero exit, signal, timeout, or watchdog |
| `on-abnormal` | Signal, timeout, or watchdog — not a plain non-zero exit |
| `on-abort` | Only an uncaught signal |
| `always` | Everything, including a clean exit and manual `systemctl stop` |

`always` is rarely correct — it also restarts after an intentional `systemctl
stop`, which then requires `systemctl stop` twice or fights the operator.
`on-failure` is the right default for almost every service.

`StartLimitBurst`/`StartLimitIntervalSec` is a circuit breaker: after 5
restarts in 60 seconds the unit enters `failed` state and **stops retrying**.
Without it, a crash-looping process restarts forever, burning CPU and filling
the journal.

```bash
systemctl reset-failed myapp.service      # clear the counter and try again
```

## Sandboxing directives

These cost nothing to add and meaningfully reduce blast radius:

| Directive | Effect |
| --- | --- |
| `NoNewPrivileges=true` | Blocks setuid/capability escalation via `execve` |
| `PrivateTmp=true` | Private `/tmp` and `/var/tmp` |
| `ProtectSystem=strict` | Entire filesystem read-only except what's listed in `ReadWritePaths=` |
| `ProtectHome=true` | `/home`, `/root`, `/run/user` inaccessible |
| `ProtectKernelTunables=true` | `/proc/sys`, `/sys` read-only |
| `ProtectControlGroups=true` | cgroup filesystem read-only |
| `RestrictAddressFamilies=` | Limit to e.g. `AF_INET AF_INET6 AF_UNIX` |
| `SystemCallFilter=` | Seccomp allowlist, e.g. `@system-service` |
| `ReadWritePaths=` | Explicit exception under `ProtectSystem=strict` |

```bash
systemd-analyze security myapp.service    # score + specific recommendations
```

Start from the score output — it tells you exactly which directive to add
next, ranked by impact.

## Timers — a cron replacement

```ini
# /etc/systemd/system/backup.timer
[Unit]
Description=Run backup nightly

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
```

```ini
# /etc/systemd/system/backup.service
[Unit]
Description=Backup job

[Service]
Type=oneshot
ExecStart=/opt/scripts/backup.sh
```

The timer and the service are separate units sharing a basename; the timer
triggers the like-named `.service`. Enable and start the **timer**, not the
service:

```bash
systemctl enable --now backup.timer
systemctl list-timers                 # next run, last run, unit
```

Advantages over cron: `Persistent=true` catches up a missed run after the
machine was off (cron silently skips it), output goes to the journal
automatically, dependencies and resource limits from `[Service]` apply, and
`RandomizedDelaySec` avoids a thundering herd across a fleet.

```
OnCalendar=*-*-* *:00:00      # hourly
OnCalendar=Mon..Fri 09:00     # weekdays at 9am
OnCalendar=weekly
OnBootSec=5min                # 5 minutes after boot
OnUnitActiveSec=1h            # 1 hour after the service last activated
```

```bash
systemd-analyze calendar 'Mon..Fri 09:00'   # verify a calendar expression
```

## Debugging a unit that will not start

```bash
systemctl status myapp.service           # state, recent log lines, cgroup
systemctl show myapp.service              # every property, unabbreviated
journalctl -u myapp.service                # this unit's log
journalctl -u myapp.service -b             # since the last boot only
journalctl -u myapp.service -f             # follow live
journalctl -u myapp.service -p err         # errors and above only
journalctl -u myapp.service --since "10 min ago"
systemd-analyze verify myapp.service       # STATIC check: syntax and references
systemctl cat myapp.service                # the effective unit, including drop-ins
```

`systemd-analyze verify` catches typos, missing `ExecStart=`, and bad
directives **before** attempting to start the unit — always run it after
editing a unit file.

```bash
systemctl daemon-reload      # required after ANY unit file edit
systemctl restart myapp.service
```

Forgetting `daemon-reload` is extremely common: `systemctl status` still shows
the *old* unit content even though the file on disk changed, so the fix
appears not to have worked.

### Reading `status` output

```
● myapp.service - My Application
     Loaded: loaded (/etc/systemd/system/myapp.service; enabled)
     Active: failed (Result: exit-code) since ...; 3s ago
    Process: 1234 ExecStart=/opt/myapp/bin/server (code=exited, status=1/FAILURE)
   Main PID: 1234 (code=exited, status=1/FAILURE)
```

| `Result:` | Meaning |
| --- | --- |
| `exit-code` | The process exited non-zero |
| `signal` | Killed by a signal |
| `timeout` | Exceeded `TimeoutStartSec` / `TimeoutStopSec` |
| `oom-kill` | The cgroup's `MemoryMax` was exceeded |
| `watchdog` | Missed an `sd_notify` watchdog ping |
| `start-limit-hit` | `StartLimitBurst` exhausted — see `reset-failed` |

`oom-kill` here means the service's own `MemoryMax` — this is a self-inflicted
resource limit, not a system-wide OOM. Raise the limit or fix the leak.

## Drop-ins — overriding a unit without editing it

```bash
systemctl edit myapp.service
```

Opens an editor on `/etc/systemd/system/myapp.service.d/override.conf`,
creating the directory if needed. This is the correct way to customize a
vendor-shipped unit — the override survives package upgrades, whereas editing
the shipped file gets clobbered.

```ini
# /etc/systemd/system/myapp.service.d/override.conf
[Service]
MemoryMax=2G
Environment=LOG_LEVEL=debug
```

`Environment=` in a drop-in **adds** to the parent unit; it does not replace
it. To clear an inherited `ExecStart=` before setting a new one:

```ini
[Service]
ExecStart=
ExecStart=/opt/myapp/bin/server --new-flag
```

The empty `ExecStart=` resets the list — without it, both commands run in
sequence.

```bash
systemctl edit --full myapp.service     # edit the whole unit, not a drop-in
systemctl cat myapp.service             # see the MERGED result: base + drop-ins
```

## Environment and secrets

```ini
[Service]
Environment=LOG_LEVEL=info
Environment=FEATURE_X=true
EnvironmentFile=/etc/myapp/env          # KEY=VALUE lines, no quoting/expansion
EnvironmentFile=-/etc/myapp/env.local   # leading '-': optional, no error if missing
```

For secrets, prefer `LoadCredential=` (systemd 246+) over an env file readable
by anyone who can `cat /proc/<pid>/environ`:

```ini
[Service]
LoadCredential=db-password:/etc/myapp/secrets/db-password
ExecStart=/opt/myapp/bin/server --password-file=%d/db-password
```

`%d` expands to the runtime credentials directory, which is only readable by
the service's own user and torn down when the unit stops.

## User services

Run as a normal user, without root, using `systemctl --user`:

```bash
systemctl --user enable --now myapp.service
loginctl enable-linger "$USER"      # keep it running after logout
journalctl --user -u myapp.service
```

Units live in `~/.config/systemd/user/`. Without `enable-linger`, the user's
systemd instance (and everything in it) stops when the last session for that
user ends.

## Pitfalls

- **Editing the unit file without `daemon-reload`** — systemd keeps using the
  cached copy; `status` output is misleadingly stale.
- **`After=` mistaken for a dependency** — pair it with `Requires=` or
  `Wants=` when the ordering must also be enforced.
- **`Restart=always`** — also fires after a deliberate `systemctl stop`.
- **No `StartLimitBurst`** — a crash loop restarts forever and floods the
  journal.
- **`Type=simple` for something that needs a readiness check** — traffic
  arrives before the app can serve it. Use `Type=notify`.
- **Editing a vendor unit directly** — lost on the next package upgrade. Use
  `systemctl edit`.
- **Secrets in `Environment=`** — visible to anyone reading
  `/proc/<pid>/environ` or `systemctl show`. Use `LoadCredential=`.
- **Assuming `enable` starts a unit** — it only wires up the boot symlink.
  Use `enable --now` or a separate `start`.
- **Forgetting `enable --now` on a timer, and instead enabling the `.service`**
  — the service will never fire on its own; the timer is what needs enabling.

## Verification

```bash
systemd-analyze verify myapp.service          # static check before starting
systemctl daemon-reload
systemctl restart myapp.service
systemctl is-active myapp.service             # exit 0 iff active
systemctl is-enabled myapp.service
systemctl status myapp.service --no-pager
journalctl -u myapp.service -n 50 --no-pager
systemd-analyze security myapp.service        # hardening score
systemd-analyze blame                         # slowest units at boot
systemd-analyze critical-chain myapp.service  # what it waited on to start
```

`scripts/unit-doctor.sh` runs a static-then-dynamic check sequence against a
unit and reports exactly where it fails.

## Reference

- `references/unit-directives.md` — directive tables by section, with defaults
- `references/journalctl-recipes.md` — practical `journalctl` query patterns
- `scripts/unit-doctor.sh` — verify, reload, start, and diagnose a unit
- `examples/webapp.service` — a complete hardened unit with resource limits
- `examples/webapp-backup.timer` — a timer/service pair with `Persistent=true`

## When NOT to use

- **Container orchestration** (Docker, Kubernetes) — systemd manages the host, not pods.
- **One-off commands or cron jobs** that don't need service lifecycle — a simple cron entry or systemd timer suffices.
- **Process internals** (signals, cgroups, scheduling) — see [linux-process-management](../linux/linux-process-management/SKILL.md).


## Decision tree

```
What's the situation?
├── Service won't start?
│   ├── Check logs → journalctl -u name.service -n 50 --no-pager
│   ├── Check unit file → systemd-analyze verify name.service
│   ├── Dependency issue → systemctl list-dependencies name.service
│   └── Permission denied → check User=, paths, SELinux/AppArmor
├── Service keeps restarting (crash loop)?
│   ├── Check exit code → systemctl status (Main PID ... code=exited, status=N)
│   ├── OOM killed → journalctl -k | grep -i oom; adjust MemoryMax=
│   ├── Too fast → add RestartSec=5, StartLimitIntervalSec/StartLimitBurst
│   └── Bad config → ExecStartPre= with config validation command
├── Create a new service?
│   ├── Long-running daemon → Type=notify (preferred) or Type=simple
│   ├── One-shot task → Type=oneshot + RemainAfterExit=yes
│   ├── Needs network → After=network-online.target + Wants=
│   └── Security → DynamicUser=yes, ProtectSystem=strict, NoNewPrivileges=yes
└── Reload without restart?
    └── ExecReload= defined → systemctl reload name.service
```

## Related skills

- [linux-process-management](../linux/linux-process-management/SKILL.md) — signals, ps, cgroups.
- [ubuntu-administration](../linux/ubuntu-administration/SKILL.md) — package management, system config.
- [log-analysis](../troubleshooting/log-analysis/SKILL.md) — reading journald output.
- [incident-triage-linux](../troubleshooting/incident-triage-linux/SKILL.md) — when a crashed service triggers an incident.
