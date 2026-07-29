# Permissions Reference

## Mode bits

A mode is four octal digits: special, owner, group, other.

```
  4    7    5    5
  │    │    │    └── other:  r-x  (4+1)
  │    │    └─────── group:  r-x  (4+1)
  │    └──────────── owner:  rwx  (4+2+1)
  └───────────────── special: setuid (4)
```

| Value | Permission |
| --- | --- |
| 0 | `---` |
| 1 | `--x` |
| 2 | `-w-` |
| 3 | `-wx` |
| 4 | `r--` |
| 5 | `r-x` |
| 6 | `rw-` |
| 7 | `rwx` |

Special digit: setuid 4, setgid 2, sticky 1 (combinable).

## Common modes

| Mode | Use |
| --- | --- |
| 600 | Private file — SSH private keys, credentials |
| 640 | Owner writes, group reads — config with secrets |
| 644 | World-readable file — normal config, web content |
| 700 | Private directory — `~/.ssh`, `~/.gnupg` |
| 750 | Owner full, group traverse — service directories |
| 755 | Standard directory or executable |
| 775 | Group-writable directory — shared team work |
| 1777 | World-writable with sticky — `/tmp` only |
| 2775 | setgid group-writable directory — shared project trees |
| 4755 | setuid binary — audit every one of these |

SSH refuses to use keys and configs with loose permissions:

| Path | Required |
| --- | --- |
| `~/.ssh` | 700 |
| `~/.ssh/id_*` (private) | 600 |
| `~/.ssh/id_*.pub` | 644 |
| `~/.ssh/authorized_keys` | 600 |
| `~/.ssh/config` | 600 |
| `$HOME` | not group- or world-writable |

A world-writable `$HOME` breaks key authentication with a message that does
not mention the home directory — a frequent time sink.

## Symbolic notation

```
chmod [ugoa][+-=][rwxXst] file
```

| Who | Meaning |
| --- | --- |
| `u` | Owner |
| `g` | Group |
| `o` | Other |
| `a` | All (default when omitted) |

| Op | Meaning |
| --- | --- |
| `+` | Add |
| `-` | Remove |
| `=` | Set exactly (clears the others in that triad) |

| Perm | Meaning |
| --- | --- |
| `r` `w` `x` | Read, write, execute |
| `X` | Execute **only** on directories or files already executable |
| `s` | setuid (with `u`) or setgid (with `g`) |
| `t` | Sticky bit |

```bash
chmod u+x script.sh
chmod go-rwx secret
chmod a=r file                 # exactly r--r--r--
chmod g+s shared_dir           # setgid
chmod -R u=rwX,go=rX tree      # the correct recursive form
chmod --reference=model target # copy another file's mode
```

`X` is the critical one for recursion. `chmod -R a+x` marks every data file
executable; `chmod -R a+X` marks only directories and already-executable
files.

## umask arithmetic

The umask *removes* bits from the base: 666 for files, 777 for directories.
It is a bitwise AND with the complement, not subtraction — though for the
common values the result is the same.

| umask | File | Directory | Typical use |
| --- | --- | --- | --- |
| 000 | 666 | 777 | Never |
| 002 | 664 | 775 | Shared group development |
| 022 | 644 | 755 | Default on most distributions |
| 027 | 640 | 750 | Hardened: nothing for "other" |
| 077 | 600 | 700 | Private: owner only |

```bash
umask                    # current, in octal
umask -S                 # symbolic
umask 027                # set for this shell
(umask 077; touch key)   # scoped -- the parent shell is unchanged
```

Set it system-wide in `/etc/login.defs` (`UMASK`) or `/etc/profile`. For a
systemd service, use `UMask=` in the unit — a login shell's umask does not
apply to services.

## Checking effective access

```bash
namei -l /srv/app/data/file.txt     # mode of EVERY path component
sudo -u www-data test -r /path && echo yes
sudo -u www-data -s -- sh -c 'cat /path'
stat -c '%A %U:%G %n' file
getfacl file
```

`namei -l` is the fastest diagnostic for a permission error, because the
failure is usually a missing `x` on an intermediate directory rather than
anything about the file:

```
$ namei -l /srv/app/data/file.txt
f: /srv/app/data/file.txt
 drwxr-xr-x root   root   /
 drwxr-xr-x root   root   srv
 drwx------ deploy deploy app      <-- other users cannot traverse here
 drwxr-xr-x deploy deploy data
 -rw-r--r-- deploy deploy file.txt
```

## ACL semantics

```bash
getfacl file
setfacl -m u:alice:rw file
setfacl -m g:auditors:r file
setfacl -m o::--- file
setfacl -x u:alice file
setfacl -b file                    # strip all ACLs

# Defaults: inherited by newly created entries in this directory.
setfacl -d -m u:deploy:rwx /srv/app
setfacl -d -m g:developers:rx /srv/app

# Apply to existing content and set defaults in one pass.
setfacl -R -m u:deploy:rwX /srv/app
setfacl -R -d -m u:deploy:rwX /srv/app

# Copy an ACL between files.
getfacl source | setfacl --set-file=- target
```

**The mask.** Any ACL beyond the base entries introduces a `mask::` entry that
caps every named user and group entry. Effective permissions are the AND of
the entry and the mask:

```
user:alice:rwx          #effective:r--
mask::r--
```

`chmod g+w` on an ACL-bearing file changes the **mask**, not the group entry —
this quietly changes effective permissions for every named entry. Check the
mask whenever an ACL "does not work":

```bash
getfacl file | grep mask
setfacl -m m::rwx file
```

The `+` suffix in `ls -l` (`-rw-rw----+`) indicates an ACL is present.

Requirements: the filesystem must support ACLs (ext4, xfs do by default) and
be mounted with `acl` on older kernels. `cp` drops ACLs unless given `-p` or
`--preserve=all`; `rsync` needs `-A`. `tar` needs `--acls`.

## Capabilities: setuid without setuid

File capabilities grant a specific privilege instead of full root:

```bash
getcap /usr/bin/ping
setcap cap_net_bind_service=+ep /usr/local/bin/myserver   # bind ports < 1024
setcap cap_net_raw+ep /usr/local/bin/mytool               # raw sockets
getcap -r / 2>/dev/null                                   # audit everything
```

Prefer this over setuid root: `cap_net_bind_service` on a binary is a far
smaller blast radius than making it run as root. Note that capabilities are
lost when a file is copied or rewritten, so they must be reapplied on deploy.

## Immutable and append-only attributes

```bash
lsattr file
chattr +i file        # immutable: cannot be modified, deleted, or renamed
chattr +a file        # append-only: useful for audit logs
chattr -i file        # remove
```

`+i` blocks even root until removed. It is occasionally the cause of an
inexplicable "operation not permitted" as root — check `lsattr` when
permissions look correct but writes still fail.

## Extended attributes

```bash
getfattr -d file             # user namespace
getfattr -d -m - file        # all namespaces including security.*
setfattr -n user.comment -v "text" file
```

SELinux labels live in `security.selinux`. On RHEL-family systems a
permission error with correct Unix modes is usually SELinux:

```bash
getenforce
ls -Z file
ausearch -m avc -ts recent
restorecon -Rv /srv/app
```

Check `getenforce` before spending time on modes when a distribution ships
SELinux enforcing.
