---
name: network-troubleshooting-tools
description: "Use ss, tcpdump, curl and traceroute to diagnose issues."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [tcpdump, ss, curl, traceroute, mtr, netcat, wireshark, packet-capture]
    category: networking
    related_skills: [tcp-ip-fundamentals, dns-troubleshooting, tls-troubleshooting, linux-firewall]
---
# Network Troubleshooting Tools

The core toolkit for diagnosing network problems from the command line: `ss`
for current connections, `curl -v` for a single request's full lifecycle,
`tcpdump` for what's actually on the wire, and `traceroute`/`mtr` for the
path in between. Knowing which tool answers which question is most of the
skill.

## When to Use

Use when diagnosing a connection failure, verifying what's actually
listening on a port, capturing traffic to settle a dispute about what a
service is really sending, or tracing the path a packet takes.

## Choosing the right tool

| Question | Tool |
| --- | --- |
| What's listening on this host? | `ss -tlnp` |
| Is a specific port reachable? | `nc -zv` or `curl` |
| What's the full lifecycle of one HTTP request? | `curl -v` |
| What's actually on the wire? | `tcpdump` |
| What's the path to a destination? | `traceroute` / `mtr` |
| Is DNS the problem? | `dig` — see `dns-troubleshooting` |
| What TLS is happening? | `openssl s_client` — see `tls-troubleshooting` |

## ss — sockets, replacing netstat

```bash
ss -tlnp                     # TCP, listening, numeric ports, with owning process
ss -tan                      # all TCP connections and their states
ss -tan state established
ss -tan state time-wait | wc -l
ss -unlp                     # UDP listening sockets
ss -s                         # summary counts by state
ss -o state established '( dport = :443 or sport = :443 )'   # filter expressions
```

`-p` (show the owning process) typically requires root or the socket's
owning user. `ss` reads directly from the kernel and is materially faster
than the older `netstat` on a host with many connections — prefer it.

```bash
ss -tlnp | grep :8080         # what's actually bound to this port, and by whom
```

This answers "is anything listening here" before assuming a firewall or
routing problem — a connection refused locally means nothing's listening,
which is a configuration problem, not a network one.

## curl -v — one request, fully visible

```bash
curl -v https://example.com
curl -v --resolve example.com:443:1.2.3.4 https://example.com   # bypass DNS
curl -o /dev/null -s -w '%{time_namelookup} %{time_connect} %{time_appconnect} %{time_starttransfer} %{time_total}\n' https://example.com
curl -I https://example.com       # headers only (HEAD request)
curl -v --resolve host:443:127.0.0.1 https://host   # test a specific backend directly
```

`-v` shows every phase: DNS resolution, TCP connect, TLS handshake, request
headers sent, response headers received. Reading where in that sequence a
request fails immediately narrows the problem — a hang after "Connected to"
but before any TLS output is a TLS-layer issue; a hang before "Connected to"
is DNS or TCP-layer.

The `-w` timing breakdown is the fastest way to tell whether latency is DNS,
connect, TLS handshake, or server processing time — without it, "the request
is slow" has no further diagnostic value on its own.

## nc (netcat) — raw connectivity and simple protocol probing

```bash
nc -zv host 443                # TCP port check: zero-I/O, verbose
nc -zv -u host 53               # UDP port check (less reliable -- UDP has no handshake to confirm)
nc -zv host 20-30                # a port range
echo -e "GET / HTTP/1.0\r\n\r\n" | nc host 80    # manually speak a raw protocol
```

`nc -zv` for UDP only confirms the packet was *sent*, not that anything
received or processed it — UDP has no equivalent to a TCP SYN-ACK to
confirm the other side is actually there. A UDP "success" is weaker evidence
than a TCP one; treat it accordingly.

## traceroute / mtr — the path

```bash
traceroute host
traceroute -T -p 443 host      # TCP instead of the default UDP/ICMP -- some firewalls only allow this
mtr host                        # continuous traceroute + per-hop loss/latency statistics
mtr -r -c 100 host               # report mode: 100 packets, then print and exit (good for scripts/tickets)
```

`mtr` is `traceroute` combined with `ping`, run continuously — it shows loss
percentage **per hop**, which pinpoints exactly where in the path packets
are being dropped rather than just confirming that *some* loss exists
end-to-end. A hop showing loss that later hops don't is usually that
specific router deprioritizing ICMP for its own traffic (not an actual
problem) — consistent loss that *persists* through to the final hops is the
real signal.

```bash
traceroute -I host        # ICMP instead of UDP -- some networks handle this differently
```

Different traceroute probe types (UDP, ICMP, TCP) can produce different
results across the same path, since firewalls frequently treat them
differently — if one method shows a path timing out entirely, trying another
before concluding the destination is unreachable is worth the extra command.

## tcpdump — ground truth on the wire

