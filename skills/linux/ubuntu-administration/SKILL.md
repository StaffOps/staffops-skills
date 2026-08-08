---
name: ubuntu-administration
description: "Manage packages, users, network and updates on Ubuntu."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [ubuntu, apt, dpkg, netplan, ufw, cloud-init, users, debian, apparmor]
    category: linux
    related_skills: [linux-filesystem, linux-process-management, systemd-services]
---
# Ubuntu Administration

Package management with `apt`/`dpkg`, user and group administration, Netplan
networking, `ufw`, unattended upgrades, and `cloud-init` — the parts of
day-to-day Ubuntu server administration that differ from a generic Linux
skill. Debian-derived, so most of this applies to Debian directly too.

## When to Use

Use when installing or holding back a package, debugging a broken `apt`
state, adding a service account, configuring a static IP with Netplan,
opening a port with `ufw`, chasing a permission denial that looks correct at
the Unix level, or working through `cloud-init` on first boot.

## Package management

```bash
apt update                          # refresh the package index (not upgrade)
apt list --upgradable
apt upgrade                         # safe: never removes packages
apt full-upgrade                    # may remove packages to resolve deps
apt install pkg=1.2.3-1              # a specific version
apt install ./local-package.deb      # a local .deb, with dependency resolution
apt remove pkg                       # keep config files
apt purge pkg                        # remove config files too
apt autoremove                       # drop orphaned dependencies
apt autoremove --purge
```

`apt` is the front end meant for humans (progress bars, confirmation
prompts); `apt-get`/`apt-cache` are meant for scripts, with stable output
across versions. Prefer `apt-get` in automation:

```bash
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq pkg
```

`DEBIAN_FRONTEND=noninteractive` prevents a package's postinst script from
opening an interactive prompt and hanging a script or CI job. Always pair it
with `-y`.

### Inspecting packages

```bash
dpkg -l | grep pkg                  # installed, with version
dpkg -L pkg                         # every file the package installed
dpkg -S /usr/bin/something          # which package owns this file
apt-cache policy pkg                # installed vs candidate version, and WHICH repo
apt-cache depends pkg               # dependencies
apt-cache rdepends pkg              # reverse dependencies -- what needs this
apt show pkg                        # description, size, maintainer
apt-file search /usr/bin/something  # find the package for an uninstalled file
```

`apt-cache policy` is the tool for "why did the wrong version install" — it
shows every source offering the package and their priorities.

### Holding a package

```bash
apt-mark hold pkg                   # exclude from upgrade/full-upgrade
apt-mark unhold pkg
apt-mark showhold
```

Holds are the correct way to pin a package version through a known-bad
upstream release without disabling updates for everything else.

### Fixing a broken apt state

```bash
apt --fix-broken install            # resolve dependency problems
dpkg --configure -a                 # finish interrupted postinst scripts
rm /var/lib/dpkg/lock-frontend      # ONLY if certain nothing else holds it
lsof /var/lib/dpkg/lock-frontend    # check first -- see what actually holds it
apt clean                           # clear the downloaded .deb cache
```

`E: Could not get lock /var/lib/dpkg/lock-frontend` almost always means
another `apt`/`dpkg`/`unattended-upgrade` process is genuinely running —
check with `lsof` or `ps aux | grep -E 'apt|dpkg'` before removing the lock
file. Removing a lock held by a live process corrupts the package database.

### Repositories

```bash
cat /etc/apt/sources.list
ls /etc/apt/sources.list.d/
add-apt-repository ppa:someone/ppa
add-apt-repository --remove ppa:someone/ppa
apt-key list                        # legacy; modern repos use signed-by=
```

Modern Ubuntu (22.04+) prefers per-repo keyrings over the deprecated global
`apt-key`:

```
# /etc/apt/sources.list.d/example.list
deb [signed-by=/usr/share/keyrings/example.gpg] https://repo.example.com/ubuntu jammy main
```

