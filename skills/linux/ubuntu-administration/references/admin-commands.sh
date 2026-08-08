#!/usr/bin/env bash
# Ubuntu Administration Quick Reference

# ═══ PACKAGE MANAGEMENT ════════════════════════════════════════
apt update                               # refresh package index
apt upgrade -y                           # upgrade all packages
apt install -y "package"                 # install
apt remove "package"                     # remove (keep config)
apt purge "package"                      # remove + config
apt autoremove -y                        # remove unused deps
apt list --installed | grep "term"       # search installed
apt-cache search "term"                  # search available
apt-cache show "package"                 # package info
dpkg -l | grep "term"                    # low-level package query
dpkg -L "package"                        # list files in package
dpkg -S /path/to/file                    # which package owns file

# Hold package version (prevent upgrade):
apt-mark hold "package"
apt-mark unhold "package"
apt-mark showhold

# ═══ UNATTENDED UPGRADES ══════════════════════════════════════
# /etc/apt/apt.conf.d/50unattended-upgrades
apt install -y unattended-upgrades
dpkg-reconfigure unattended-upgrades
systemctl status unattended-upgrades
cat /var/log/unattended-upgrades/unattended-upgrades.log

# ═══ USER MANAGEMENT ═════════════════════════════════════════
useradd -m -s /bin/bash -G sudo newuser  # create with home+sudo
passwd newuser                           # set password
usermod -aG docker newuser               # add to group
userdel -r olduser                       # remove user + home
id newuser                               # show uid/gid/groups
getent passwd                            # all users
getent group sudo                        # who has sudo

# ═══ NETWORKING ══════════════════════════════════════════════
# Netplan (Ubuntu 18.04+)
cat /etc/netplan/*.yaml                  # current config
netplan apply                            # apply changes
netplan try                              # apply with auto-revert (120s)
ip addr show                             # verify

# Hostname
hostnamectl set-hostname myserver
cat /etc/hostname

# ═══ STORAGE ════════════════════════════════════════════════
lsblk                                    # list block devices
fdisk -l                                 # partition info
blkid                                    # device UUIDs
# Extend LVM:
lvextend -l +100%FREE /dev/ubuntu-vg/ubuntu-lv
resize2fs /dev/ubuntu-vg/ubuntu-lv

# ═══ SERVICES / BOOT ═══════════════════════════════════════
systemctl list-units --state=failed      # failed services
systemctl list-timers --all              # scheduled timers
journalctl -b -p err                     # errors since boot
journalctl --disk-usage                  # log space used
journalctl --vacuum-size=500M            # trim logs to 500M
systemd-analyze blame                    # slow boot services

# ═══ SECURITY ═════════════════════════════════════════════
# UFW firewall
ufw status verbose
ufw allow 22/tcp
ufw enable

# SSH hardening
# /etc/ssh/sshd_config:
#   PermitRootLogin no
#   PasswordAuthentication no
#   PubkeyAuthentication yes
systemctl restart sshd

# Fail2ban
apt install -y fail2ban
systemctl enable --now fail2ban
fail2ban-client status sshd

# ═══ TROUBLESHOOTING ═══════════════════════════════════════
dmesg -T | tail -50                      # kernel messages
journalctl -xe                           # recent systemd errors
cat /var/log/syslog | tail -100          # system log
cat /var/log/auth.log | tail -50         # auth attempts
last -10                                 # recent logins
lastb -10                                # failed logins
who -a                                   # currently logged in
