#!/usr/bin/env bash
# Incident Triage — Systematic First-60-Seconds Procedure

# ═══ STEP 1: SCOPE (10 seconds) ════════════════════════════════
# What's affected? Single host? Multiple? All?
hostname; date; uptime
# If remote: is it just this host or broader?

# ═══ STEP 2: RECENT CHANGES (10 seconds) ═══════════════════════
# What changed?
last -5                                  # recent logins
journalctl --since "30min ago" -p warning | tail -20
dmesg -T | tail -20                      # kernel events
# K8s: kubectl get events --sort-by=.lastTimestamp | tail -20

# ═══ STEP 3: SYMPTOMS (40 seconds — the "5 vitals") ════════════

# 1. CPU
uptime                                   # load average vs CPU count
mpstat -P ALL 1 1 | tail                # per-CPU (one imbalanced = single-thread bottleneck)

# 2. Memory
free -h                                  # available < 10% = concern
dmesg -T | grep -c "oom\|Out of memory" # OOM kills?

# 3. Disk
df -h | awk '$5+0 > 80 {print}'         # filesystems >80%
iostat -xz 1 1 | awk '$NF+0 > 50'       # disks >50% utilized

# 4. Network
ss -s                                    # socket states summary
ip -s link show | grep -E "dropped|errors" | grep -v " 0$"  # interface errors

# 5. Processes
ps aux --sort=-%cpu | head -5            # CPU hogs
ps aux --sort=-%mem | head -5            # memory hogs
ps aux | awk '$8 ~ /[DZ]/ {print}'      # D-state (stuck I/O) or zombie

# ═══ STEP 4: CLASSIFY ══════════════════════════════════════════
# Based on steps 1-3, categorize:
# | Symptom | Likely cause |
# |---------|-------------|
# | High load, CPU 100% | CPU-bound process (check top PID) |
# | High load, low CPU | I/O wait (iostat → disk problem) |
# | OOM kills | Memory leak or undersized |
# | Disk full | Log rotation, temp files, data growth |
# | Network errors | Cable, switch, MTU, firewall |
# | D-state processes | Disk/NFS hang |

# ═══ STEP 5: IMMEDIATE MITIGATION ══════════════════════════════
# DON'T: restart blindly (loses evidence)
# DO: preserve state THEN mitigate

# Preserve evidence:
top -bn1 > /tmp/incident-top-$(date +%s).txt
ps auxf > /tmp/incident-ps-$(date +%s).txt
ss -tnp > /tmp/incident-ss-$(date +%s).txt
cp /var/log/syslog /tmp/incident-syslog-$(date +%s).txt

# Then mitigate based on category above.

# ═══ STEP 6: COMMUNICATE ═══════════════════════════════════════
# Template: "At HH:MM, [symptom]. Affects [scope]. Investigating [category]. ETA [X]min."
# DON'T: "looking into it" (no information)
# DO: "API 500s started at 14:32. Single host (app-3). CPU saturated by pid 12345. Killing in 2min if no response from owner."

# ═══ TIMELINE TEMPLATE ══════════════════════════════════════════
# HH:MM - symptom first observed / alert fired
# HH:MM - investigation started, initial findings: ...
# HH:MM - root cause identified: ...
# HH:MM - mitigation applied: ...
# HH:MM - confirmed resolved: [evidence]
