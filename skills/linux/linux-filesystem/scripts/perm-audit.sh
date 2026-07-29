#!/usr/bin/env bash
#
# perm-audit.sh — report permission and ownership problems in a directory tree.
#
# Checks:
#   - world-writable files and directories (missing sticky bit on dirs)
#   - setuid / setgid binaries
#   - files owned by no existing user or group
#   - SSH key material with permissions SSH will reject
#   - executable data files (a symptom of `chmod -R 755`)
#   - broken symlinks
#
# Usage:
#   ./perm-audit.sh /srv/app
#   ./perm-audit.sh -q /srv/app          # only findings, no section headers
#   ./perm-audit.sh -x /                 # stay on one filesystem
#
# Exit codes:
#   0  no findings
#   1  at least one finding
#   2  usage error
#
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"

QUIET=0
ONE_FS=0
FINDINGS=0

die() {
    printf '%s: %s\n' "$SCRIPT_NAME" "$*" >&2
    exit 2
}

usage() {
    cat <<EOF
${SCRIPT_NAME} — audit permissions and ownership in a tree.

Usage:
  ${SCRIPT_NAME} [-q] [-x] DIRECTORY

Options:
  -q  Quiet: print findings only
  -x  Do not cross filesystem boundaries
  -h  Help
EOF
}

section() { ((QUIET)) || printf '\n=== %s ===\n' "$*"; }

# Print each finding and count it. Reads NUL-delimited paths on stdin.
#
# Callers MUST invoke this with process substitution, never as the right side
# of a pipe: a pipeline stage runs in a subshell, so FINDINGS increments would
# be discarded and every count would come back zero.
report() {
    local label="$1" count=0 path
    while IFS= read -r -d '' path; do
        printf '%-22s %s\n' "$label" "$path"
        count=$((count + 1))
    done
    ((count)) && FINDINGS=$((FINDINGS + count))
    ((QUIET)) || printf '  (%d)\n' "$count"
}

main() {
    local opt
    while getopts ':qxh' opt; do
        case "$opt" in
            q) QUIET=1 ;;
            x) ONE_FS=1 ;;
            h)
                usage
                exit 0
                ;;
            \?) die "unknown option: -${OPTARG}" ;;
        esac
    done
    shift $((OPTIND - 1))

    (($# == 1)) || {
        usage >&2
        exit 2
    }
    local root="$1"
    [[ -d "$root" ]] || die "not a directory: ${root}"

    local -a base=("$root")
    ((ONE_FS)) && base+=(-xdev)

    section "World-writable files"
    report "world-writable" < <(find "${base[@]}" -type f -perm -o+w -print0 2>/dev/null)

    section "World-writable directories without the sticky bit"
    report "no-sticky" < <(find "${base[@]}" -type d -perm -o+w ! -perm -1000 -print0 2>/dev/null)

    section "setuid / setgid binaries"
    report "setuid-setgid" < <(find "${base[@]}" -type f -perm /6000 -print0 2>/dev/null)

    section "Orphaned ownership"
    report "orphaned" < <(find "${base[@]}" \( -nouser -o -nogroup \) -print0 2>/dev/null)

    section "Broken symlinks"
    report "broken-symlink" < <(find "${base[@]}" -xtype l -print0 2>/dev/null)

    section "SSH key material with unsafe permissions"
    # Private keys must be 600 or stricter; SSH refuses anything looser.
    report "ssh-perms" < <(find "${base[@]}" -type f \
        \( -name 'id_*' ! -name '*.pub' -o -name 'authorized_keys' \) \
        -perm /077 -print0 2>/dev/null)

    section "Executable non-script files"
    # Data files with the execute bit usually mean a recursive chmod went wrong.
    local path
    while IFS= read -r -d '' path; do
        case "$path" in
            *.sh | *.bash | *.py | *.pl | *.rb) continue ;;
        esac
        # Anything with a shebang or an ELF header is legitimately executable.
        head -c 2 -- "$path" 2>/dev/null | grep -q '^#!' && continue
        file -b -- "$path" 2>/dev/null | grep -qiE 'executable|shared object' && continue
        printf '%-22s %s\n' "exec-data-file" "$path"
        FINDINGS=$((FINDINGS + 1))
    done < <(find "${base[@]}" -type f -perm /111 -print0 2>/dev/null)

    printf '\n%s: %d finding(s)\n' "$SCRIPT_NAME" "$FINDINGS" >&2
    ((FINDINGS == 0))
}

main "$@"
