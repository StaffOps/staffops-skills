#!/usr/bin/env bash
# Linux Filesystem — Useful Commands

# ═══ SPACE ANALYSIS ═════════════════════════════════════════════
df -h                                    # filesystem usage
df -i                                    # inode usage (can run out!)
du -sh /var/log/*  | sort -rh | head    # biggest dirs in /var/log
du -sh */ | sort -rh                    # top dirs in current path
ncdu /                                  # interactive (install: apt install ncdu)

# Find big files
find / -type f -size +500M -exec ls -lh {} \; 2>/dev/null
find / -xdev -type f -size +100M -printf "%s %p\n" | sort -rn | head

# Find recently modified
find /etc -mmin -60 -type f             # changed in last hour
find / -mtime -1 -type f 2>/dev/null    # changed in last day

# ═══ INODE TROUBLESHOOTING ═══════════════════════════════════
df -i                                    # check inode usage
# If 100% inodes used (0% space used = small files problem):
find / -xdev -type d | while read d; do echo "$(find "$d" -maxdepth 1 | wc -l) $d"; done | sort -rn | head

# ═══ MOUNT OPERATIONS ═══════════════════════════════════════════
mount | column -t                        # current mounts
cat /etc/fstab                           # persistent mounts
findmnt --real                           # tree view of mounts
lsblk -f                                 # devices + filesystems + UUIDs

# Mount/unmount
mount /dev/sdb1 /mnt/data
umount /mnt/data
umount -l /mnt/stuck                    # lazy unmount (busy fs)
fuser -vm /mnt/data                     # who's using it

# ═══ FILESYSTEM OPERATIONS ═══════════════════════════════════
# Check filesystem (unmounted only!)
fsck -n /dev/sda1                       # dry run check
e2fsck -f /dev/sda1                     # ext4 full check
xfs_repair -n /dev/sda1                 # XFS check

# Filesystem info
tune2fs -l /dev/sda1                    # ext4 info
xfs_info /mount/point                   # XFS info
stat /path/to/file                      # file metadata

# ═══ PERMISSIONS ════════════════════════════════════════════════
chmod 755 dir/ ; chmod 644 file         # standard dirs/files
chmod -R u+rwX,go+rX,go-w .            # recursive sane perms
chown -R app:app /srv/app               # change owner
getfacl /path                           # ACL permissions
setfacl -m u:deploy:rx /path            # grant user access

# Find permission issues
find / -perm -4000 -type f 2>/dev/null  # SUID files
find / -perm -2000 -type f 2>/dev/null  # SGID files
find /tmp -perm -o+w -type f            # world-writable in /tmp
namei -l /path/to/problematic/file      # trace permission chain

# ═══ LVM (if applicable) ═══════════════════════════════════════
pvs                                      # physical volumes
vgs                                      # volume groups
lvs                                      # logical volumes
lvextend -l +100%FREE /dev/vg/lv && resize2fs /dev/vg/lv  # extend to fill

# ═══ RECOVERY ══════════════════════════════════════════════════
# Disk full emergency: find and truncate biggest log
find /var/log -name "*.log" -size +1G -exec truncate -s 0 {} \;

# Deleted file still holding space (process has fd open):
lsof +L1 | grep deleted                 # find processes
# Either restart the process or:
# > /proc/<pid>/fd/<fd_number>           # truncate the deleted file
