# Disk Full: Decision Tree

"No space left on device" (`ENOSPC`) has several distinct causes that need
different fixes. Work through them in this order — the first two account for
most incidents where `df -h` looks fine.

## Step 1: Is it actually blocks?

```bash
df -h /path            # block usage
df -i /path            # INODE usage
```

If `IUse%` is 100% but `Use%` is low, the filesystem ran out of **inodes**,
not space. Find the offender:

```bash
# Directories with the most entries.
find /var -xdev -type d -exec sh -c 'printf "%s\t%s\n" "$(ls -A "$1" | wc -l)" "$1"' _ {} \; 2>/dev/null \
  | sort -rn | head -20

# Faster on huge trees.
du --inodes -x /var 2>/dev/null | sort -rn | head -20
```

Typical sources: mail queues (`/var/spool`), PHP or Rails session files,
unrotated per-request log files, `node_modules` in many checkouts, Docker
overlay layers.

Inode count is fixed at mkfs time on ext4 — it cannot be grown. The fix is to
delete files or recreate the filesystem with `mkfs.ext4 -i` tuned lower. XFS
allocates inodes dynamically and rarely hits this.

## Step 2: Deleted files still held open

The classic "`du` says 2 GB, `df` says 100%".

When a process holds an open descriptor to a deleted file, the blocks are not
freed. `du` walks directory entries and cannot see it; `df` reads the
allocation map and can.

```bash
lsof +L1                    # files whose link count is 0
lsof -nP | grep '(deleted)'
```

Fix, in order of preference:

```bash
# 1. Restart or signal the process to reopen its logs.
systemctl restart myservice
kill -HUP "$pid"            # many daemons reopen logs on SIGHUP

# 2. Truncate through /proc without restarting (reclaims space immediately).
: > "/proc/<pid>/fd/<n>"
```

The `/proc` trick works because the descriptor still points at the inode.
Identify `<n>` from the `FD` column of `lsof`.

This is almost always a log file that was `rm`'d instead of truncated, or a
logrotate configuration missing `copytruncate` for a daemon that does not
handle `SIGHUP`.

## Step 3: Reserved blocks

ext2/3/4 reserve 5% of the filesystem for root by default so the system stays
usable when a filesystem fills. Non-root writes fail while `df` shows ~5%
available.

```bash
tune2fs -l /dev/sda1 | grep -i 'reserved block'
tune2fs -m 1 /dev/sda1        # reduce the reservation to 1%
```

On a dedicated data volume, 0-1% is reasonable. Keep 5% on the root
filesystem — it is what lets you log in and fix things.

## Step 4: A mount shadowing a populated directory

Files written to `/data` *before* a filesystem was mounted there still occupy
space on the parent filesystem, but are invisible while the mount is active.

```bash
mkdir /mnt/probe
mount --bind / /mnt/probe
du -sh /mnt/probe/data        # what is hidden underneath
umount /mnt/probe
```

## Step 5: Quotas

If only one user is affected:

```bash
quota -u username
repquota -a
xfs_quota -x -c 'report -h' /data
```

## Step 6: Filesystem-specific

**XFS** can fail with `ENOSPC` due to fragmentation of free space even with
capacity available:

```bash
xfs_db -r -c freesp /dev/sda1
xfs_fsr /dev/sda1            # online defragmentation
```

**Btrfs** reports space in a way `df` cannot represent correctly; use its own
tooling:

```bash
btrfs filesystem usage /mnt
btrfs balance start -dusage=50 /mnt
```

**Snapshots** (LVM, ZFS, Btrfs) consume space that is invisible in the mounted
tree:

```bash
lvs -o +lv_when_full
zfs list -t snapshot -o name,used -s used
btrfs subvolume list /
```

## Finding what to delete

```bash
# Largest directories, one filesystem only.
du -xh --max-depth=2 / 2>/dev/null | sort -rh | head -20

# Largest individual files.
find / -xdev -type f -printf '%s\t%p\n' 2>/dev/null | sort -rn | head -20

# Interactive, if available.
ncdu -x /

# Journal size (frequently multiple GB).
journalctl --disk-usage
journalctl --vacuum-size=200M
journalctl --vacuum-time=7d

# Package cache.
apt-get clean                          # Debian/Ubuntu
dnf clean all                          # RHEL family

# Docker -- often the single largest consumer.
docker system df
docker system prune -a --volumes       # destructive; read the output first

# Old kernels (Debian/Ubuntu).
apt-get autoremove --purge
```

## Safe emptying

```bash
: > /var/log/big.log          # truncate in place -- keeps the descriptor valid
truncate -s 0 /var/log/big.log
```

Never `rm` an active log file — that produces exactly the Step 2 problem. Use
truncation, and fix logrotate so it does not recur:

```
/var/log/app/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    copytruncate      # for daemons that do not reopen on SIGHUP
}
```

Prefer `create` plus a `postrotate` `SIGHUP` when the daemon supports it —
`copytruncate` has a small window where log lines can be lost.

## Prevention

- Alert on **both** `df` and `df -i` — inode exhaustion is invisible otherwise.
- Alert on the *rate of change*, not only the threshold: a partition going
  from 40% to 70% in an hour matters more than one sitting at 85%.
- Put `/var/log` on its own filesystem so a log flood cannot take down the
  root filesystem.
- Set `SystemMaxUse` in `/etc/systemd/journald.conf`.
- Cap container log size in `/etc/docker/daemon.json`:
  ```json
  { "log-driver": "json-file", "log-opts": { "max-size": "50m", "max-file": "3" } }
  ```
- Keep 5% reserved on the root filesystem so recovery remains possible.

## Quick triage sequence

```bash
df -h; df -i                                    # blocks or inodes?
lsof +L1 2>/dev/null | head                     # deleted-but-open?
du -xh --max-depth=1 / 2>/dev/null | sort -rh | head
journalctl --disk-usage; docker system df 2>/dev/null
```

Four commands identify the cause in the large majority of cases.
