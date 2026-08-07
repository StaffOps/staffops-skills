# Linux Hardening Checklist
# Run through this sequentially on new hosts before production. Each item is verify + fix.

## 1. Kernel parameters (sysctl)
```bash
# Verify current state
sysctl net.ipv4.ip_forward net.ipv4.conf.all.accept_redirects kernel.randomize_va_space

# Apply hardened baseline
cat <<'EOF' | sudo tee /etc/sysctl.d/99-hardening.conf
net.ipv4.ip_forward = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.log_martians = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.tcp_syncookies = 1
kernel.randomize_va_space = 2
kernel.dmesg_restrict = 1
kernel.kptr_restrict = 2
kernel.yama.ptrace_scope = 1
fs.protected_hardlinks = 1
fs.protected_symlinks = 1
fs.suid_dumpable = 0
EOF
sudo sysctl --system
```

## 2. Mount options
```bash
# Verify /tmp
findmnt /tmp
# Should show: nosuid,nodev,noexec

# Fix via /etc/fstab (add options):
# tmpfs /tmp tmpfs defaults,nosuid,nodev,noexec 0 0
# /dev/sda2 /var ext4 defaults,nosuid,nodev 0 0
```

## 3. Disable unnecessary services
```bash
# List enabled services
systemctl list-unit-files --type=service --state=enabled

# Common services to disable if not needed:
sudo systemctl disable --now avahi-daemon cups bluetooth
```

## 4. PAM password policy
```bash
# /etc/security/pwquality.conf
minlen = 14
dcredit = -1
ucredit = -1
lcredit = -1
ocredit = -1
maxrepeat = 3

# Account lockout: /etc/pam.d/common-auth
# auth required pam_tally2.so deny=5 unlock_time=900 onerr=fail
```

## 5. File permissions
```bash
# Find world-writable files (excluding /proc /sys /tmp)
find / -path /proc -prune -o -path /sys -prune -o -path /tmp -prune -o -perm -0002 -type f -print

# Find SUID/SGID binaries
find / -path /proc -prune -o -type f \( -perm -4000 -o -perm -2000 \) -print

# Secure key files
chmod 600 /etc/ssh/sshd_config
chmod 640 /etc/shadow
chmod 644 /etc/passwd
```

## 6. Disable kernel modules not needed
```bash
cat <<'EOF' | sudo tee /etc/modprobe.d/hardening.conf
install cramfs /bin/true
install freevxfs /bin/true
install jffs2 /bin/true
install hfs /bin/true
install hfsplus /bin/true
install udf /bin/true
install usb-storage /bin/true
EOF
```

## 7. Verify SSH hardening
```bash
# Check config
sudo sshd -T | grep -E 'permitrootlogin|passwordauthentication|pubkeyauthentication'
# Expected: permitrootlogin no, passwordauthentication no, pubkeyauthentication yes
```

## 8. Automatic security updates
```bash
# Ubuntu/Debian
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades

# Verify
cat /etc/apt/apt.conf.d/20auto-upgrades
```
