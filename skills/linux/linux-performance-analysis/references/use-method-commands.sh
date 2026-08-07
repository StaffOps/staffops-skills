#!/usr/bin/env bash
# Linux Performance Analysis — USE Method
# For each resource: Utilization, Saturation, Errors

# ═══ CPU ════════════════════════════════════════════════════════
# Utilization
uptime                                   # load average (1/5/15 min)
mpstat -P ALL 1 3                       # per-CPU utilization
top -bn1 | head -5                      # quick summary
sar -u 1 5                              # CPU over time

# Saturation
vmstat 1 5                              # r column > CPU count = saturated
cat /proc/stat | grep procs_running

# Errors
dmesg | grep -i "mce\|machine check"   # hardware CPU errors
perf stat -a sleep 5                    # PMU counters

# ═══ MEMORY ═════════════════════════════════════════════════════
# Utilization
free -h                                  # total/used/available
cat /proc/meminfo | grep -E "MemTotal|MemAvailable|Buffers|Cached"
vmstat -s | grep -E "total|free|active"

# Saturation
vmstat 1 5                              # si/so columns (swap in/out)
sar -B 1 5                             # pgscand/s > 0 = direct reclaim (bad)
dmesg | grep -i "oom"                   # OOM killer invoked

# Errors
dmesg | grep -iE "memory|edac|ecc"     # hardware memory errors
cat /proc/buddyinfo                     # fragmentation

# ═══ DISK I/O ═══════════════════════════════════════════════════
# Utilization
iostat -xz 1 3                          # %util column (>80% = concern)
iotop -bon 3                            # per-process I/O

# Saturation
iostat -xz 1 3                          # avgqu-sz column (queue depth)
cat /sys/block/sda/stat                 # raw counters

# Errors
dmesg | grep -iE "error|i/o|read\|write.*fail"
smartctl -a /dev/sda | grep -E "Reallocated|Current_Pending|Offline_Uncorrectable"

# ═══ NETWORK ═══════════════════════════════════════════════════
# Utilization
sar -n DEV 1 3                          # interface throughput
ip -s link show eth0                    # TX/RX bytes

# Saturation
netstat -s | grep -E "retrans|overflow|drop"
ss -tnp | wc -l                         # connection count
cat /proc/net/softnet_stat | awk '{print $2}' # NIC backlog drops (2nd col)

# Errors
ip -s link show eth0                    # errors, dropped, overruns
ethtool -S eth0 | grep -iE "error|drop|miss|crc"
dmesg | grep -i "link\|eth\|nic"

# ═══ FILESYSTEM ═════════════════════════════════════════════════
# Utilization
df -h                                    # space
df -i                                    # inodes

# Saturation (not typical — filesystem waits on disk I/O)
cat /proc/sys/fs/file-nr               # allocated / max open files

# Errors
dmesg | grep -iE "ext4\|xfs\|readonly\|corrupt"
mount | grep "ro,"                      # remounted read-only = FS error

# ═══ QUICK "60 SECONDS" CHECKLIST ══════════════════════════════
# 1. uptime           → load average
# 2. dmesg -T | tail  → kernel errors
# 3. vmstat 1 5       → cpu/mem/swap/io
# 4. mpstat -P ALL 1  → per-cpu balance
# 5. iostat -xz 1 3   → disk utilization
# 6. free -h          → memory
# 7. sar -n DEV 1 3   → network throughput
# 8. ss -s            → socket stats
# 9. top -bn1 | head  → top processes
# 10. dmesg -T | tail → recent errors
