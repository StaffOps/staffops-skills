---
name: linux-security-auditing
description: "Audit a Linux host for common misconfigurations."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [audit, security-scan, setuid, world-writable, cve, lynis]
    category: security
    related_skills: [linux-hardening, ssh-hardening]
---
# Linux Security Auditing

A checklist and toolset for auditing a Linux host's current security
posture: finding overly permissive files, stale accounts, listening
services that shouldn't be there, and outdated packages with known CVEs.
Complements `linux-hardening` (applying a baseline) — this is about
verifying and finding drift from it.

## When to Use

Use when auditing a host before or after it goes into production,
investigating a suspected compromise, responding to a compliance
requirement, or periodically verifying a hardening baseline hasn't drifted.

## Users and accounts

```bash
awk -F: '$3 == 0 {print}' /etc/passwd          # every account with UID 0 -- should be ONLY root
awk -F: '($3 >= 1000) {print $1}' /etc/passwd   # regular (non-system) user accounts
awk -F: '$2 == "" {print $1}' /etc/shadow       # accounts with NO password set at all (as root)
lastlog -b 90                                    # accounts unused in the last 90 days
```

**More than one UID-0 account is an immediate finding** — a second account
with root's UID is functionally a hidden root account, regardless of what
name it has, and is a classic backdoor pattern.

```bash
grep -v '/nologin\|/false' /etc/passwd | awk -F: '{print $1, $7}'   # accounts with an interactive shell
```

Service accounts (for applications, daemons) should have a non-login shell
(`/usr/sbin/nologin` or `/bin/false`) — a service account with `/bin/bash`
that doesn't need interactive access is unnecessary risk if that account is
ever compromised.

## sudo and privilege escalation paths

```bash
cat /etc/sudoers
ls -la /etc/sudoers.d/
sudo -l -U someuser              # what a specific user can actually run
```

```bash
find / -xdev -perm -4000 -type f 2>/dev/null    # every setuid binary
find / -xdev -perm -2000 -type f 2>/dev/null    # every setgid binary
```

Compare the setuid/setgid list against a known-good baseline for the
distribution — an *unexpected* setuid binary (something not part of the
standard package set) is a significant finding worth investigating
immediately; it's a common privilege-escalation vector.

```bash
# NOPASSWD sudo entries -- worth specific scrutiny, especially for
# broad commands rather than a narrowly scoped one.
grep -r NOPASSWD /etc/sudoers /etc/sudoers.d/ 2>/dev/null
```

A `NOPASSWD: ALL` entry means that account (or anyone who compromises it)
gets unrestricted root with no additional authentication step — reasonable
for a tightly scoped automation account with its own strong protections,
a serious finding for a general user account.

## File permissions

```bash
find / -xdev -perm -o+w -type f 2>/dev/null      # world-writable files
find / -xdev -perm -o+w -type d ! -perm -1000 2>/dev/null   # world-writable dirs WITHOUT the sticky bit
find / -xdev -nouser -o -nogroup 2>/dev/null      # orphaned ownership -- UID/GID with no matching account
```

A world-writable directory without the sticky bit lets any user delete or
replace *any other user's* files in it — see `linux-filesystem`'s
permissions reference for why the sticky bit specifically matters here.
Orphaned ownership (a file owned by a UID that no longer maps to any
account) is often leftover from a deleted user and worth investigating —
occasionally it's evidence of an account that was deliberately removed to
hide activity.

```bash
find / -xdev -name "*.pem" -o -name "*.key" 2>/dev/null | xargs -I{} sh -c 'stat -c "%a %n" "{}"'
```

Private key files should be `600` (owner read/write only) — anything looser
found during an audit is a direct, immediately actionable finding.

## Listening services

```bash
ss -tlnp
ss -ulnp
```

Compare against an expected/documented list for the host's actual role —
anything unexpected listening is worth investigating: is it a legitimate
service someone forgot to document, or something that shouldn't be there at
all.

