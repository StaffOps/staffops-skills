#!/usr/bin/env bash
# Linux Troubleshooting Methodology — USE Method + Checklist
# USE = Utilization, Saturation, Errors (per Brendan Gregg)

# ═══ USE METHOD TABLE ═══════════════════════════════════════════
# Resource    | Utilization        | Saturation          | Errors
# ------------|--------------------|--------------------|--------
# CPU         | mpstat, top %us+sy | vmstat r > ncpu    | dmesg mce
# Memory      | free MemAvail      | vmstat si/so > 0   | dmesg oom
# Disk I/O    | iostat %util       | iostat avgqu-sz    | dmesg i/o
# Network     | sar -n DEV rx/tx   | netstat overflow   | ip -s (drops)
# Filesystem  | df -h %used        | —                  | dmesg ext4/xfs
# TCP         | ss -s established  | ss -tnp CLOSE_WAIT | netstat retrans

# ═══ QUICK CHECKLIST (run in order) ═════════════════════════════
echo "=== 1. System Overview ==="
uptime; hostname; uname -r

echo "=== 2. CPU ==="
mpstat 1 1 | tail -2
echo "Load vs CPUs: $(uptime | awk -F'average:' '{print $2}') / $(nproc) cores"

echo "=== 3. Memory ==="
free -h | grep -E "Mem|Swap"
echo "Available: $(awk '/MemAvailable/ {printf "%.0f%%", $2/'"$(awk '/MemTotal/ {print $2}' /proc/meminfo)"'*100}' /proc/meminfo)"

echo "=== 4. Disk Space ==="
df -h | awk '$5+0 > 70'

echo "=== 5. Disk I/O ==="
iostat -xz 1 1 2>/dev/null | awk 'NR>3 && $NF+0>0'

echo "=== 6. Network ==="
ip -s link show | grep -E "^[0-9]|RX:|TX:" | grep -v "0$"

echo "=== 7. Top Processes ==="
ps -eo pid,%cpu,%mem,comm --sort=-%cpu | head -5

echo "=== 8. Recent Errors ==="
dmesg -T --level=err,crit,alert,emerg 2>/dev/null | tail -5
journalctl -p err --since "1 hour ago" --no-pager | tail -10

# ═══ DECISION TREE ══════════════════════════════════════════════
# Problem reported
# │
# ├─ Is it happening NOW?
# │  ├── YES → Check the 5 vitals (cpu/mem/disk/net/proc)
# │  └── NO → Check logs, dmesg for when it happened
# │
# ├─ Single host or multiple?
# │  ├── Single → host-specific (hardware, local config, local process)
# │  └── Multiple → shared infrastructure (network, DNS, storage, deploy)
# │
# ├─ Did something change?
# │  ├── YES → Correlate change timestamp with symptom start
# │  └── NO → Resource exhaustion / degradation over time
# │
# └─ Has it happened before?
#    ├── YES → Check previous RCA, same fix applies?
#    └── NO → Systematic USE method investigation

# ═══ ANTI-PATTERNS ══════════════════════════════════════════════
# ❌ "I'll just restart it" (loses evidence, may recur)
# ❌ Checking one resource and concluding (check ALL resources)
# ❌ Blaming the last deploy without evidence
# ❌ Spending 30min on CPU when the problem is disk
# ❌ Not preserving evidence before mitigation
# ❌ Fixing the symptom without understanding the cause