```bash
curl -fsSL https://repo.example.com/key.gpg | gpg --dearmor -o /usr/share/keyrings/example.gpg
```

## Unattended upgrades

```bash
cat /etc/apt/apt.conf.d/50unattended-upgrades
systemctl status unattended-upgrades.service
unattended-upgrade --dry-run -d      # simulate, verbose
cat /var/log/unattended-upgrades/unattended-upgrades.log
```

Key settings:

```
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
};
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::Automatic-Reboot-Time "02:00";
```

Check whether a reboot is pending after kernel or libc updates:

```bash
test -f /var/run/reboot-required && cat /var/run/reboot-required
cat /var/run/reboot-required.pkgs 2>/dev/null
```

## Users and groups

```bash
useradd -m -s /bin/bash -c "Full Name" username    # -m creates the home dir
useradd -r -s /usr/sbin/nologin svcaccount           # system/service account
usermod -aG docker username                          # ADD to a group (-a is critical)
usermod -L username                                  # lock the password
passwd -l username                                   # equivalent lock
userdel -r username                                   # remove, including home dir
groupadd developers
gpasswd -a username developers
id username
groups username
getent passwd username                                # works with LDAP/SSSD too
```

**`usermod -G` without `-a` replaces the user's entire group list** — a
frequent way to accidentally revoke every other group membership:

```bash
usermod -G docker deploy      # WRONG: deploy is now ONLY in the docker group
usermod -aG docker deploy     # correct: docker is ADDED to existing groups
```

`-r` for a service account creates it with a UID below `SYS_UID_MAX` (usually
999) and skips creating a home directory or mail spool.

### sudo

```bash
visudo                              # always -- validates syntax before saving
visudo -f /etc/sudoers.d/myapp      # edit a drop-in instead
```

```
# /etc/sudoers.d/deploy
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart myapp
```

Never edit `/etc/sudoers` directly with a plain editor — a syntax error there
can lock out `sudo` entirely. `visudo` parses before saving and refuses to
write a broken file. Prefer a scoped `/etc/sudoers.d/` file over widening
`/etc/sudoers` itself.

## Networking with Netplan

Ubuntu 18.04+ configures networking through YAML consumed by either
`systemd-networkd` or NetworkManager.

```yaml
# /etc/netplan/01-netcfg.yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      dhcp4: false
      addresses:
        - 192.168.1.10/24
      routes:
        - to: default
          via: 192.168.1.1
      nameservers:
        addresses: [1.1.1.1, 8.8.8.8]
```

```bash
netplan generate                # render without applying -- syntax check
netplan try                     # apply with an automatic 120s rollback
netplan apply                   # apply immediately, no rollback
ip addr show
ip route show
resolvectl status               # DNS resolution status
```

**Always use `netplan try` for a remote host.** If the new configuration
breaks connectivity, it reverts automatically after the timeout; `netplan
apply` over SSH can lock you out permanently with no way back in except
console access.

File permissions matter: Netplan **warns** (not silently) when a YAML file is
group- or world-readable, because it may contain WiFi passwords — the file is
still applied, but `netplan generate`/`apply` prints
`Permissions ... are too open` to stderr. Set `chmod 600 /etc/netplan/*.yaml`
to silence it; do not mistake the warning for a functional problem when
troubleshooting a config that "does nothing" — check the actual generated
output in `/run/systemd/network/` instead.

## Firewall (ufw)

```bash
ufw status verbose
ufw allow 22/tcp
ufw allow from 10.0.0.0/8 to any port 5432
ufw allow proto tcp from any to any port 80,443
ufw delete allow 22/tcp
ufw enable
ufw disable
ufw logging on
```

`ufw` is a friendlier front end over `nftables`/`iptables`. Enabling it
**before** confirming an SSH rule exists locks out a remote session
immediately — always add the SSH rule first:

```bash
ufw allow OpenSSH      # requires openssh-server installed (registers this app profile)
ufw allow 22/tcp       # always available, no dependency on a profile
ufw enable
```