```bash
tcpdump -i eth0                        # everything on an interface -- usually too much
tcpdump -i eth0 port 443
tcpdump -i eth0 host 1.2.3.4
tcpdump -i eth0 'tcp[tcpflags] & tcp-syn != 0'    # SYN packets only -- connection attempts
tcpdump -i eth0 -w capture.pcap port 443           # write to a file for later/deeper analysis
tcpdump -r capture.pcap                             # read it back
tcpdump -i eth0 -A port 80              # print packet contents as ASCII (plaintext protocols only)
tcpdump -i any -n port 53                # -n: don't resolve names (avoids a DNS dependency to debug DNS!)
```

`-n` matters specifically when debugging DNS itself — without it, `tcpdump`
tries to reverse-resolve every address it prints, which can hang or produce
misleading extra traffic while investigating a DNS problem.

Reading a capture to diagnose a **hang**: look for a SYN with no SYN-ACK
response (nothing is answering — a firewall drop or routing issue), or a
SYN-ACK immediately followed by an RST (something actively rejected it after
appearing to accept).

`.pcap` files captured with `tcpdump -w` open directly in Wireshark for
deeper protocol-level analysis — capture on the command line, analyze
graphically, is a common and effective split of labor.

## Filter syntax essentials

```bash
tcpdump 'host 1.2.3.4 and port 443'
tcpdump 'src host 1.2.3.4'
tcpdump 'dst port 443'
tcpdump 'tcp and (port 80 or port 443)'
tcpdump 'net 10.0.0.0/8'
```

Filtering at capture time (rather than capturing everything and filtering
later) matters on a busy interface — an unfiltered capture on a loaded
production host can itself become a performance problem.

## Bandwidth and throughput testing

```bash
iperf3 -s                         # on the receiving host
iperf3 -c server_host             # on the sending host
iperf3 -c server_host -u -b 100M   # UDP, targeting 100Mbps
```

`iperf3` measures achievable throughput directly, isolating whether a
performance problem is the network path itself versus the application —
if `iperf3` between the same two hosts hits line rate but the real
application is slow, the network is not the bottleneck.

## A troubleshooting sequence

```
Connection problem to a remote host
│
├─ ss -tlnp (locally, if it's meant to be listening here) -- is anything listening?
├─ nc -zv host port -- is the port reachable at all?
│   ├─ hangs -> traceroute / mtr -- where does the path break?
│   └─ refused -> nothing is listening on the far end; check the SERVICE, not the network
├─ curl -v (if it's HTTP/S) -- which phase fails: DNS, connect, TLS, response?
└─ tcpdump on both ends simultaneously, if still unclear -- what's ACTUALLY sent/received?
```

Capturing on **both** ends of a suspected firewall or NAT boundary
simultaneously is the definitive way to prove where a packet is being
dropped — if it leaves host A but never arrives at host B, the problem is
provably in between, not on either host.

## Pitfalls

- **Trusting `ping` alone to mean full connectivity** — ICMP is often
  handled (allowed, blocked, or rate-limited) completely differently than
  the actual TCP/UDP traffic in question.
- **`nc -zv -u` "success" for UDP** — only confirms the packet was sent, not
  received.
- **An unfiltered `tcpdump` on a busy production interface** — can itself
  degrade performance; always filter at capture time.
- **Not using `-n` while debugging DNS** — `tcpdump`'s own reverse lookups
  interfere with the investigation.
- **Assuming one traceroute probe type's result is definitive** — UDP, ICMP,
  and TCP traceroute can each show a different path or failure point.
- **Skipping `curl -v`'s timing breakdown** — "it's slow" without knowing
  *which phase* is slow wastes the next round of investigation.

## Reference

- `tcp-ip-fundamentals` — the handshake/state model these tools observe
- `dns-troubleshooting` — `dig` and the DNS-specific diagnostic path
- `tls-troubleshooting` — `openssl s_client` and certificate-layer diagnosis
- `linux-firewall` — the rules behind a DROP/REJECT a capture confirms

## When NOT to use

- **Application performance profiling** (slow queries, GC pauses) — use APM/profiling tools.
- **DNS-specific resolution** issues — see [dns-troubleshooting](../networking/dns-troubleshooting/SKILL.md) for dig/resolvectl.
- **TLS certificate or handshake** problems — see [tls-troubleshooting](../networking/tls-troubleshooting/SKILL.md).

## Related skills

- [tcp-ip-fundamentals](../networking/tcp-ip-fundamentals/SKILL.md) — theory behind what the tools measure.
- [dns-troubleshooting](../networking/dns-troubleshooting/SKILL.md) — name resolution debugging.
- [tls-troubleshooting](../networking/tls-troubleshooting/SKILL.md) — certificate and handshake issues.
- [linux-firewall](../networking/linux-firewall/SKILL.md) — when packets are being dropped by rules.
- [incident-triage-linux](../troubleshooting/incident-triage-linux/SKILL.md) — using these tools during outages.
