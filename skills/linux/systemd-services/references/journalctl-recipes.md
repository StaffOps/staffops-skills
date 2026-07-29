# journalctl Recipes

`journalctl` reads the structured binary journal maintained by
`systemd-journald`. Every entry carries metadata (unit, PID, priority, boot
ID) that plain log files do not, which is what makes precise filtering
possible.

## Basic filtering

```bash
journalctl -u myapp.service              # this unit only
journalctl -u myapp.service -u nginx     # multiple units
journalctl -b                            # since the current boot
journalctl -b -1                         # the PREVIOUS boot
journalctl --list-boots                  # enumerate boots with their IDs
journalctl -k                            # kernel messages only (dmesg equivalent)
journalctl _PID=1234                     # by PID
journalctl _UID=1000                     # by UID
journalctl /usr/bin/myapp                # by executable path
```

## Time ranges

```bash
journalctl --since "2026-01-10 09:00:00"
journalctl --since "1 hour ago"
journalctl --since today
journalctl --since yesterday --until today
journalctl --since "-15min"
journalctl -u myapp.service --since "10 min ago" --until "5 min ago"
```

## Priority

```bash
journalctl -p err                    # this level AND above
journalctl -p warning..err           # a range
journalctl -u myapp.service -p err -b
```

| Level | Name |
| --- | --- |
| 0 | emerg |
| 1 | alert |
| 2 | crit |
| 3 | err |
| 4 | warning |
| 5 | notice |
| 6 | info |
| 7 | debug |

## Following (like `tail -f`)

```bash
journalctl -f                        # follow everything
journalctl -u myapp.service -f
journalctl -f -u myapp.service -o cat    # follow, message text only
journalctl -f --since now            # skip history, start from now
```

## Output formats

```bash
journalctl -o json                   # one JSON object per line
journalctl -o json-pretty            # human-readable JSON
journalctl -o cat                    # message text only, no metadata
journalctl -o short-iso              # ISO 8601 timestamps
journalctl -o verbose                # every field, including internal ones
journalctl -o json -u myapp.service | jq -r '.MESSAGE'
```

`-o json` is the integration point for log shipping — pipe it to `jq` or a
forwarder rather than parsing the default human-readable format.

## Correlating an incident

```bash
# Everything across the whole system in a tight window -- for cross-service
# correlation during an incident.
journalctl --since "13:45:00" --until "13:50:00"

# This unit and everything it depends on, ordered together.
journalctl -u myapp.service -u postgresql.service --since "10 min ago"

# The boot in which a specific failure happened.
journalctl --list-boots
journalctl -b -2 -u myapp.service

# Every restart of a unit, to see a crash-loop's cadence.
journalctl -u myapp.service -o short-iso | grep -E 'Started|Stopped|Failed'
```

## Disk usage and retention

```bash
journalctl --disk-usage
journalctl --vacuum-size=500M        # shrink to at most 500M
journalctl --vacuum-time=7d          # drop anything older than 7 days
journalctl --vacuum-files=5          # keep at most 5 rotated files
```

Persistent storage is controlled in `/etc/systemd/journald.conf`:

```ini
[Journal]
Storage=persistent
SystemMaxUse=500M
SystemMaxFileSize=50M
MaxRetentionSec=7day
```

Without `Storage=persistent`, the journal lives only in `/run/log/journal`
(tmpfs) and is lost on reboot. Confirm with:

```bash
journalctl --disk-usage
test -d /var/log/journal && echo persistent || echo volatile
```

## Filtering by structured fields

Every entry carries systemd-assigned metadata fields you can filter on
directly:

```bash
journalctl _SYSTEMD_UNIT=myapp.service     # equivalent to -u, more explicit
journalctl _COMM=nginx                     # by process name (comm)
journalctl _TRANSPORT=stdout               # only stdout/stderr-captured lines
journalctl _HOSTNAME=web-01
journalctl _EXE=/usr/bin/myapp
journalctl SYSLOG_IDENTIFIER=sshd

# Combine fields (AND); repeat a field (OR).
journalctl _SYSTEMD_UNIT=myapp.service _PID=1234
journalctl _SYSTEMD_UNIT=myapp.service _SYSTEMD_UNIT=nginx.service   # OR
```

List every field an entry carries:

```bash
journalctl -u myapp.service -o verbose -n 1
```

## Application-supplied structured fields

Applications using the native journal API (or `systemd-cat`) can attach
custom fields, queryable the same way:

```bash
journalctl MESSAGE_ID=<uuid>
journalctl TRACE_ID=abc123def456          # if the app logs a trace ID field
```

From a shell script, `systemd-cat` sends output into the journal with a
chosen identifier:

```bash
mycommand 2>&1 | systemd-cat -t mycommand -p info
journalctl -t mycommand
```

## Debugging a service that will not start

```bash
# The failure itself, tightly scoped.
journalctl -u myapp.service -p err -b --no-pager

# Everything since the last restart attempt.
journalctl -u myapp.service --since "$(systemctl show myapp -p ActiveEnterTimestamp --value)"

# Interleaved with the units it depends on.
journalctl -u myapp.service -u postgresql.service -u network-online.target -b

# Just before and after a known timestamp.
journalctl --since "13:44:50" --until "13:45:10"
```

## Cross-referencing exit codes

```bash
journalctl -u myapp.service | grep -E 'Main process exited|Failed with result'
systemctl show myapp.service -p Result -p ExecMainStatus -p ExecMainCode
```

`ExecMainCode` distinguishes `exited` (a normal exit(2), check
`ExecMainStatus` for the number) from `killed` (a signal — `ExecMainStatus`
is then the signal number).

## Performance and scripting notes

```bash
journalctl --no-pager                # required in scripts; otherwise blocks on a pager
journalctl -n 100 --no-pager -u myapp.service   # last 100 lines
journalctl -u myapp.service -q       # suppress the "-- Boot --" separator lines
```

`journalctl` output is expensive to grep repeatedly over a long window —
prefer narrowing with `--since`/`--until`/`-u`/`-p` first, and reach for
`-o json | jq` when the extraction logic is non-trivial rather than layering
`grep`/`awk` on the human-readable format.

## Remote and centralized logs

```bash
journalctl --list-boots -M container-name        # a systemd-nspawn container
journalctl --file=/mnt/backup/journal/*.journal   # read an exported journal file

# Forward to a central log server (requires systemd-journal-remote / -upload).
journalctl --output=export | curl --data-binary @- \
    http://log-server:19532/upload
```

For most fleets, forwarding through an OTel Collector or Fluent Bit reading
`journald` as a source is more common than `systemd-journal-remote` directly
— see the `fluent-bit-loki-pipeline` skill.
