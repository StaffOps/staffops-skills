---
name: linux-filesystem
description: "Manage permissions, mounts, links and disk usage."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [filesystem, permissions, acl, mount, inode, disk, df, du, symlink]
    category: linux
    related_skills: [linux-command-line, bash-scripting]
---
# Linux Filesystem

Permissions and ownership, special bits, ACLs, mounts, links, and finding
where the disk actually went. Most "permission denied" and "no space left"
incidents resolve to one of a handful of causes covered here.

## When to Use

Use when debugging permission errors, deciding on ownership for a service
directory, investigating a full disk, understanding a mount option, or
choosing between a hard link and a symlink.

## Permission model

Every file has an owner, a group, and three permission triads.

```
-rwxr-xr--  1 deploy www-data  4096 Jan 10 12:00 script.sh
│└┬┘└┬┘└┬┘     └──┬─┘ └───┬──┘
│ │  │  │         │       └─ group
│ │  │  └─ other  └───────── owner
│ │  └──── group
│ └─────── owner
└───────── type: - file, d dir, l symlink, b block, c char, s socket, p fifo
```

| Bit | On a file | On a directory |
| --- | --- | --- |
| `r` (4) | Read contents | List names |
| `w` (2) | Modify contents | **Create and delete entries** |
| `x` (1) | Execute | Traverse into / access entries |

The directory semantics are what surprise people:

- **Deleting a file needs `w` on the directory, not on the file.** A read-only
  file in a writable directory can be removed.
- **`r` without `x` on a directory** lets you list names but stat nothing —
  `ls` works, `ls -l` shows `?`.
- **`x` without `r`** lets you access a known path but not list it.

```bash
chmod 644 file           # rw-r--r--
chmod 755 dir            # rwxr-xr-x
chmod u+x,go-w file      # symbolic
chmod -R u=rwX,go=rX dir # capital X: x only on dirs and already-executable files
```

`X` (capital) is the correct way to fix a tree recursively — it avoids making
every data file executable:

```bash
chmod -R u=rwX,go=rX /srv/app       # right
chmod -R 755 /srv/app               # wrong: marks every .txt executable
```

Or split by type:

```bash
find /srv/app -type d -exec chmod 755 {} +
find /srv/app -type f -exec chmod 644 {} +
```

## Special bits

| Bit | Octal | Effect |
| --- | --- | --- |
| setuid | 4000 | Executable runs as the file's **owner** |
| setgid | 2000 | Executable runs as the file's group; on a **directory**, new entries inherit the directory's group |
| sticky | 1000 | On a directory, only the owner of a file may delete it |

```bash
chmod 4755 binary      # setuid -- shows as rwsr-xr-x
chmod 2775 shared_dir  # setgid -- new files inherit the group
chmod 1777 /tmp        # sticky -- shows as rwxrwxrwt
```

**setgid on a directory** is the standard way to make a shared team directory
work: every file created inside inherits the group regardless of the creator's
primary group.

```bash
chgrp -R developers /srv/shared
chmod -R g+ws /srv/shared      # setgid + group write
```

setuid binaries are a standing security risk. Audit them:

```bash
find / -xdev -type f -perm /6000 -exec ls -l {} + 2>/dev/null
```

setuid is **ignored on shell scripts** by every modern kernel, and on
filesystems mounted `nosuid`.

## umask

`umask` masks off bits from the default (666 for files, 777 for directories):

| umask | New file | New directory |
| --- | --- | --- |
| 022 | 644 | 755 |
| 002 | 664 | 775 |
| 027 | 640 | 750 |
| 077 | 600 | 700 |

```bash
umask               # show current
umask 027           # owner full, group read, other nothing
(umask 077; touch secret)   # scoped to a subshell
```

Files are never created executable by `umask` alone — that is why the base is
666, not 777.

## ACLs

When the owner/group/other model is not enough, POSIX ACLs grant per-user and
per-group entries. The filesystem must be mounted with `acl` (default on ext4
and xfs).

```bash
getfacl file
setfacl -m u:alice:rw file          # grant alice read-write
setfacl -m g:auditors:r file        # grant a group
setfacl -x u:alice file             # remove alice's entry
setfacl -b file                     # remove all ACLs

# Default ACLs: inherited by new entries in a directory.
setfacl -d -m u:deploy:rwx /srv/app
setfacl -R -m u:deploy:rwX /srv/app
```

A `+` at the end of the mode in `ls -l` means an ACL is present:

```
-rw-rw----+ 1 root root 0 Jan 10 12:00 file
```

The "mask" entry caps every named entry. If effective permissions look wrong
despite a correct ACL, check the mask:

```bash
getfacl file | grep mask
setfacl -m m::rwx file
```

## Links

| | Hard link | Symbolic link |
| --- | --- | --- |
| Points to | The inode | A path string |
| Cross filesystems | No | Yes |
| Link to a directory | No (except `.`/`..`) | Yes |
| Survives target rename | Yes | No — becomes broken |
| Own permissions | Shares the inode's | Has its own, usually ignored |
| Space | None | A small inode |

