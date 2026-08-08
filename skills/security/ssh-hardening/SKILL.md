---
name: ssh-hardening
description: "Configure SSH for key-only, restricted, auditable access."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [ssh, sshd, key-authentication, bastion, fail2ban, port-forwarding]
    category: security
    related_skills: [linux-hardening, linux-security-auditing]
---
# SSH Hardening

Configuring `sshd` for key-only authentication, restricting what a key can
do, and closing the specific misconfigurations that account for most SSH
security findings. Covers both server (`sshd_config`) and client-side key
hygiene.

## When to Use

Use when hardening a server's SSH configuration, setting up key-based
authentication for a fleet, restricting a deploy key's capabilities, or
responding to an SSH-related audit finding.

## When NOT to Use

- Ephemeral containers/pods that don't run sshd → no SSH to harden
- AWS SSM Session Manager replaces SSH entirely → no sshd needed
- Network-level ACLs or firewall rules → use `linux-firewall`

## The core sshd_config baseline

```
# /etc/ssh/sshd_config

PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
ChallengeResponseAuthentication no
KbdInteractiveAuthentication no

X11Forwarding no
AllowTcpForwarding no          # unless port forwarding is a genuine requirement
PermitTunnel no

MaxAuthTries 3
LoginGraceTime 30
ClientAliveInterval 300
ClientAliveCountMax 2
```

```bash
sshd -t                          # ALWAYS validate syntax before restarting sshd
systemctl restart sshd
```

**`sshd -t` before restarting is not optional** — a syntax error in
`sshd_config` combined with a restart can leave the SSH daemon refusing to
start entirely, and if that's the only access path to a remote host, this is
a hard lockout requiring console/IPMI access to recover from. Always
validate first.

## PermitRootLogin: the most consequential single setting

```
PermitRootLogin no
```

Disabling direct root login forces every session to authenticate as a named
user and elevate via `sudo` — this means every privileged action is
attributable to a specific person's audit trail, rather than an
undifferentiated "root" login that could be anyone with the key/password.
`PermitRootLogin prohibit-password` is a weaker but sometimes necessary
middle ground (root login only via key, never password) for specific
automation use cases — `no` is the stronger default and should be the
starting point.

## Password authentication: disable it, don't just discourage it

```
PasswordAuthentication no
```

With this set, a compromised or guessed password is worthless for SSH
access — only a private key (something possessed, not something known)
works. This single setting eliminates the entire class of online
brute-force/credential-stuffing attacks against SSH, which is why it matters
more than almost any other hardening step on this page.

Before disabling, **confirm at least one working key-based login already
succeeds** — testing in a second terminal session while the first remains
open is the safe verification pattern, so a mistake doesn't lock out the
only active session.

## Key types and generation

```bash
ssh-keygen -t ed25519 -C "name@host-purpose"
ssh-keygen -t rsa -b 4096 -C "name@host-purpose"    # only if ed25519 isn't supported somewhere in the chain
```

Ed25519 is the modern default: smaller keys, faster operations, and no
known weak-parameter class of issues that has historically affected some RSA
key generation implementations. RSA remains necessary only for
compatibility with older systems/hardware that don't support Ed25519 (some
older network appliances, certain HSMs) — verify that specific constraint
exists before defaulting to RSA.

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub
chmod 600 ~/.ssh/authorized_keys
chmod 600 ~/.ssh/config
```

SSH refuses to use a private key with overly permissive modes — see
`linux-filesystem`'s permissions reference for the exact required modes and
why `$HOME` itself must not be group/world-writable either.

## Restricting what a key can do (authorized_keys options)

Not every key needs full shell access — a key used only for a specific
automated task (a backup job, a CI deploy) should be restricted to exactly
that:

```
# ~/.ssh/authorized_keys
command="/opt/scripts/backup.sh",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA... backup-key
```

| Option | Effect |
| --- | --- |
| `command="..."` | Forces this command to run regardless of what the client requests — the single most powerful restriction |
| `no-port-forwarding` | Blocks using this connection as a tunnel |
| `no-agent-forwarding` | Blocks forwarding the client's SSH agent (a real lateral-movement risk if this host is compromised) |
| `no-pty` | No interactive terminal — appropriate for a purely automated key |
| `from="10.0.0.0/8"` | Restricts which source addresses may use this key at all |

A deploy key that only ever needs to run one script should have all of
these applied — it dramatically limits what an attacker who obtains that
specific private key can actually do, even though the key itself
authenticates successfully.

## Agent forwarding: understand the risk before enabling it

```
# Client-side, ~/.ssh/config
Host bastion
    ForwardAgent yes
