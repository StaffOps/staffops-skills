#!/usr/bin/env bash
# Linux Firewall Cheat Sheet — iptables + nftables

# ═══ IPTABLES ═══════════════════════════════════════════════════
# List rules
iptables -L -n -v                        # all chains, numeric, verbose
iptables -L -n -v --line-numbers         # with rule numbers
iptables -t nat -L -n -v                 # NAT table
iptables -S                              # as commands (reproducible)

# Allow/deny
iptables -A INPUT -p tcp --dport 22 -j ACCEPT       # allow SSH
iptables -A INPUT -p tcp --dport 80 -j ACCEPT       # allow HTTP
iptables -A INPUT -s 10.0.0.0/8 -j ACCEPT           # allow subnet
iptables -A INPUT -p tcp --dport 3306 -j DROP        # block MySQL
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT  # allow replies

# Delete rule
iptables -D INPUT 3                                  # by line number
iptables -D INPUT -p tcp --dport 80 -j ACCEPT       # by spec

# Save / restore
iptables-save > /etc/iptables/rules.v4
iptables-restore < /etc/iptables/rules.v4

# Port forwarding (DNAT)
iptables -t nat -A PREROUTING -p tcp --dport 80 -j DNAT --to-destination 10.0.0.5:8080
iptables -t nat -A POSTROUTING -j MASQUERADE

# Log dropped packets (debug)
iptables -A INPUT -j LOG --log-prefix "DROPPED: " --log-level 4
# View: journalctl -k | grep DROPPED

# ═══ NFTABLES (modern replacement) ═════════════════════════════
# List everything
nft list ruleset
nft list tables
nft list chain inet filter input

# Create basic firewall
nft add table inet filter
nft add chain inet filter input '{ type filter hook input priority 0; policy drop; }'
nft add rule inet filter input ct state established,related accept
nft add rule inet filter input iif lo accept
nft add rule inet filter input tcp dport 22 accept
nft add rule inet filter input tcp dport {80, 443} accept
nft add rule inet filter input counter drop

# Delete rule (by handle)
nft -a list chain inet filter input      # shows handles
nft delete rule inet filter input handle 5

# Save / restore
nft list ruleset > /etc/nftables.conf
nft -f /etc/nftables.conf

# ═══ FIREWALLD (RHEL/CentOS) ═══════════════════════════════════
firewall-cmd --state
firewall-cmd --list-all
firewall-cmd --add-port=8080/tcp --permanent
firewall-cmd --add-service=http --permanent
firewall-cmd --reload

# ═══ UFW (Ubuntu simplified) ═══════════════════════════════════
ufw status verbose
ufw allow 22/tcp
ufw allow from 10.0.0.0/8
ufw deny 3306/tcp
ufw enable
ufw reset                                # remove all rules

# ═══ DEBUGGING ═════════════════════════════════════════════════
# Check if port is blocked:
ss -tlnp | grep :8080                    # is something listening?
iptables -L -n -v | grep -i drop         # are packets being dropped?
conntrack -L | grep <ip>                 # connection tracking
tcpdump -i eth0 port 8080 -c 5          # do packets arrive?
