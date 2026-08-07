---
name: linux-firewall
description: "Write and debug nftables/iptables firewall rules."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [nftables, iptables, firewall, netfilter, conntrack, drop, reject]
    category: networking
    related_skills: [tcp-ip-fundamentals, network-troubleshooting-tools, ubuntu-administration]
---
# Linux Firewall (nftables/iptables)

Netfilter-based packet filtering: the difference between `DROP` and
`REJECT`, how chains and tables actually get evaluated, stateful
connection tracking, and debugging a rule that isn't matching what you
expect. `nftables` is the modern replacement for `iptables`; both are
covered since `iptables` remains extremely common in existing systems.

## When to Use

Use when writing firewall rules, debugging why traffic is unexpectedly
blocked or unexpectedly allowed, choosing between `DROP` and `REJECT`, or
reading an existing ruleset to understand what it actually does.

## nftables vs iptables

```bash
nft list ruleset             # nftables: current rules
iptables -L -n -v             # iptables: current rules (legacy, but still everywhere)
iptables-nft -L -n -v         # iptables commands translated to nftables backend
update-alternatives --config iptables   # Debian/Ubuntu: check which backend is active
```

Modern distributions (Ubuntu 20.04+, RHEL 8+) use `nftables` as the actual
kernel packet-filtering engine by default, with `iptables` commands
transparently translated to it via `iptables-nft`. Tools like `ufw` and
`firewalld` are front ends generating nftables or iptables-nft rules
underneath — see `ubuntu-administration` for `ufw` specifically.

## Basic nftables structure

```bash
nft add table inet filter
nft add chain inet filter input { type filter hook input priority 0 \; policy drop \; }
nft add rule inet filter input ct state established,related accept
nft add rule inet filter input iif lo accept
nft add rule inet filter input tcp dport 22 accept
nft add rule inet filter input tcp dport { 80, 443 } accept
nft add rule inet filter input ip saddr 10.0.0.0/8 accept
```

```bash
nft list ruleset                # everything, current state
nft list table inet filter       # one table
nft -a list ruleset               # WITH rule handles -- needed to delete a specific rule
nft delete rule inet filter input handle 5
```

`inet` covers both IPv4 and IPv6 in one table — the modern approach,
replacing the need for separate `ip` (v4) and `ip6` (v6) tables/rulesets
unless dual-stack behavior genuinely needs to differ.

## Chain hooks and priority

| Hook | When it fires |
| --- | --- |
| `prerouting` | Before a routing decision — sees all traffic, even what's not for this host |
| `input` | Destined for this host |
| `forward` | Passing through this host (routing/NAT) |
| `output` | Originating from this host |
| `postrouting` | After a routing decision, about to leave |

A rule in `input` only sees traffic addressed to the local host; a router or
NAT gateway needs `forward` rules for traffic passing *through* it, which is
a common source of "the rule is right there, why isn't it matching" —
checking the wrong chain for the traffic's actual path.

## DROP vs REJECT

```bash
nft add rule inet filter input tcp dport 23 drop      # silent -- no response at all
nft add rule inet filter input tcp dport 23 reject     # sends an ICMP/TCP-RST response
```

| | `DROP` | `REJECT` |
| --- | --- | --- |
| Client sees | Nothing — connection hangs until it times out | Immediate refusal (ICMP unreachable or TCP RST) |
| Information leaked | Minimal — attacker can't easily tell if a host exists | Confirms the host exists and is filtering |
| Client experience | Slow failure (times out) | Fast failure (immediate error) |

`DROP` is the conventional default for perimeter/internet-facing rules
(minimizes information disclosure to a scanner). `REJECT` is often better
**internally**, between services you control — a fast, clear failure is more
debuggable than a hang, and there's no meaningful attacker to hide
information from on an internal network segment.

## Connection tracking (conntrack)

```bash
nft add rule inet filter input ct state established,related accept
conntrack -L                      # current tracked connections
conntrack -L | wc -l               # table size -- can be exhausted under load
cat /proc/sys/net/netfilter/nf_conntrack_max
```

| State | Meaning |
| --- | --- |
| `NEW` | First packet of a connection |
| `ESTABLISHED` | Part of an already-tracked connection |
| `RELATED` | Associated with an established connection but a different flow (e.g. FTP data channel, ICMP error responses) |
| `INVALID` | Doesn't fit any tracked connection — often malformed or a fragment problem |

**Almost every ruleset needs an `established,related accept` rule near the
top of `input`**, or every *response* packet for a connection you initiated
outbound gets independently re-evaluated against the whole ruleset and
potentially dropped — this single rule is what makes "allow the outbound
request, and let its response back in" work without writing a matching
inbound rule for every possible response port.

`conntrack` table exhaustion under high connection volume (many short-lived
connections, a flood) causes new connections to silently fail even though
the rules themselves are correct — check `conntrack -L | wc -l` against
`nf_conntrack_max` when connections fail under load with no obvious rule
explanation.

