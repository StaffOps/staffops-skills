#!/usr/bin/env bash
# Log Analysis — journalctl patterns + text log tools

# ═══ JOURNALCTL (systemd) ═══════════════════════════════════════
# Time-based
journalctl --since "2 hours ago"
journalctl --since "2024-01-15 14:00" --until "2024-01-15 15:00"
journalctl --since today
journalctl -b                            # current boot only
journalctl -b -1                         # previous boot

# By unit/service
journalctl -u nginx.service -f           # follow service logs
journalctl -u nginx -u php-fpm          # multiple services
journalctl -u myapp --since "5min ago" -p err  # errors in last 5min

# By priority
journalctl -p err                        # error and above
journalctl -p warning                    # warning and above
journalctl -p crit                       # critical only
# Priorities: emerg(0) alert(1) crit(2) err(3) warning(4) notice(5) info(6) debug(7)

# By PID / user
journalctl _PID=1234
journalctl _UID=1000
journalctl _COMM=sshd                    # by command name

# Kernel messages
journalctl -k                            # kernel ring buffer
journalctl -k -p err                     # kernel errors

# Output formats
journalctl -u myapp -o json-pretty | head -50    # JSON (for parsing)
journalctl -u myapp -o short-iso                 # ISO timestamps
journalctl -u myapp -o cat                       # message only (no metadata)
journalctl -u myapp --no-pager | wc -l          # count lines

# Disk usage
journalctl --disk-usage                  # how much space
journalctl --vacuum-size=500M            # trim to 500M
journalctl --vacuum-time=7d              # keep only 7 days

# ═══ TEXT LOG ANALYSIS ═══════════════════════════════════════════
# Count errors per hour
grep -c "ERROR" /var/log/app/app.log

# Error frequency over time
grep "ERROR" app.log | awk '{print $1, $2}' | cut -d: -f1-2 | uniq -c | sort -rn

# Top error messages (deduplicated)
grep "ERROR" app.log | sed 's/[0-9]//g' | sort | uniq -c | sort -rn | head

# Extract timestamps and correlate
grep "timeout" app.log | awk '{print $1"T"$2}' | head

# Follow multiple logs
tail -f /var/log/nginx/error.log /var/log/app/app.log

# ═══ STRUCTURED LOG PARSING (JSON logs) ═══════════════════════
# Parse JSON logs with jq
cat app.log | jq -r 'select(.level == "error") | "\(.timestamp) \(.message)"'
cat app.log | jq -r 'select(.status >= 500) | "\(.timestamp) \(.method) \(.path) \(.status)"'

# Error rate per minute
cat app.log | jq -r 'select(.level == "error") | .timestamp' | cut -c1-16 | uniq -c

# ═══ QUICK FORENSICS ═══════════════════════════════════════════
# What happened at time T?
journalctl --since "14:30" --until "14:35" --no-pager
grep "14:3[0-5]" /var/log/*.log

# What services had errors?
journalctl --since "1 hour ago" -p err --no-pager | awk '{print $5}' | sort | uniq -c | sort -rn

# Auth failures (brute force detection)
journalctl -u sshd --since today | grep -c "Failed password"
grep "Failed password" /var/log/auth.log | awk '{print $11}' | sort | uniq -c | sort -rn | head

# ═══ KUBERNETES LOG PATTERNS ═══════════════════════════════════
# kubectl logs <pod> --since=5m                    # last 5 min
# kubectl logs <pod> --previous                    # crashed container
# kubectl logs -l app=myapp --all-containers       # by label
# kubectl logs <pod> -c sidecar                    # specific container
# kubectl logs <pod> --timestamps | grep ERROR     # with timestamps
