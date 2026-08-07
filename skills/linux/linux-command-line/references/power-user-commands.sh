#!/usr/bin/env bash
# Linux Command Line — Power User Commands

# ═══ FIND + EXEC ═══════════════════════════════════════════════
find / -name "*.log" -mtime +7 -delete                     # delete logs >7 days
find . -type f -size +100M                                  # files >100MB
find . -type f -name "*.py" -exec grep -l "TODO" {} \;     # search in files
find . -type f -newer /tmp/marker -name "*.yaml"           # modified after marker
find . -maxdepth 1 -type d | wc -l                         # count subdirs
find / -perm -4000 2>/dev/null                             # SUID binaries

# ═══ XARGS (parallel execution) ═══════════════════════════════
find . -name "*.gz" | xargs -P4 gunzip                     # parallel gunzip
cat urls.txt | xargs -P8 -I{} curl -sL {} -o /dev/null    # parallel curl
echo "a b c" | xargs -n1                                   # one arg per line

# ═══ PROCESS SUBSTITUTION + REDIRECTION ═══════════════════════
diff <(ssh host1 cat /etc/config) <(ssh host2 cat /etc/config)  # compare remote files
paste <(cut -d: -f1 /etc/passwd) <(cut -d: -f7 /etc/passwd)   # join columns
command > >(tee stdout.log) 2> >(tee stderr.log >&2)          # split stdout/stderr

# ═══ HISTORY + EXPANSION ══════════════════════════════════════
!!                   # re-run last command
!$                   # last argument of previous command
!:2                  # 2nd argument of previous command
^old^new             # replace in last command
history | awk '{print $2}' | sort | uniq -c | sort -rn | head  # most used commands

# ═══ COLUMN / TABLE FORMATTING ════════════════════════════════
mount | column -t                        # align mount output
cat /etc/fstab | column -t               # pretty-print fstab
ps aux | awk '{printf "%-10s %5s %s\n", $1, $2, $11}' | head

# ═══ DISK / FILE OPERATIONS ══════════════════════════════════
du -sh */ | sort -rh | head -10          # top 10 dirs by size
ncdu /var                                # interactive disk usage
rsync -avP --delete src/ dest/           # mirror dirs with progress
tar czf - dir/ | pv | ssh host 'tar xzf - -C /dest'  # copy with progress

# ═══ SYSTEM INFO ═════════════════════════════════════════════
lscpu                                    # CPU info
lsblk -f                                 # block devices + filesystems
lsof -i :8080                            # who's using port 8080
lsof +D /var/log                         # open files in dir
fuser -v /mount/point                    # processes using mount
strace -p <pid> -e trace=network        # trace network syscalls
ltrace -p <pid>                          # library calls

# ═══ QUICK ONE-LINERS ═══════════════════════════════════════
# Count lines across all files
find . -name "*.go" | xargs wc -l | tail -1

# Watch for file changes
inotifywait -mr /path -e modify,create,delete

# Generate random password
openssl rand -base64 32 | head -c 24

# Quick HTTP server
python3 -m http.server 8080

# Repeat command until it succeeds
until curl -sf http://localhost:8080/healthz; do sleep 2; done

# Parallel SSH
for h in host{1..5}; do ssh $h "hostname; uptime" & done; wait
