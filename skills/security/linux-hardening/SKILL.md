---
name: linux-hardening
description: "Apply baseline OS hardening: sysctl, PAM, mounts, kernel."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [hardening, cis, sysctl, pam, kernel, aslr, mount-options]
    category: security
    related_skills: [ssh-hardening, linux-security-auditing, linux-firewall]
---
# Linux Hardening

Baseline OS-level hardening: kernel parameters (`sysctl`), mount options,
PAM password/lockout policy, and disabling unnecessary services and kernel
modules. This is host-level hardening specifically — `ssh-hardening` and
`linux-firewall` cover two specific, larger subtopics in depth.

## When to Use

Use when building a hardened base image, responding to a CIS benchmark or
compliance audit finding, or reviewing a host's baseline security posture
before it goes into production.

## Kernel network parameters (sysctl)

```
# /etc/sysctl.d/99-hardening.conf

# Disable IP forwarding unless this host is genuinely a router.
net.ipv4.ip_forward = 0

# Reject source-routed packets (an old spoofing/routing-bypass technique).
net.ipv4.conf.all.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0

# Don't send/accept ICMP redirects -- a host has no business rewriting routes.
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0

# Reverse-path filtering: drop packets whose source wouldn't route back
# out the interface they arrived on. Strong anti-spoofing measure.
net.ipv4.conf.all.rp_filter = 1

# Log packets with impossible/spoofed source addresses.
net.ipv4.conf.all.log_martians = 1

# SYN flood mitigation.
net.ipv4.tcp_syncookies = 1

# Ignore broadcast ICMP (mitigates smurf-style amplification).
net.ipv4.icmp_echo_ignore_broadcasts = 1
```

```bash
sysctl -p /etc/sysctl.d/99-hardening.conf     # apply immediately
sysctl net.ipv4.ip_forward                     # verify a single value
```

`ip_forward = 0` is the one most likely to break something if applied
carelessly — it's *correct* for an ordinary host, but a genuine router, NAT
gateway, or Kubernetes node (which needs forwarding for pod networking) must
keep it enabled. Know what the host's actual role is before applying a
blanket hardening template.

## Kernel-level protections

```
# /etc/sysctl.d/99-hardening.conf (continued)

# Address Space Layout Randomization -- makes memory-corruption exploits
# significantly harder. 2 = full randomization.
kernel.randomize_va_space = 2

# Restrict access to kernel pointers in /proc -- prevents using them to
# defeat ASLR from an unprivileged process.
kernel.kptr_restrict = 1

# Restrict dmesg to privileged users -- kernel logs can leak addresses
# and other information useful to an attacker.
kernel.dmesg_restrict = 1

# Restrict ptrace to a process's own children (or CAP_SYS_PTRACE) --
# limits one process's ability to inspect/inject into another.
kernel.yama.ptrace_scope = 1

# Disallow unprivileged users from creating user namespaces, a common
# stepping stone in container-escape and local-privilege-escalation chains.
# NOTE: this breaks rootless Docker/Podman if the host needs to run them.
kernel.unprivileged_userns_clone = 0
```

The `unprivileged_userns_clone` setting is the clearest example of hardening
that's a genuine trade-off, not a free win — verify the host doesn't need
rootless containers before disabling it, or scope the restriction more
narrowly.

## Filesystem mount hardening

```
# /etc/fstab entries
tmpfs  /tmp      tmpfs  defaults,nosuid,nodev,noexec  0  0
tmpfs  /dev/shm  tmpfs  defaults,nosuid,nodev,noexec  0  0
```

| Option | Prevents |
| --- | --- |
| `nosuid` | setuid/setgid bits taking effect on this filesystem |
| `nodev` | Device nodes being interpreted as devices |
| `noexec` | Binaries being executed directly from this filesystem |

