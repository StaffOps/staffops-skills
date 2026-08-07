#!/usr/bin/env bash
# DNS Troubleshooting Cheat Sheet

# ═══ DIG (primary tool) ═════════════════════════════════════════
dig example.com                          # full query (A record)
dig +short example.com                   # just the IP
dig AAAA example.com                     # IPv6
dig MX example.com                       # mail servers
dig TXT example.com                      # SPF/DKIM/DMARC
dig NS example.com                       # nameservers
dig SOA example.com                      # zone authority
dig ANY example.com +noall +answer       # all records

# Query specific server
dig @8.8.8.8 example.com                # ask Google DNS
dig @ns1.example.com example.com        # ask authoritative NS

# Trace delegation chain (find where it breaks)
dig +trace example.com

# Reverse lookup
dig -x 1.2.3.4

# Check TTL remaining
dig +nocmd +noall +answer +ttlunits example.com

# DNSSEC validation
dig +dnssec example.com

# ═══ NSLOOKUP (simpler, always available) ═══════════════════════
nslookup example.com                     # default resolver
nslookup example.com 8.8.8.8           # specific server
nslookup -type=MX example.com
nslookup -type=SRV _http._tcp.example.com   # service discovery

# ═══ HOST (quick lookups) ═══════════════════════════════════════
host example.com                         # forward
host 1.2.3.4                             # reverse
host -t CNAME www.example.com            # specific record type

# ═══ SYSTEMD-RESOLVED (Ubuntu/modern distros) ═══════════════════
resolvectl status                        # current DNS config
resolvectl query example.com            # resolve through systemd
resolvectl statistics                    # cache hit/miss stats
resolvectl flush-caches                 # clear DNS cache
resolvectl dns eth0 8.8.8.8 8.8.4.4    # set DNS for interface

# ═══ LOCAL RESOLVER CONFIG ══════════════════════════════════════
cat /etc/resolv.conf                     # active nameservers
cat /etc/nsswitch.conf | grep hosts      # resolution order
cat /etc/hosts                           # local overrides
systemctl status systemd-resolved       # resolver daemon status

# ═══ KUBERNETES DNS ═════════════════════════════════════════════
# From inside a pod:
# nslookup myservice.mynamespace.svc.cluster.local
# dig +short myservice.mynamespace.svc.cluster.local @10.96.0.10

# Check CoreDNS:
# kubectl -n kube-system logs -l k8s-app=kube-dns --tail=50
# kubectl -n kube-system get cm coredns -o yaml

# ═══ COMMON DIAGNOSES ══════════════════════════════════════════
# "works from one host, not another" → check /etc/resolv.conf + search domains
# "NXDOMAIN" → domain doesn't exist or wrong search domain
# "SERVFAIL" → upstream DNS can't answer (DNSSEC failure, zone broken)
# "connection timed out" → firewall blocking UDP/53 or TCP/53
# "truncated" → response >512B over UDP, need TCP fallback
