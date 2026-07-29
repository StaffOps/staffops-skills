# apt/dpkg Internals

## The layers

```
apt / apt-get / aptitude   <- dependency resolution, repository handling
        |
      dpkg                 <- installs/removes individual .deb files, no dependency resolution
        |
   /var/lib/dpkg/status    <- the actual database of installed package state
```

`dpkg` cannot resolve dependencies; it fails loudly if a `.deb` needs
something not installed. `apt` computes the dependency graph and calls `dpkg`
for the mechanical install/remove.

## Package states (dpkg -l column 1)

```
dpkg -l | head -5
```

```
Desired=Unknown/Install/Remove/Purge/Hold
| Status=Not/Inst/Conf-files/Unpacked/halF-conf/Half-inst/trig-aWait/Trig-pend
|/ Err?=(none)/Reinst-required (Status,Err: uppercase=bad)
||/ Name           Version          Architecture Description
+++-==============-================-============-=================
ii  nginx          1.24.0-1         amd64        small, powerful web server
```

Two-letter code: desired state / current status.

| Code | Desired | | Code | Status |
| --- | --- | --- | --- | --- |
| `i` | Install | | `i` | Installed |
| `r` | Remove | | `c` | Config files remain (removed, not purged) |
| `p` | Purge | | `U` | Unpacked, not configured |
| `h` | Hold | | `F` | Half-configured (failed mid-way) |
| | | | `H` | Half-installed |
| | | | `W` | Triggers awaited |
| | | | `t` | Triggers pending |

`rc` (remove/config-files) is common after `apt remove` without `--purge` —
the package is gone but its config remains in `/etc`. `iF` or `iH` indicates
an interrupted install; `dpkg --configure -a` resumes it.

```bash
dpkg -l | awk '$1 !~ /^ii/ { print }'      # anything not cleanly installed
dpkg -l | grep '^rc' | awk '{print $2}' | xargs -r dpkg --purge   # clean up all rc packages
```

## Version pinning

`/etc/apt/preferences.d/` controls which candidate version `apt` prefers,
independent of `apt-mark hold` (which is a full freeze).

```
# /etc/apt/preferences.d/pin-nginx
Package: nginx
Pin: version 1.24.*
Pin-Priority: 1001
```

| Priority | Effect |
| --- | --- |
| < 0 | Never installed |
| 1-99 | Only if no installed version exists |
| 100 | Default for an already-installed package's own archive |
| 500 | Default for a package not yet installed |
| 990 | `-t` target release default |
| 1001 | Force even a downgrade |

```bash
apt-cache policy nginx          # shows the resolved priority per source
apt-get install nginx -t stable  # prefer a specific release for this install only
```

Pinning is the correct tool for "always use this major version across
upgrades"; `apt-mark hold` is the correct tool for "never touch this package
at all until I unhold it".

## Sources

```bash
cat /etc/apt/sources.list
ls /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources 2>/dev/null
```

Ubuntu 24.04 introduced the DEB822 format (`.sources`, structured stanzas)
alongside the classic one-line `.list` format. Both work; DEB822 is the
default going forward.

```
# classic .list
deb [signed-by=/usr/share/keyrings/example.gpg] https://repo.example.com/ubuntu jammy main

# DEB822 .sources
Types: deb
URIs: https://repo.example.com/ubuntu
Suites: jammy
Components: main
Signed-By: /usr/share/keyrings/example.gpg
```

`signed-by=` (or `Signed-By:`) scopes a keyring to that single repository.
The deprecated `apt-key add` installed keys **globally**, letting any
repository sign for any package — avoid it on anything modern.

## Downloaded package cache

```bash
ls /var/cache/apt/archives/*.deb | wc -l
du -sh /var/cache/apt/archives/
apt-get clean         # removes everything
apt-get autoclean     # removes only packages no longer downloadable (superseded)
```

`apt-get clean` is safe at any time — it only removes the local `.deb` cache,
never installed packages.

## Locks

| Lock file | Held during |
| --- | --- |
| `/var/lib/dpkg/lock-frontend` | Any `apt`/`apt-get` operation |
| `/var/lib/dpkg/lock` | Any `dpkg` operation |
| `/var/cache/apt/archives/lock` | Downloading packages |

```bash
lsof /var/lib/dpkg/lock-frontend      # who holds it, before assuming it's stale
ps aux | grep -E 'apt|dpkg|unattended'
fuser -v /var/lib/dpkg/lock-frontend
```

Only remove a lock file after confirming via `lsof`/`ps` that nothing is
genuinely running — removing a live lock corrupts `/var/lib/dpkg/status`,
which then requires manual repair.

## Triggers

Some packages (notably `man-db`, `desktop-file-utils`, `libc-bin`) defer
expensive post-install work using dpkg triggers, batched across a
transaction:

```bash
dpkg --triggers-only --pending    # process any pending triggers manually
```

`Processing triggers for libc-bin ...` at the end of an `apt` run is this
mechanism — normal, not an error.

## Full dependency resolution failures

```bash
apt-get install -f              # attempt automatic repair
apt-get install pkg --fix-missing
aptitude install pkg            # a different SAT solver; sometimes succeeds where apt-get fails
apt-cache unmet                 # list unmet dependencies for ANY package, installed or not
```

`aptitude`'s resolver explores more of the solution space than `apt-get`'s
and occasionally finds a working combination when `apt-get` reports an
unresolvable conflict.

## Rebuilding a corrupted package database

Last resort, when `/var/lib/dpkg/status` itself is damaged:

```bash
cp /var/lib/dpkg/status /var/lib/dpkg/status.bak
cp /var/backups/dpkg.status.0 /var/lib/dpkg/status   # daily rotated backup
dpkg --configure -a
apt-get install -f
```

`/var/backups/dpkg.status.*` is rotated automatically by `dpkg` itself and is
the recovery path when the live file is corrupted.

## Useful one-liners

```bash
# Every manually-installed package (not pulled in as a dependency).
apt-mark showmanual

# Packages installed but no longer available in any configured repo.
apt list --installed 2>/dev/null | grep -v "^Listing" \
    | awk -F/ '{print $1}' | while read -r p; do
        apt-cache policy "$p" | grep -q "Candidate: (none)" && echo "$p"
    done

# Disk space used per top-level installed package.
dpkg-query -Wf '${Installed-Size}\t${Package}\n' | sort -rn | head -20

# All configuration files a package owns (vs binaries/docs).
dpkg -L pkg | xargs -I{} sh -c 'test -f "{}" && dpkg -S "{}" 2>/dev/null | grep -q conffile' 2>/dev/null

# Packages with an available security update.
apt list --upgradable 2>/dev/null | grep -i security
```