`/tmp` and `/dev/shm` are world-writable by design, which makes them the
conventional place to drop and execute a malicious binary if an application
allows writing there — `noexec` specifically closes that path. Verify no
legitimate application relies on executing something from `/tmp` before
applying this broadly (some install scripts and language runtimes
occasionally do, though it's poor practice on their part).

## PAM: password and lockout policy

```
# /etc/security/pwquality.conf
minlen = 14
dcredit = -1        # require at least 1 digit
ucredit = -1        # require at least 1 uppercase
ocredit = -1        # require at least 1 special character
retry = 3
```

```
# /etc/pam.d/common-auth (Debian/Ubuntu) or /etc/pam.d/system-auth (RHEL)
auth required pam_faillock.so preauth silent deny=5 unlock_time=900
auth required pam_faillock.so authfail deny=5 unlock_time=900
```

`pam_faillock` (the modern replacement for the older `pam_tally2`) locks an
account after repeated failed attempts — `deny=5 unlock_time=900` allows 5
attempts before a 15-minute lockout. This is specifically about mitigating
online brute-force against local/password authentication; for SSH
specifically, key-based auth with password auth disabled (covered in
`ssh-hardening`) is the more robust control, and faillock is defense in
depth for whatever still uses PAM-based auth on the host.

```bash
faillock --user someuser              # check an account's current lockout status
faillock --user someuser --reset       # clear it
```

## Disabling unnecessary kernel modules

```bash
lsmod | wc -l                                    # what's currently loaded
cat /etc/modprobe.d/hardening.conf 2>/dev/null    # existing blacklist, if any
```

```
# /etc/modprobe.d/hardening.conf
install cramfs /bin/false
install freevxfs /bin/false
install usb-storage /bin/false     # blocks USB mass storage specifically
```

Blacklisting rarely-used or legacy filesystem modules (`cramfs`,
`freevxfs`, `hfs`, `squashfs` if genuinely unused) reduces kernel attack
surface — these are old, less-audited codepaths that a system rarely
actually needs loaded. `usb-storage` is specifically relevant for physical
servers/workstations where blocking USB mass-storage devices is an explicit
policy goal; irrelevant for a cloud VM with no USB ports.

## Auditd: making changes observable

```bash
systemctl status auditd
auditctl -l                          # currently loaded rules
```

```
# /etc/audit/rules.d/hardening.rules
-w /etc/passwd -p wa -k identity
-w /etc/shadow -p wa -k identity
-w /etc/sudoers -p wa -k privilege_escalation
-w /etc/ssh/sshd_config -p wa -k sshd_config
```

`-w` watches a file for the specified access types (`w`rite, `a`ttribute
change); `-k` tags matching events with a searchable key. Hardening a
system's *configuration* is only half the goal — being able to prove (via
audit logs) that it stayed hardened, and see exactly what changed and when
if it didn't, is the other half.

```bash
ausearch -k identity              # find every logged change to watched identity files
ausearch -k privilege_escalation --start today
```

## Removing/disabling unnecessary services

```bash
systemctl list-unit-files --state=enabled       # everything set to start at boot
systemctl disable --now avahi-daemon.service     # example: mDNS, rarely needed on a server
```

Every enabled service is both attack surface and a maintenance burden
(patching, monitoring). The general principle: a server should run what it
needs and nothing it doesn't — desktop-oriented services (mDNS/Avahi,
Bluetooth, CUPS printing) are common and safe candidates for disabling on a
headless server, but verify against the specific host's actual role before
applying a blanket list.

## Automated benchmarking tools

```bash
# CIS benchmark scanning (various tools implement this).
lynis audit system            # broad, general-purpose hardening scanner
```

Automated scanners are useful for **breadth** (catching things a manual
checklist misses) but produce findings that need judgment to apply — many
CIS benchmark items are genuinely situational (a control appropriate for a
workstation may be actively wrong for a container host or a Kubernetes
node). Treat scanner output as a checklist to evaluate, not a list of
commands to run unconditionally.

## Pitfalls

- **Applying a hardening template without checking the host's actual
  role** — `ip_forward=0` is correct almost everywhere except the router/NAT
  gateway/Kubernetes node it will break.
- **`noexec` on `/tmp` breaking a legitimate installer or runtime** that
  relies on executing there — verify before broad rollout.
- **Disabling `unprivileged_userns_clone`** on a host that needs rootless
  containers.
- **Hardening configuration without auditd watching it** — no way to detect
  or prove it stayed hardened afterward.
- **Treating an automated scanner's full output as a mandatory checklist**
  — many findings are genuinely situational and need judgment, not blind
  application.
- **Forgetting `sysctl -p` (or a reboot) after editing sysctl config
  files** — the change exists on disk but isn't actually applied yet.

## Reference

- `ssh-hardening` — SSH-specific configuration in depth
- `linux-security-auditing` — verifying and continuously checking this baseline
- `linux-firewall` — network-layer controls, a separate and complementary layer
