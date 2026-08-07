---
name: tcp-ip-fundamentals
description: "Understand TCP handshakes, states and packet flow."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tcp, ip, networking, handshake, mtu, subnetting, sockets]
    category: networking
    related_skills: [network-troubleshooting-tools, dns-troubleshooting, linux-firewall]
---
# TCP/IP Fundamentals

The mental model behind most networking troubleshooting: how a TCP
connection is actually established and torn down, what each socket state
means, and the addressing basics (subnets, CIDR) needed to read a routing
table or firewall rule correctly.

## When to Use

Use when a connection hangs instead of failing fast, `ss`/`netstat` output
shows a state that doesn't make sense, subnetting math is needed for a
firewall rule or VPC design, or explaining the difference between a
connection timeout and a connection refused.

## The three-way handshake

```
Client                          Server
  |--------- SYN ---------------->|      client: SYN_SENT
  |<------- SYN-ACK ---------------|      server: SYN_RECEIVED
  |--------- ACK ----------------->|      both: ESTABLISHED
```

Every TCP connection starts here. A connection that **hangs** (no response
at all, eventually times out) usually means the SYN never got a reply —
firewall dropping it silently, wrong IP/port, or the destination host
unreachable at the network layer. A connection that's **refused immediately**
means the SYN reached the host and got an RST back — nothing is listening on
that port, which is a different, more informative failure than a silent
drop.

```bash
# hangs -> nothing responded to the SYN
telnet host 9999

# instant "Connection refused" -> host responded, nothing listening
telnet host 9998
```

## Connection teardown

```
Initiator                        Peer
  |--------- FIN ----------------->|      initiator: FIN_WAIT_1
  |<-------- ACK -------------------|      initiator: FIN_WAIT_2
  |<-------- FIN --------------------|      peer: LAST_ACK
  |--------- ACK ------------------->|      initiator: TIME_WAIT
```

Four packets, because each side closes its own direction independently
(TCP is full-duplex). The side that sends the first `FIN` ends up in
`TIME_WAIT` after the exchange completes.

## Socket states

```bash
ss -tan
```

| State | Meaning |
| --- | --- |
| `LISTEN` | Waiting for incoming connections |
| `SYN_SENT` | Client sent SYN, awaiting SYN-ACK |
| `SYN_RECV` | Server got SYN, sent SYN-ACK, awaiting ACK |
| `ESTABLISHED` | Handshake complete, data can flow |
| `FIN_WAIT_1` / `FIN_WAIT_2` | This side initiated close |
| `CLOSE_WAIT` | **Peer** closed; this side hasn't called `close()` yet |
| `LAST_ACK` | This side closed after the peer did, awaiting final ACK |
| `TIME_WAIT` | Closed; waiting to guarantee no stray packets confuse a new connection |
| `CLOSING` | Both sides closed simultaneously (rare) |

Two states are the common troubleshooting signals:

**Many connections stuck in `CLOSE_WAIT`** means the application is not
calling `close()` on sockets after the peer disconnects — a resource leak in
the application, not a network problem. Growing without bound eventually
exhausts file descriptors.

**Excessive `TIME_WAIT`** on a host making many short-lived outbound
connections (a proxy, a load-generator) can exhaust the ephemeral port range.
`TIME_WAIT` is normal and self-clearing (default ~60s on Linux); the fix for
high volume is usually connection reuse (keep-alive, connection pooling)
rather than tuning kernel parameters.

```bash
ss -tan state time-wait | wc -l
ss -tan state close-wait
cat /proc/sys/net/ipv4/ip_local_port_range   # the ephemeral port pool size
```

## MTU and fragmentation

Maximum Transmission Unit — the largest packet a link can carry without
fragmenting. Standard Ethernet is 1500 bytes; a mismatch across a path
(common with VPN/tunnel overhead) causes a specific symptom: small packets
work, large ones silently hang.

```bash
ping -M do -s 1472 host      # 1472 + 28 (IP+ICMP headers) = 1500; -M do disables fragmentation
```

If that fails but a smaller size succeeds, something on the path has a
smaller MTU than expected — a VPN tunnel is the most common cause, since it
adds encapsulation overhead on top of the underlying 1500-byte link. This
manifests as: SSH connects fine (small packets), but a large file transfer
or HTTPS page with a big response hangs.