```bash
ln target hardlink
ln -s /path/to/target symlink
ln -sfn /new/target existing_symlink    # -n avoids descending into a dir symlink
readlink -f symlink                     # resolve fully
find . -xtype l                         # broken symlinks
stat -c '%h' file                       # hard link count
```

A file's data is freed only when its link count reaches zero **and** no
process holds it open — the basis of the "deleted but still using space"
problem.

## Mounts

```bash
mount                              # everything currently mounted
findmnt                            # tree view, much more readable
findmnt /var                       # what is mounted there
mount -o remount,ro /mnt/data      # change options in place
umount -l /mnt/data                # lazy: detach now, clean up when free
lsblk -f                           # block devices with filesystem and UUID
blkid                              # UUIDs for fstab
```

Options that matter operationally:

| Option | Effect |
| --- | --- |
| `noexec` | Binaries cannot be executed from this mount |
| `nosuid` | setuid/setgid bits ignored |
| `nodev` | Device nodes ignored |
| `ro` | Read-only |
| `noatime` | Do not update access times — a real performance win |
| `relatime` | Update atime only if older than mtime (modern default) |
| `nofail` | Boot continues if the mount fails |
| `_netdev` | Wait for the network before mounting |

`/etc/fstab` entries, always by UUID rather than device name (which can change
across boots):

```
UUID=1234-5678  /data  ext4  defaults,noatime,nofail  0  2
```

Validate before rebooting — a bad fstab can leave a machine unbootable:

```bash
mount -a          # mount everything in fstab; errors surface here
findmnt --verify  # syntax check
```

## Disk usage

```bash
df -h                    # free space per filesystem
df -i                    # free INODES -- the other way to run out
du -sh /var/*            # size per entry
du -h --max-depth=1 /var | sort -h
du -xsh /*               # -x: stay on one filesystem
ncdu /var                # interactive, if available
```

**"No space left on device" with free space in `df -h`** has three usual
causes:

1. **Inodes exhausted** — `df -i`. Millions of tiny files, often a mail queue
   or session directory.
2. **A deleted file held open** — the space returns only when the holder
   closes it:
   ```bash
   lsof +L1                        # files with link count 0
   lsof -nP | grep deleted
   ```
   Restart the process, or truncate through `/proc`:
   ```bash
   : > /proc/<pid>/fd/<n>
   ```
3. **Reserved blocks** — ext4 reserves 5% for root by default:
   ```bash
   tune2fs -l /dev/sda1 | grep -i reserved
   tune2fs -m 1 /dev/sda1          # reduce to 1%
   ```

A fourth, subtler case: a directory mounted over. Files written before the
mount are hidden but still consume space. Check by bind-mounting the parent
elsewhere.

## Ownership

```bash
chown user file
chown user:group file
chown -R user:group dir
chown --reference=other file       # copy ownership from another file
chgrp group file
```

`chown` requires root. `chgrp` works for the owner if they are a member of the
target group.

Prefer group-based access over per-file `chown` for service directories: add
the service account to a group, `setgid` the directory, and the permissions
stay correct as files are created.

## Pitfalls

- **`chmod -R 777`** — never a fix; it makes every file world-writable and
  executable, and breaks `ssh` key permission checks outright.
- **`chmod -R 755` on a data tree** — marks data files executable. Use `u=rwX`.
- **Deleting requires `w` on the directory** — file permissions are irrelevant.
- **`ln -sf` onto an existing symlink-to-directory** — creates the link
  *inside* it. Add `-n`.
- **`rm -rf "$dir/"` with `$dir` empty** — use `"${dir:?}"`.
- **Device names in fstab** — `/dev/sdb` can become `/dev/sdc`. Use UUIDs.
- **Forgetting `nofail`** — a missing disk blocks boot.
- **`du` vs `df` disagreement** — deleted-but-open files, or a mount shadowing
  a populated directory.
- **`umount` says "target is busy"** — `fuser -vm /mnt` or `lsof +f -- /mnt`
  shows who.

## Verification

```bash
namei -l /full/path/to/file    # permissions of EVERY component in the path
stat file                      # inode, links, mode, times
getfacl file                   # ACLs
sudo -u www-data test -r file && echo readable   # check AS the service user
findmnt -o TARGET,SOURCE,FSTYPE,OPTIONS
```

`namei -l` is the fastest way to diagnose a permission error — it shows which
directory in the path denies traversal, which is usually a missing `x` several
levels up rather than anything wrong with the file itself.

`scripts/perm-audit.sh` reports world-writable files, setuid binaries, and
broken ownership across a tree.

## Reference

- `references/permissions.md` — full mode table, ACL semantics, umask math
- `references/disk-full.md` — decision tree for space and inode exhaustion
- `scripts/perm-audit.sh` — permission and ownership audit for a directory tree
