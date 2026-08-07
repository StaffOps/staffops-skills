---
name: dns-troubleshooting
description: "Diagnose DNS resolution failures with dig and resolvectl."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [dns, dig, resolv-conf, nslookup, caching, ttl, resolvectl]
    category: networking
    related_skills: [tcp-ip-fundamentals, network-troubleshooting-tools, linux-firewall]
---
# DNS Troubleshooting

Diagnosing name resolution failures — the difference between a DNS problem
and a connectivity problem that only looks like one, reading `dig` output
correctly, and the resolver-chain quirks (search domains, `nsswitch.conf`,
systemd-resolved) that cause "works on one host, not another."

## When to Use

Use when a hostname fails to resolve, resolution is inconsistent between
hosts, DNS changes aren't taking effect, or distinguishing a DNS failure from
a downstream connection failure during an outage.

## First question: is it actually DNS?

```bash
dig +short example.com          # resolve the name
curl -v --resolve example.com:443:1.2.3.4 https://example.com   # bypass DNS, test connectivity directly
```

If resolution fails but connecting directly to the known IP works,
it's DNS. If both fail, the problem is downstream (routing, firewall, the
service itself) — don't spend time on DNS config that isn't the cause.

## dig — the primary diagnostic tool

```bash
dig example.com                    # full output: question, answer, authority, timing
dig +short example.com             # just the IP(s)
dig example.com A                  # explicit record type
dig example.com AAAA                # IPv6
dig example.com MX
dig example.com TXT
dig example.com NS
dig -x 1.2.3.4                      # reverse lookup
dig @8.8.8.8 example.com            # query a SPECIFIC server, bypassing local resolver config entirely
dig +trace example.com              # walk the full chain from root servers down
```

`dig @server` is the single most useful diagnostic technique: it isolates
whether the problem is the **record itself** (fails against every server,
including public ones like `8.8.8.8`) or **local resolver configuration**
(fails locally but succeeds against a public server).

```bash
dig example.com                # fails or wrong answer
dig @8.8.8.8 example.com       # succeeds -- the problem is LOCAL resolver config, not the record
```

## Reading dig output

```
;; ANSWER SECTION:
example.com.        299    IN    A    93.184.216.34

;; Query time: 23 msec
;; SERVER: 127.0.0.53#53(127.0.0.53)
```

| Field | Meaning |
| --- | --- |
| `299` | TTL in seconds — how much longer this answer is valid/cacheable |
| `Query time` | How long the query took — high values suggest the authoritative or upstream server is slow |
| `SERVER` | Which resolver actually answered — `127.0.0.53` is systemd-resolved's local stub, not the real upstream |

A `Query time` of 0ms on a repeated query means it was served from cache,
not from a fresh lookup — useful for confirming whether a DNS change has
actually propagated locally yet.

## The resolver chain on Linux

Resolution doesn't go straight to `/etc/resolv.conf` on modern systems —
`nsswitch.conf` determines the lookup order, and a local stub resolver
often sits in between:

```bash
cat /etc/nsswitch.conf | grep hosts
# hosts: files dns    -- /etc/hosts checked BEFORE DNS, every time
```

```bash
cat /etc/resolv.conf
resolvectl status              # on systemd-resolved systems -- the ACTUAL config in effect
```

**`/etc/resolv.conf` frequently does not reflect reality** on a system using
`systemd-resolved`: it may point at `127.0.0.53` (the local stub), with the
real upstream servers configured per-interface and visible only via
`resolvectl status`. Editing `/etc/resolv.conf` directly on such a system is
often overwritten automatically and doesn't change actual behavior — the fix
usually belongs in Netplan, NetworkManager, or the DHCP configuration
instead.

```bash
resolvectl status                    # per-interface DNS servers actually in use
resolvectl query example.com          # resolve using the real chain, with details
resolvectl flush-caches               # clear the local cache
```

