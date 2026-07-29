#!/usr/bin/env bash
#
# apt-audit.sh — one-pass report of package/update/reboot state on a
# Debian/Ubuntu host.
#
# Checks:
#   - packages in a broken dpkg state (not cleanly "ii")
#   - held packages (excluded from upgrades)
#   - manually installed packages no longer available in any repo
#   - pending reboot (kernel/libc update applied but not active)
#   - dpkg/apt lock held by a live process
#   - available security updates
#   - unattended-upgrades service state, if present
#
# Usage:
#   ./apt-audit.sh
#   ./apt-audit.sh -q          # findings only, no section headers
#
# Exit codes:
#   0  nothing actionable found
#   1  at least one finding
#   2  usage error, or apt/dpkg not available
#
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"

QUIET=0
FINDINGS=0

die() {
    printf '%s: %s\n' "$SCRIPT_NAME" "$*" >&2
    exit 2
}

usage() {
    cat <<EOF
${SCRIPT_NAME} — package, update and reboot state in one report.

Usage:
  ${SCRIPT_NAME} [-q]

Options:
  -q  Quiet: findings only
  -h  Help
EOF
}

section() { ((QUIET)) || printf '\n=== %s ===\n' "$*" >&2; }
finding() {
    printf '%s\n' "$*"
    FINDINGS=$((FINDINGS + 1))
}
clean() { ((QUIET)) || printf '(none)\n' >&2; }

check_broken() {
    section "Packages not cleanly installed"
    local out=0
    while read -r state pkg; do
        [[ -n "$state" ]] || continue
        finding "broken-state  ${state}  ${pkg}"
        out=1
    done < <(dpkg -l 2>/dev/null | awk 'NR > 5 && $1 !~ /^ii$/ { print $1, $2 }')
    ((out)) || clean
}

check_held() {
    section "Held packages"
    local pkg found=0
    while read -r pkg; do
        [[ -n "$pkg" ]] || continue
        finding "held  ${pkg}"
        found=1
    done < <(apt-mark showhold 2>/dev/null)
    ((found)) || clean
}

check_orphaned_manual() {
    section "Manually installed packages no longer in any repo"

    local -a manual=()
    mapfile -t manual < <(apt-mark showmanual 2>/dev/null)
    ((${#manual[@]})) || {
        clean
        return 0
    }

    # ONE apt-cache invocation for every package, not one per package.
    #
    # apt-cache policy re-reads and re-parses the entire package cache from
    # disk on every invocation. Calling it once per manually-installed
    # package made this check O(n) subprocess spawns -- on a host with ~100
    # manual packages (unremarkable after a handful of `apt-get install`
    # runs) that took well over two minutes. `apt-cache policy` accepts many
    # package names in one call and prints one block per package, so a
    # single invocation covering all of them is the fix.
    local pkg found=0
    while read -r pkg; do
        [[ -n "$pkg" ]] || continue
        finding "orphaned  ${pkg}"
        found=1
    done < <(apt-cache policy "${manual[@]}" 2>/dev/null | awk '
        /^[^ ]/ { pkg = $0; sub(/:$/, "", pkg) }
        /Candidate: \(none\)/ { print pkg }
    ')
    ((found)) || clean
}

check_reboot() {
    section "Reboot required"
    if [[ -f /var/run/reboot-required ]]; then
        finding "reboot-required  $(cat /var/run/reboot-required)"
        if [[ -f /var/run/reboot-required.pkgs ]]; then
            while read -r pkg; do
                finding "  because of: ${pkg}"
            done </var/run/reboot-required.pkgs
        fi
    else
        clean
    fi
}

check_locks() {
    section "Package manager locks"
    local lock held=0
    for lock in /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/cache/apt/archives/lock; do
        [[ -f "$lock" ]] || continue
        if command -v fuser >/dev/null 2>&1 && fuser "$lock" >/dev/null 2>&1; then
            finding "locked  ${lock}  (held by: $(fuser "$lock" 2>&1 | awk '{print $NF}'))"
            held=1
        fi
    done
    ((held)) || clean
}

check_security_updates() {
    section "Available security updates"
    # apt-get -s (simulate) needs no root and touches nothing.
    local pkg ver found=0
    while read -r pkg ver; do
        [[ -n "$pkg" ]] || continue
        finding "security-update  ${pkg}  ${ver}"
        found=1
    done < <(apt-get -s upgrade 2>/dev/null | awk '/^Inst/ && /security/ {print $2, $3}')
    ((found)) || clean
}

check_unattended_upgrades() {
    section "unattended-upgrades service"
    command -v systemctl >/dev/null 2>&1 || {
        ((QUIET)) || printf '(systemctl unavailable, skipping)\n' >&2
        return 0
    }
    if systemctl list-unit-files unattended-upgrades.service >/dev/null 2>&1; then
        local state
        state="$(systemctl is-enabled unattended-upgrades.service 2>/dev/null || printf 'unknown')"
        if [[ "$state" != "enabled" ]]; then
            finding "unattended-upgrades  not enabled (state: ${state})"
        else
            ((QUIET)) || printf 'enabled\n' >&2
        fi
    else
        ((QUIET)) || printf '(not installed)\n' >&2
    fi
}

main() {
    local opt
    while getopts ':qh' opt; do
        case "$opt" in
            q) QUIET=1 ;;
            h)
                usage
                exit 0
                ;;
            \?) die "unknown option: -${OPTARG}" ;;
        esac
    done

    command -v dpkg >/dev/null 2>&1 || die "dpkg not found -- not a Debian/Ubuntu system?"

    check_broken
    check_held
    check_orphaned_manual
    check_reboot
    check_locks
    check_security_updates
    check_unattended_upgrades

    printf '\n%s: %d finding(s)\n' "$SCRIPT_NAME" "$FINDINGS" >&2
    ((FINDINGS == 0))
}

main "$@"
