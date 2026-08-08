#!/usr/bin/env bash
# TCP/IP Diagnostic Commands

# ═══ LAYER 2 — LINK ═══════════════════════════════════════════
ip link show                             # interfaces + state (UP/DOWN)
ip link set eth0 up                      # bring interface up
ethtool eth0                             # speed, duplex, link detected?
ip neigh show                            # ARP cache (who's at what MAC)
arp -n                                   # same, older syntax
bridge fdb show                          # bridge forwarding table

# ═══ LAYER 3 — NETWORK ═══════════════════════════════════════
ip addr show                             # IPs on all interfaces
ip route show                            # routing table
ip route get 10.0.0.5                    # how would we reach this IP?
traceroute -n 10.0.0.5                   # hop-by-hop path
ping -c 4 10.0.0.5                       # basic reachability
ip rule show                             # policy routing rules
sysctl net.ipv4.ip_forward              # is forwarding enabled?

# ═══ LAYER 4 — TRANSPORT ═════════════════════════════════════
ss -tlnp                                 # TCP listeners
ss -tnp                                  # established TCP connections
ss -s                                    # socket statistics summary
cat /proc/net/tcp                        # raw kernel TCP table
# TCP state counts:
ss -tan | awk '{print $1}' | sort | uniq -c | sort -rn

# ═══ COMMON TCP STATES ═══════════════════════════════════════
# LISTEN      → server waiting for connections
# ESTABLISHED → active connection
# TIME_WAIT   → closed, waiting for stray packets (normal)
# CLOSE_WAIT  → remote closed, local hasn't (app bug!)
# SYN_SENT    → connection attempt (timeout = can't reach)
# FIN_WAIT2   → we closed, waiting for remote FIN

# ═══ KERNEL TUNING (read-only check) ═════════════════════════
sysctl net.core.somaxconn               # listen backlog limit
sysctl net.ipv4.tcp_max_syn_backlog     # SYN queue size
sysctl net.ipv4.tcp_fin_timeout         # TIME_WAIT duration
sysctl net.ipv4.tcp_tw_reuse            # reuse TIME_WAIT sockets
sysctl net.ipv4.tcp_keepalive_time      # keepalive interval
sysctl net.core.netdev_max_backlog      # NIC rx queue length
cat /proc/sys/net/core/rmem_max         # max receive buffer
cat /proc/sys/net/core/wmem_max         # max send buffer

# ═══ PACKET LOSS / ERRORS ════════════════════════════════════
ip -s link show eth0                     # interface counters (drops, errors)
ethtool -S eth0 | grep -i "drop\|error\|miss"  # NIC-level stats
cat /proc/net/snmp | grep -A1 Tcp       # TCP retransmits, resets
nstat -az | grep -i "drop\|overflow\|loss"  # kernel network stats

# ═══ MTU ISSUES ══════════════════════════════════════════════
ping -M do -s 1472 10.0.0.5             # test MTU (1472 + 28 = 1500)
# If fails: path MTU < 1500 (common in VPN/overlay networks)
ip link show | grep mtu                  # current MTU settings