`/etc/hosts` is checked **before** DNS by default (`nsswitch.conf`'s `files
dns` order) — a stale or incorrect entry there silently overrides every DNS
change, and is one of the most common "why isn't my DNS change working"
causes.

```bash
grep -i example.com /etc/hosts        # check this BEFORE debugging DNS servers
```

## Search domains

```bash
cat /etc/resolv.conf | grep search
```

```
search prod.internal corp.example.com
```

An unqualified name (`db` rather than `db.prod.internal`) gets each search
domain appended in order until one resolves. This explains two common
surprises: a name that resolves inside one environment but not another
(different search domains configured), and a name resolving to the *wrong*
thing because an earlier search domain matched unexpectedly.

```bash
dig db.prod.internal +short     # test the fully-qualified name directly
                                  # to rule out search-domain interference
```

## Caching and TTL

Three separate caches can each independently hold a stale answer:

1. **Application-level** — some runtimes (older Java versions notably) cache
   DNS answers in-process, ignoring the record's TTL entirely.
2. **OS-level resolver cache** — `systemd-resolved`, `nscd`, or similar.
3. **Recursive resolver cache** — the upstream DNS server (ISP, `8.8.8.8`,
   internal corporate resolver) caches per the record's TTL.

A DNS record change "not taking effect" is very often one of these layers
still serving the old answer, not a problem with the DNS change itself.

```bash
dig +short example.com                 # what's currently cached/being served
dig @8.8.8.8 +short example.com        # check a DIFFERENT resolver -- may already have the update
resolvectl flush-caches                 # clear the local systemd-resolved cache
```

Lowering a record's TTL **before** a planned change (well ahead of time, so
the low TTL itself propagates first) is the standard way to make a future
cutover fast — changing the TTL at the same time as the record doesn't help,
since the *old* TTL is what's already cached everywhere.

## Common failure signatures

| Symptom | Likely cause |
| --- | --- |
| `NXDOMAIN` | The name genuinely doesn't exist (or a typo) |
| `SERVFAIL` | The authoritative server is having a problem, or DNSSEC validation failed |
| Times out, no answer at all | Resolver unreachable — firewall blocking port 53, or the resolver IP is wrong |
| Different answers on different hosts | Different resolvers configured, or one has stale cache |
| Works with `dig`, fails in the application | Application-level caching, or it's using a different resolution path (e.g. `getaddrinfo` behavior, IPv6 preference) |

```bash
dig example.com +dnssec           # check for DNSSEC-related SERVFAIL
nc -zv -u 8.8.8.8 53               # can we even REACH the resolver (UDP/53)?
```

DNS primarily uses UDP port 53 (TCP for zone transfers and large responses,
including many DNSSEC answers) — a firewall rule that only accounts for TCP
can silently break DNS while looking correct on paper.

## IPv4/IPv6 dual-stack quirks

```bash
dig example.com A                  # IPv4 answer
dig example.com AAAA                # IPv6 answer
```

A host with both an `A` and `AAAA` record can connect over either family
depending on the client's preference and connectivity. A connection that
"sometimes" fails intermittently, especially from dual-stack hosts, is worth
checking for a broken IPv6 path even when IPv4 works fine — the client may
be trying IPv6 first (Happy Eyeballs-style behavior) and falling back slowly
or not at all.

## Pitfalls

- **Debugging local resolver config when the record itself is wrong** — use
  `dig @8.8.8.8` first to isolate which side the problem is on.
- **Editing `/etc/resolv.conf` directly on a systemd-resolved system** —
  often overwritten; check `resolvectl status` for what's actually in
  effect.
- **Forgetting `/etc/hosts` is checked first** — a stale entry silently
  wins over any DNS change.
- **Assuming a TTL change takes effect immediately** — the OLD TTL is what's
  cached until it expires; plan ahead by lowering TTL before the actual
  change.
- **Only allowing TCP/53 in a firewall rule and calling it done** — DNS
  needs UDP/53 for the overwhelming majority of ordinary queries.
- **Not checking `resolvectl status`** on modern Linux and only looking at
  `/etc/resolv.conf`, missing the actual per-interface configuration.

## Reference

- `tcp-ip-fundamentals` — the connectivity layer DNS problems are often confused with
- `network-troubleshooting-tools` — `dig`, `nc`, packet capture in more depth
- `linux-firewall` — where a UDP/53 rule gap actually blocks resolution
