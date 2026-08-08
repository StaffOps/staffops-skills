#!/usr/bin/env bash
# Network Troubleshooting Tools — tcpdump / ss / curl / mtr

# ═══ SS (socket statistics — replaces netstat) ══════════════════
ss -tlnp                                 # TCP listening, numeric, process
ss -ulnp                                 # UDP listening
ss -tnp                                  # TCP established connections
ss -s                                    # summary stats
ss -tnp dst :443                         # connections to port 443
ss -tnp src :8080                        # connections FROM port 8080
ss state established '( sport = :80 )'   # filter by state
ss -tnp | grep CLOSE-WAIT               # stuck connections
ss -tnp | awk '{print $5}' | cut -d: -f1 | sort | uniq -c | sort -rn | head  # top IPs

# ═══ TCPDUMP ═══════════════════════════════════════════════════
# Basic capture
tcpdump -i eth0 -n port 80              # HTTP traffic, no DNS resolution
tcpdump -i any -n host 10.0.0.5         # all traffic to/from IP
tcpdump -i eth0 -n 'port 443 and host 10.0.0.5'  # specific host+port
tcpdump -i eth0 -n -c 10 port 53        # first 10 DNS packets

# Save to file (analyze later with Wireshark)
tcpdump -i eth0 -w /tmp/capture.pcap -c 1000
tcpdump -r /tmp/capture.pcap            # read pcap file

# Show packet contents
tcpdump -i eth0 -A port 80              # ASCII (HTTP)
tcpdump -i eth0 -X port 80              # hex + ASCII

# Filter expressions
tcpdump -i eth0 'tcp[tcpflags] & (tcp-syn) != 0'     # SYN packets
tcpdump -i eth0 'tcp[tcpflags] & (tcp-rst) != 0'     # RST packets (rejects)
tcpdump -i eth0 -n 'icmp'               # ping/traceroute

# ═══ CURL (HTTP debugging) ═════════════════════════════════════
curl -v https://example.com              # verbose (TLS handshake, headers)
curl -o /dev/null -s -w '%{http_code}\n' https://example.com  # just status code
curl -s -w 'DNS: %{time_namelookup}s\nConnect: %{time_connect}s\nTLS: %{time_appconnect}s\nTotal: %{time_total}s\n' -o /dev/null https://example.com  # timing breakdown
curl -k https://self-signed.example.com  # skip TLS verification
curl --resolve example.com:443:1.2.3.4 https://example.com  # bypass DNS
curl -H "Host: myapp.internal" http://10.0.0.1:80  # custom Host header
curl -x http://proxy:3128 https://example.com       # through proxy
curl --connect-timeout 3 --max-time 10 http://slow-api.com  # timeouts

# ═══ MTR (traceroute + ping combined) ══════════════════════════
mtr --report -c 10 example.com          # 10 probes, report mode
mtr --tcp -P 443 example.com            # TCP mode (bypasses ICMP blocks)
mtr -n example.com                      # no DNS (faster)

# ═══ QUICK CONNECTIVITY TESTS ══════════════════════════════════
# Is port open?
nc -zv 10.0.0.5 8080                     # TCP connection test
timeout 3 bash -c '</dev/tcp/10.0.0.5/8080' && echo OPEN || echo CLOSED

# Is host reachable?
ping -c 3 -W 2 10.0.0.5                 # 3 pings, 2s timeout
arping -c 3 10.0.0.5                    # ARP-level (same subnet)

# What's my IP / route?
ip addr show                             # all interfaces
ip route get 10.0.0.5                    # which interface/route used
ip neigh show                            # ARP table