**Path MTU Discovery** (PMTUD) is supposed to handle this automatically —
routers send an ICMP "fragmentation needed" back to the sender when a packet
is too big for `DF` (don't fragment). It fails silently when a firewall
somewhere on the path blocks that ICMP message entirely, which is why "large
transfers hang, small ones work" is specifically an MTU/PMTUD-blackhole
symptom rather than a generic connectivity problem.

## IP addressing and CIDR

```
10.0.1.0/24
   │      │
   │      └── 24 bits are the NETWORK; the remaining 8 bits are host addresses
   └────────── 2^8 = 256 addresses (254 usable: .0 is network, .255 is broadcast)
```

| CIDR | Addresses | Usable hosts | Typical use |
| --- | --- | --- | --- |
| /32 | 1 | 1 (a single host route) | — |
| /30 | 4 | 2 | Point-to-point link |
| /29 | 8 | 6 | Small subnet |
| /24 | 256 | 254 | Common subnet size |
| /16 | 65,536 | 65,534 | A large VPC/site range |
| /8 | 16.7M | — | An entire private range (10.0.0.0/8) |

```bash
ipcalc 10.0.1.0/24              # network, broadcast, usable range, netmask
python3 -c "import ipaddress; print(ipaddress.ip_network('10.0.1.0/24'))"
```

**Private address ranges** (RFC 1918), never routable on the public
internet:

| Range | Size |
| --- | --- |
| `10.0.0.0/8` | Largest, common in enterprise/cloud VPCs |
| `172.16.0.0/12` | Docker's default bridge often uses this range |
| `192.168.0.0/16` | Common for home/small-office networks |

Overlapping private ranges between environments (a VPC and an on-prem
network both using `10.0.0.0/8`) is a frequent cause of routing conflicts
when connecting them via VPN or peering — always check for overlap before
establishing the connection.

## Routing basics

```bash
ip route show
ip route get 8.8.8.8          # which route/interface would be used
traceroute host                # the actual path, hop by hop
```

A packet's destination is matched against the routing table using
**longest-prefix match** — the most specific matching route wins, not the
first one listed. A `/32` route to a specific host overrides a broader
`/24` or default route for that one address, which is exactly how policy
overrides and VPN split-tunneling work.

## Ports and well-known ranges

| Range | Use |
| --- | --- |
| 0-1023 | Well-known/system ports; binding requires root/`CAP_NET_BIND_SERVICE` on Linux |
| 1024-49151 | Registered ports (assigned to specific applications by convention) |
| 49152-65535 | Ephemeral — the OS's pool for outbound connection source ports |

`Permission denied` binding to port 80 or 443 as a non-root user is this
restriction — either run as root (not recommended for a long-running
service), use `setcap cap_net_bind_service+ep` on the binary, or put a
reverse proxy in front that binds the low port and forwards to a high one.

## Pitfalls

- **Treating "connection refused" and "connection timeout" as the same
  problem** — refused means the host responded (routing/firewall to the
  host is fine, nothing's listening); timeout means no response reached
  back at all (check firewall/routing/host reachability).
- **Assuming a `CLOSE_WAIT` buildup is a network issue** — it's an
  application not closing sockets.
- **Tuning `TIME_WAIT` sysctls instead of fixing connection reuse** — the
  actual fix for ephemeral port exhaustion is almost always pooling/keep-alive.
- **Debugging an MTU-related hang as if it were a generic timeout** — the
  "small packets work, large ones hang" pattern is specific and points
  directly at MTU/PMTUD.
- **Forgetting longest-prefix match** — assuming route order in `ip route
  show` determines which route wins.

## Reference

- `network-troubleshooting-tools` — the tools (`ss`, `tcpdump`, `traceroute`) in depth
- `dns-troubleshooting` — the layer above this, name resolution specifically
- `linux-firewall` — where SYN packets actually get dropped or rejected

## When NOT to use

- **Hands-on tool usage** (tcpdump flags, ss options) — see [network-troubleshooting-tools](../networking/network-troubleshooting-tools/SKILL.md).
- **Application protocol debugging** (HTTP/2, gRPC, WebSocket) — use protocol-specific tools.
- **Cloud networking** (VPC peering, Transit Gateway, overlay networks) — different abstraction layer.

## Related skills

- [network-troubleshooting-tools](../networking/network-troubleshooting-tools/SKILL.md) — practical tools for TCP/IP diagnosis.
- [linux-firewall](../networking/linux-firewall/SKILL.md) — filtering at network/transport layers.
- [dns-troubleshooting](../networking/dns-troubleshooting/SKILL.md) — application-layer name resolution.
- [tls-troubleshooting](../networking/tls-troubleshooting/SKILL.md) — transport-layer security.
