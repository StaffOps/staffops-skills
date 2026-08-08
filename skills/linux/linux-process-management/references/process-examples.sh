#!/usr/bin/env bash
# Linux Process Management — Practical Examples

# ═══ VIEWING PROCESSES ══════════════════════════════════════════
ps aux --sort=-%mem | head -10           # top memory consumers
ps aux --sort=-%cpu | head -10           # top CPU consumers
ps -eo pid,ppid,user,%mem,%cpu,stat,start,time,comm --sort=-%mem | head
ps -eLf | wc -l                          # total thread count
ps -eo user | sort | uniq -c | sort -rn  # processes per user
pstree -p "pid"                          # process tree from PID
pstree -u                                # all with user changes

# ═══ SIGNALS ═══════════════════════════════════════════════════
kill -0 "pid"                            # check if process exists (no signal)
kill "pid"                               # SIGTERM (graceful)
kill -9 "pid"                            # SIGKILL (force, last resort)
kill -HUP "pid"                          # reload config (nginx, haproxy)
kill -USR1 "pid"                         # app-specific (log rotate, dump state)
killall -u baduser                       # kill all by user
pkill -f "python worker"                 # kill by command pattern

# ═══ RESOURCE LIMITS ═══════════════════════════════════════════
ulimit -a                                # show limits for current shell
cat /proc/"pid"/limits                   # limits for running process
# Common ones:
ulimit -n                                # max open files
ulimit -u                                # max processes
# System-wide:
sysctl fs.file-max                       # system open file limit
cat /proc/sys/kernel/pid_max             # max PIDs

# ═══ PROCESS INVESTIGATION ═════════════════════════════════════
# What's this process doing?
strace -p "pid" -c                       # syscall summary
strace -p "pid" -e trace=file            # file operations only
strace -p "pid" -e trace=network         # network operations only

# What files does it have open?
lsof -p "pid"                            # all open files
lsof -p "pid" | grep -E "TCP|UDP"       # network connections
ls -la /proc/"pid"/fd/                   # raw file descriptors
cat /proc/"pid"/maps                     # memory mappings

# What's its environment?
cat /proc/"pid"/environ | tr '\0' '\n'   # environment variables
cat /proc/"pid"/cmdline | tr '\0' ' '   # full command line
cat /proc/"pid"/status                   # memory, threads, state
readlink /proc/"pid"/cwd                 # working directory
readlink /proc/"pid"/exe                 # binary path

# ═══ PRIORITY / SCHEDULING ═════════════════════════════════════
nice -n 10 ./heavy-job                   # start with lower priority
renice -n 5 -p "pid"                     # change running process priority
ionice -c3 -p "pid"                      # idle I/O priority (won't starve others)
taskset -cp 0-3 "pid"                    # pin to CPUs 0-3
chrt -f -p 50 "pid"                      # real-time FIFO priority 50

# ═══ BACKGROUND / JOB CONTROL ══════════════════════════════════
command &                                # run in background
nohup command &                          # survive terminal close
disown %1                                # detach job from shell
jobs -l                                  # list background jobs
fg %1                                    # bring to foreground
bg %1                                    # resume in background

# Long-running in tmux/screen:
tmux new -s myjob "command"              # named session
screen -dmS myjob command                # detached screen

# ═══ CGROUPS (container/systemd processes) ═════════════════════
systemd-cgls                             # cgroup tree
systemd-cgtop                            # top by cgroup
cat /sys/fs/cgroup/memory/"group"/memory.usage_in_bytes
cat /proc/"pid"/cgroup                   # which cgroup is a process in