`ufw allow OpenSSH` fails with `Could not find a profile matching 'OpenSSH'`
on any host where `openssh-server` is not installed — the app profile comes
from that package (`/etc/ufw/applications.d/openssh-server`), not from `ufw`
itself. `ufw app list` shows which profiles actually exist on the current
host; `ufw allow 22/tcp` has no such dependency and works everywhere.

For anything beyond simple allow/deny rules, work with `nftables` directly —
see the `linux-firewall` skill.

## AppArmor

Ubuntu's default mandatory access control (Ubuntu ships AppArmor, not
SELinux — the reverse of RHEL/Fedora). It confines individual binaries to a
profile of allowed file paths, capabilities, and network access, independent
of the Unix permission model.

```bash
aa-status                           # loaded profiles, and enforce vs complain mode
aa-status --enabled; echo $?        # exit 0 if AppArmor is enabled at all
systemctl status apparmor           # the service that loads profiles at boot
```

A denial produces a normal-looking permission error from the *application*
(`Permission denied` with correct Unix modes and no ACL) while the real
cause is in the kernel audit log, not in anything `ls -l` shows:

```bash
dmesg -T | grep -i apparmor
journalctl -k | grep -i apparmor
grep -i denied /var/log/syslog /var/log/kern.log 2>/dev/null
```

```
audit: type=1400 audit(...): apparmor="DENIED" operation="open"
profile="/usr/sbin/mysqld" name="/data/mysql/custom.cnf" pid=1234 comm="mysqld"
```

The `profile=` and `name=` fields identify the confined binary and the exact
path it was denied. Diagnose Unix permissions first (`namei -l`, see
`linux-filesystem`) — only check AppArmor once those look correct and the
denial persists.

```bash
aa-complain /etc/apparmor.d/usr.sbin.mysqld   # log denials instead of enforcing -- for diagnosis
aa-enforce /etc/apparmor.d/usr.sbin.mysqld    # back to enforcing
aa-logprof                                     # interactively add rules from recent denials
```

Profiles live in `/etc/apparmor.d/`, one file per confined binary (path
separators become dots: `/usr/sbin/mysqld` → `usr.sbin.mysqld`). Editing a
profile requires reloading it:

```bash
apparmor_parser -r /etc/apparmor.d/usr.sbin.mysqld
```

Snap packages carry their own bundled AppArmor profiles, generated per
snap and largely opaque to manual editing — a permission problem inside a
snap is usually a packaging issue, not something to fix by hand-editing its
profile.

## cloud-init

Handles first-boot configuration on cloud images (EC2, GCE, Azure,
OpenStack, and most VM images).

```bash
cloud-init status --long
cloud-init analyze show           # timing breakdown of each stage
cat /var/log/cloud-init.log
cat /var/log/cloud-init-output.log   # stdout/stderr of user-data scripts
```

```yaml
#cloud-config
users:
  - name: deploy
    groups: sudo
    shell: /bin/bash
    sudo: 'ALL=(ALL) NOPASSWD:ALL'
    ssh_authorized_keys:
      - ssh-ed25519 AAAA...

package_update: true
packages:
  - nginx
  - curl

runcmd:
  - systemctl enable --now nginx

write_files:
  - path: /etc/myapp/config.yaml
    content: |
      key: value
    permissions: '0644'
```

`runcmd` runs once, on first boot only. Re-running `cloud-init` on an
already-initialized instance is a no-op unless the instance ID changes (a
common surprise when cloning a VM — clean `/var/lib/cloud` to force
re-initialization on the clone).

```bash
cloud-init clean --logs         # reset state; NEXT boot re-runs cloud-init
cloud-init devel schema --config-file user-data.yaml   # validate before use
```

## System information

```bash
lsb_release -a                      # Ubuntu version and codename
cat /etc/os-release
uname -r                            # kernel version
apt list --installed 'linux-image*' # installed kernels
dpkg-query -W -f='${Status} ${Package} ${Version}\n' | grep '^install ok'
hostnamectl                         # hostname, OS, kernel, virtualization
timedatectl                         # time, timezone, NTP sync status
```

