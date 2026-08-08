#!/usr/bin/env bash
# Disk & Memory Issues — Diagnostic Commands

# ═══ MEMORY — Is it actually OOM? ═══════════════════════════════
free -h                                  # quick overview
cat /proc/meminfo | grep -E "MemTotal|MemAvailable|SwapTotal|SwapFree"
vmstat 1 5                              # watch si/so (swap activity)
dmesg -T | grep -i "oom\|out of memory\|killed"   # OOM events
journalctl -k | grep -i oom             # kernel OOM messages

# Who's using memory?
ps aux --sort=-%mem | head -10           # top memory consumers
smem -t -k -p | head -20               # proportional memory (more accurate)
cat /proc/"pid"/status | grep -E "VmRSS|VmSize|VmSwap"  # specific process
pmap -x "pid" | tail -5                 # memory mapping summary

# Memory leak detection (watch RSS grow)
while true; do ps -p "pid" -o pid,rss,vsz,comm --no-headers; sleep 5; done

# Cache/buffer (reclaimable — NOT a problem)
cat /proc/meminfo | grep -E "Buffers|Cached|SReclaimable"
# Available = Free + Reclaimable. If Available is fine, it's not OOM.

# ═══ DISK — Space issues ════════════════════════════════════════
df -h                                    # filesystem space
df -i                                    # inode usage (can be full with free space!)
du -sh /* 2>/dev/null | sort -rh | head  # biggest top-level dirs
du -sh /var/log/* | sort -rh | head     # biggest in /var/log

# Find big files
find / -xdev -type f -size +100M -printf "%s %p\n" 2>/dev/null | sort -rn | head -20

# Deleted files still holding space
lsof +L1 | grep deleted                 # open handles to deleted files
# Fix: restart the process, or truncate: > /proc/"pid"/fd/"fd_number"

# What filled up recently?
find /var -mmin -60 -type f -size +10M 2>/dev/null  # grown in last hour

# ═══ DISK — I/O issues ══════════════════════════════════════════
iostat -xz 1 5                          # disk utilization + latency
# Key columns: %util (>90% = saturated), await (>10ms = slow)
iotop -bon 3                            # which processes doing I/O
cat /sys/block/sda/stat                 # raw disk counters

# Is it swap thrashing?
vmstat 1 5                              # si/so columns
sar -B 1 5                             # pgscand/s > 0 = direct reclaim (BAD)
cat /proc/vmstat | grep -E "pswpin|pswpout"

# ═══ EMERGENCY: DISK 100% ═══════════════════════════════════════
# 1. Find and truncate largest log immediately
find /var/log -name "*.log" -size +1G | head -3
truncate -s 0 /var/log/biggest.log       # instant space back

# 2. Clear systemd journal
journalctl --vacuum-size=200M

# 3. Remove old package cache
apt clean                                # Debian/Ubuntu

# 4. Find and remove old kernels
dpkg -l 'linux-image-*' | grep -E '^ii' | awk '{print $2}' | grep -v "$(uname -r)"

# ═══ EMERGENCY: OOM ═════════════════════════════════════════════
# 1. Identify the OOM-killed process
dmesg -T | grep -A5 "Out of memory"    # shows what was killed
journalctl -k --since "1 hour ago" | grep -A5 "oom_kill"

# 2. Find current memory hogs
ps -eo pid,ppid,rss,%mem,comm --sort=-rss | head -10

# 3. Quick mitigation options:
sysctl vm.drop_caches=3                 # drop page cache (safe, temp relief)
swapoff -a && swapon -a                 # reset swap (careful if under pressure)

# ═══ KUBERNETES-SPECIFIC ════════════════════════════════════════
# Container OOMKilled:
# kubectl describe pod "pod" | grep -A5 "Last State"
# kubectl get pod "pod" -o jsonpath='{.status.containerStatuses[0].lastState}'
# Pod evicted for disk pressure:
# kubectl describe node "node" | grep -A5 "Conditions"
# kubectl get events --field-selector reason=Evicted