## A minimal, safe baseline

```bash
nft add table inet filter
nft add chain inet filter input { type filter hook input priority 0 \; policy drop \; }

nft add rule inet filter input ct state established,related accept
nft add rule inet filter input ct state invalid drop
nft add rule inet filter input iif lo accept
nft add rule inet filter input tcp dport 22 accept       # SSH -- add this BEFORE enabling a drop policy
nft add rule inet filter input ip protocol icmp accept
```

**Order matters critically for a remote host: confirm the SSH-allow rule
exists and is active before setting the default policy to `drop`.** Enabling
a drop-by-default policy without first confirming the management access
rule is in place is one of the most common ways to lock yourself out of a
remote machine, exactly analogous to the `ufw enable`-before-SSH-rule trap
covered in `ubuntu-administration`.

## iptables equivalents (legacy syntax, still common)

```bash
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -p tcp --dport 22 -j ACCEPT
iptables -A INPUT -j DROP                    # default deny, appended LAST

iptables -L -n -v --line-numbers              # numbered, for targeted deletion
iptables -D INPUT 3                            # delete rule number 3
iptables-save > /etc/iptables/rules.v4         # persist across reboot (mechanism varies by distro)
```

`-A` appends to the end of a chain; rule **order determines evaluation
order** — the first matching rule wins and processing for that packet
stops. A broad `ACCEPT` early in the chain makes every rule after it for
that traffic irrelevant, which is a common cause of "I added a DROP rule
but it's not blocking anything."

## Debugging a rule that isn't matching

```bash
nft add rule inet filter input tcp dport 8080 counter accept   # counters show whether a rule is even being hit
nft list ruleset -a                                              # -a adds rule handles; counters print automatically once a rule has `counter`
watch -n1 'nft list chain inet filter input'                     # watch counters increment live
```

```bash
iptables -L INPUT -n -v          # the -v flag shows per-rule packet/byte counts
```

**A rule with a zero counter is definitively not being matched** — this
immediately distinguishes "my rule is wrong" from "traffic isn't reaching
this chain at all" (wrong chain, wrong hook, or a routing issue upstream of
the firewall entirely). Adding a `counter` (nftables) or checking `-v`
(iptables) byte/packet counts is the fastest way to localize the actual
problem instead of re-reading rule syntax repeatedly.

```bash
dmesg | grep -i "IN=.*OUT="        # if a LOG rule is present, dropped packets appear in kernel logs
nft add rule inet filter input tcp dport 8080 log prefix "blocked-8080: " drop
```

Adding a temporary `log` rule immediately before a `drop` (nftables) or
using the `LOG` target (iptables) surfaces exactly which packets are hitting
that specific rule, in kernel logs (`dmesg`/`journalctl -k`) — useful when
counters confirm a rule is matching but the *specific* traffic hitting it
isn't what's expected.

## Pitfalls

- **Setting a default-drop policy without confirming the SSH/management
  rule is already active** — the single most common way to lock yourself
  out of a remote host.
- **Forgetting `established,related accept`** — return traffic for
  legitimate outbound connections gets blocked, breaking almost everything.
- **Assuming rule order doesn't matter** — the first match wins; a broad
  early `ACCEPT` silently defeats every later, more specific rule.
- **Debugging `input` chain rules for traffic that's actually passing
  through the host** — that traffic hits `forward`, not `input`.
- **Not checking counters before re-reading syntax repeatedly** — a
  zero-hit counter proves the traffic isn't reaching that rule at all,
  redirecting the investigation.
- **Confusing `DROP`'s silence for "more secure" in every context** — for
  internal service-to-service traffic you control, `REJECT`'s fast, clear
  failure is often more operationally useful.
- **Conntrack table exhaustion misdiagnosed as a rule problem** — check
  `conntrack -L | wc -l` against the max under high connection churn.

## Reference

- `tcp-ip-fundamentals` — the connection states these rules interact with
- `network-troubleshooting-tools` — `tcpdump` to confirm what's actually arriving
- `ubuntu-administration` — `ufw` as a friendlier front end over this same mechanism

## When NOT to use

- **Cloud security groups / NACLs** (AWS, GCP) — use cloud-native tools; this is host-level iptables/nftables.
- **Kubernetes NetworkPolicies** — different abstraction; use Cilium/Calico docs.
- **Application-level access control** (auth, RBAC) — firewalls operate at L3/L4, not L7.

## Related skills

- [tcp-ip-fundamentals](../networking/tcp-ip-fundamentals/SKILL.md) — understanding what the firewall filters.
- [network-troubleshooting-tools](../networking/network-troubleshooting-tools/SKILL.md) — verifying connectivity through firewall rules.
- [dns-troubleshooting](../networking/dns-troubleshooting/SKILL.md) — when firewall blocks DNS port 53.
- [tls-troubleshooting](../networking/tls-troubleshooting/SKILL.md) — when firewall interferes with TLS handshake.