```

Agent forwarding lets a *further* SSH hop (from the bastion onward) use your
local key without copying it to the intermediate host — convenient, but it
means **anyone with root on that intermediate host can use your forwarded
agent to authenticate as you, for as long as the forwarded session is
open**, without ever seeing the private key material itself. This is a real
and frequently underestimated risk on a shared or less-trusted jump host.

`ProxyJump` is the modern, generally safer alternative for the common
bastion-hop use case — it doesn't expose agent forwarding to the
intermediate host at all:

```
# ~/.ssh/config
Host internal-host
    ProxyJump bastion.example.com
    User deploy
```

```bash
ssh internal-host    # transparently hops through the bastion, no forwarding needed
```

## Fail2ban / rate limiting

```
# /etc/fail2ban/jail.local
[sshd]
enabled = true
maxretry = 4
bantime = 3600
findtime = 600
```

```bash
fail2ban-client status sshd
fail2ban-client set sshd unbanip 1.2.3.4
```

With `PasswordAuthentication no` already in place, `fail2ban` for SSH is
defense in depth rather than the primary control — brute force against key
auth isn't meaningfully attackable the way password guessing is. It remains
worth having for noise reduction (log volume, connection overhead from
scanners) and as a control for any host where password auth genuinely can't
be fully disabled yet.

## Client-side hygiene: known_hosts and host key verification

```bash
ssh-keyscan -t ed25519 host >> ~/.ssh/known_hosts    # add a host key OUT OF BAND, not by blindly accepting on first connect
```

```
Host *
    StrictHostKeyChecking yes
    VerifyHostKeyDNS yes
```

`StrictHostKeyChecking yes` (rejecting a connection when the host key
doesn't match what's already known, rather than silently accepting a new
one) is what actually makes host-key verification meaningful — the entire
point of SSH's host-key mechanism is defeated if a client is configured to
blindly trust whatever key a server presents on every connection, since
that's exactly the situation a machine-in-the-middle attack would produce.

## Auditing active sessions and key usage

```bash
who                                # currently logged-in sessions
last -a | head -20                  # recent login history, with source
journalctl -u sshd --since "-1h" | grep -i "accepted\|failed"
grep sshd /var/log/auth.log | grep "Accepted publickey" | tail -20   # non-systemd systems
```

For attributing which specific key was used (useful when multiple people or
automation share access, or when auditing after an incident):

```bash
journalctl -u sshd | grep "Accepted publickey" | grep -oP 'SHA256:\S+'
```

Comparing the fingerprint in the log against `ssh-keygen -lf
~/.ssh/id_ed25519.pub` identifies exactly which physical key was used for a
given login — valuable when several people have their own individual keys
rather than sharing one, which is itself a hardening practice worth
adopting for accountability.

## Decision tree

```
SSH hardening task?
├── New server setup?
│   ├── Disable password auth (PasswordAuthentication no)
│   ├── Disable root login (PermitRootLogin no)
│   ├── Restrict to key-based + limit AllowUsers/AllowGroups
│   └── Set idle timeout, max auth tries, restrict ciphers/MACs
├── Audit existing server?
│   ├── Review /etc/ssh/sshd_config against CIS SSH benchmarks
│   ├── Check authorized_keys for stale/unknown keys
│   ├── Verify: no forwarding unless needed, no empty passwords
│   └── Run: ssh-audit <host> for cipher/kex/MAC compliance
└── Incident response (suspected compromise)?
    ├── Check auth logs: grep sshd /var/log/auth.log | tail -100
    ├── List active sessions: who / ss -tnp | grep :22
    ├── Revoke suspected keys immediately
    └── Rotate host keys if server integrity is in doubt
```

## Pitfalls

- **Restarting `sshd` after an edit without `sshd -t` first** — a syntax
  error can lock out the only access path to a remote host.
- **Disabling password auth without confirming key auth already works** —
  test in a second session before closing the first.
- **Sharing one SSH key across multiple people/automation** — defeats
  per-actor audit attribution; issue individual keys.
- **Enabling `ForwardAgent` to a less-trusted intermediate host** without
  understanding that root there can use the forwarded agent as you.
- **A restricted deploy key without `command=`/`no-pty`/etc.** — a key
  scoped "for backups" that still has full interactive shell access if the
  private key is ever exposed.
- **`StrictHostKeyChecking no`** (or accepting host keys on first connect
  without out-of-band verification) — removes the actual protection host-key
  checking is meant to provide.

## Reference

- `linux-hardening` — broader OS-level hardening this complements
- `linux-security-auditing` — verifying this configuration stays correct over time
- `linux-filesystem` — the permission requirements SSH enforces on key files

## Related skills
- `linux-hardening` — broader OS hardening
- `linux-security-auditing` — verifying SSH config
- `tls-troubleshooting` — certificate issues with SSH keys