## Pitfalls

- **`usermod -G` without `-a`** — wipes every other group membership.
- **`ufw enable` before an SSH rule exists** — immediate remote lockout.
- **`netplan apply` on a remote host** — no rollback if it breaks
  connectivity; use `netplan try`.
- **Deleting `/var/lib/dpkg/lock-frontend` while apt/dpkg is genuinely
  running** — corrupts the package database.
- **Editing `/etc/sudoers` directly** — a syntax error can disable `sudo`
  system-wide. Always `visudo`.
- **World-readable Netplan YAML** — silently ignored by design.
- **Assuming `apt upgrade` removes packages when needed** — it does not; use
  `full-upgrade` when a dependency change requires removal.
- **Forgetting `DEBIAN_FRONTEND=noninteractive`** — a postinst prompt hangs
  automation indefinitely.
- **Debugging a "permission denied" purely at the Unix level** — with correct
  owner/group/mode and no ACL, check `dmesg` for an AppArmor `DENIED` line
  before assuming the application itself is wrong.

## Verification

```bash
apt-get update -qq && echo "repos reachable"
dpkg --configure -a && apt --fix-broken install
netplan generate                    # syntax check without applying
netplan try                         # apply with automatic rollback
ufw status verbose
aa-status --enabled && echo "AppArmor enforcing profiles"
systemctl is-active unattended-upgrades.service
cloud-init status --long
test -f /var/run/reboot-required && echo "reboot pending"
```

`scripts/apt-audit.sh` reports held packages, pending reboots, broken
dependency state, and outdated repository keys in one pass.

## Reference

- `references/apt-internals.md` — pinning, sources.list.d, dpkg states
- `references/netplan-schema.md` — Netplan YAML reference with worked examples
- `scripts/apt-audit.sh` — package/update/reboot state in one report

## When NOT to use

- **RHEL/CentOS/Amazon Linux specifics** (yum, dnf, rpm) — this skill is Debian/Ubuntu focused.
- **Kernel tuning or low-level performance** — see [linux-performance-analysis](../linux/linux-performance-analysis/SKILL.md).
- **Container image builds** — for minimal images use apko/melange, not apt inside containers.


## Decision tree

```
What admin task?
├── Install / manage packages?
│   ├── From official repo → apt install PKG
│   ├── Specific version → apt install PKG=VERSION
│   ├── External repo → add-apt-repository / PPA, then apt update
│   ├── Remove cleanly → apt purge PKG + apt autoremove
│   └── Broken deps → apt --fix-broken install
├── Manage users / groups?
│   ├── New user → adduser NAME (interactive) or useradd -m -s /bin/bash
│   ├── Add to group → usermod -aG GROUP USER (re-login required)
│   ├── Disable account → usermod -L USER or passwd -l USER
│   └── Sudo access → usermod -aG sudo USER or /etc/sudoers.d/
├── Configure networking?
│   ├── View current → ip addr, ip route, resolvectl status
│   ├── Change config → edit /etc/netplan/*.yaml + netplan apply
│   ├── Temporary → ip addr add/del (lost on reboot)
│   └── DNS → edit netplan nameservers or systemd-resolved
└── Security hardening?
    ├── Firewall → ufw enable, ufw allow 22/tcp, ufw status
    ├── SSH → disable PasswordAuthentication, disable root login
    ├── Updates → unattended-upgrades for security patches
    └── Audit → check /var/log/auth.log, lastlog, faillog
```

## Related skills

- [systemd-services](../linux/systemd-services/SKILL.md) — service management, journald.
- [linux-filesystem](../linux/linux-filesystem/SKILL.md) — permissions, mounts, disk usage.
- [linux-command-line](../linux/linux-command-line/SKILL.md) — shell mechanics, pipes, find.
- [bash-scripting](../shell/bash-scripting/SKILL.md) — automating admin tasks.