```bash
systemctl list-unit-files --state=enabled | grep -v '^UNIT'
```

Every enabled service is attack surface — flag anything not required for
the host's documented purpose.

## Package and CVE auditing

```bash
apt list --upgradable 2>/dev/null | grep -i security     # Debian/Ubuntu
dnf updateinfo list security                                # RHEL family

# Distribution-specific vulnerability scanners.
debsecan                    # Debian
dnf list-security            # RHEL, alternate form
```

For container images specifically, a dedicated scanner (Trivy, Grype) gives
much more precise CVE-to-package mapping than checking the OS package
manager alone — see `sbom-vulnerability-management` for that workflow in
depth.

```bash
uname -r                                    # running kernel version
apt list --installed 'linux-image*'          # installed kernel packages -- may be newer than running!
test -f /var/run/reboot-required && echo "reboot needed to run the patched kernel"
```

A patched kernel package being *installed* doesn't mean it's *running* —
without a reboot, the host remains vulnerable to whatever the update fixed,
while `apt`/`dpkg` correctly report the package as up to date. This
distinction is a common gap between "patched" as reported by a package
manager and "patched" as actually true of the running system.

## Network exposure

```bash
nft list ruleset 2>/dev/null || iptables -L -n -v    # current firewall rules
ss -tlnp                                                # combined with the above: what's listening AND what's reachable
```

The combination matters: a service listening on `127.0.0.1` is not exposed
externally regardless of firewall rules; a service listening on `0.0.0.0`
with no firewall rule restricting access is fully exposed. Check both
together, not either alone.

## Log and audit trail integrity

```bash
journalctl --verify                    # check for gaps/tampering in the journal
ls -la /var/log/                        # unexpected permission changes on log files themselves
auditctl -l                              # active audit rules, if auditd is in use (see linux-hardening)
```

Logs that have been truncated, have unusual gaps, or have had their
permissions loosened are themselves a significant finding, independent of
what they do or don't show — an attacker with sufficient access frequently
targets logs specifically to cover their tracks.

## Automated scanning tools

```bash
lynis audit system --quick        # broad hardening/security scan, human-readable report
```

Lynis and similar tools are useful for **coverage** — catching the long tail
of checks a manual pass might skip — but every finding needs judgment
applied before acting on it; not every suggestion is relevant to every
host's actual role and threat model. Use scanner output as an input to
review, not a checklist to blindly execute.

## A structured audit checklist

```
[ ] Only one UID-0 account (root)
[ ] No accounts with an empty password field
[ ] Service accounts have a non-login shell
[ ] setuid/setgid binaries match the expected distribution baseline
[ ] No unexplained NOPASSWD sudo entries
[ ] No world-writable files/directories outside expected locations (/tmp, /dev/shm)
[ ] No orphaned file ownership
[ ] Private key files are mode 600
[ ] Listening services match the documented expected set
[ ] No unnecessary enabled services
[ ] No outstanding security updates; running kernel matches installed kernel
[ ] Firewall rules match documented intent
[ ] Log/journal integrity intact, no unusual gaps
```

## Pitfalls

- **Treating a package manager's "up to date" as proof the running system
  is patched** — a kernel update requires a reboot to actually take effect.
- **Finding a second UID-0 account and not treating it as urgent** — it is
  functionally a hidden root account regardless of its name.
- **Auditing file permissions but not checking `nouser`/`nogroup`
  ownership** — orphaned ownership is an easy, high-value check that's
  often skipped.
- **Running an automated scanner and applying every finding without
  judgment** — many are situational; evaluate against the host's actual
  role.
- **Checking listening services OR firewall rules, not both together** —
  the actual exposure depends on the combination.
- **Not distinguishing a documented, tightly-scoped `NOPASSWD` entry from
  an unexplained broad one** — context determines whether it's a finding.

## Reference

- `linux-hardening` — the baseline this auditing verifies
- `ssh-hardening` — SSH-specific configuration to audit against
- `linux-filesystem` — the permission model underlying several checks here
