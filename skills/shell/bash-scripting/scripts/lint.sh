#!/usr/bin/env bash
#
# lint.sh — run every static check that applies to shell scripts in a tree.
#
# Checks, in order:
#   1. bash -n     parse without executing (catches syntax errors)
#   2. shellcheck  static analysis
#   3. shfmt       formatting diff
#
# Usage:
#   ./lint.sh [path ...]        default: current directory
#   FIX=1 ./lint.sh             rewrite files with shfmt instead of diffing
#
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"
readonly SHFMT_ARGS=(-i 4 -ci -bn)

FIX="${FIX:-0}"
failures=0

log() { printf '%s\n' "$*" >&2; }
fail() {
    log "FAIL  $*"
    failures=$((failures + 1))
}
ok() { printf 'ok    %s\n' "$*"; }

have() { command -v "$1" >/dev/null 2>&1; }

# Collect shell scripts: anything ending in .sh, plus files whose shebang
# names a shell. NUL-delimited throughout so paths with spaces survive.
collect_scripts() {
    local root="$1"

    {
        find "$root" -type f -name '*.sh' -print0

        # Extensionless scripts identified by their shebang.
        find "$root" -type f ! -name '*.*' -perm -u+x -print0 \
            | while IFS= read -r -d '' file; do
                read -r first_line <"$file" 2>/dev/null || continue
                [[ "$first_line" =~ ^#!.*(bash|sh)$ ]] && printf '%s\0' "$file"
            done
    } | sort -zu
}

check_file() {
    local file="$1"
    local file_failed=0

    if ! bash -n "$file" 2>/dev/null; then
        fail "${file}: syntax error"
        bash -n "$file" 2>&1 | sed 's/^/      /' >&2 || true
        return 1
    fi

    if have shellcheck; then
        if ! shellcheck -x --color=never "$file"; then
            fail "${file}: shellcheck"
            file_failed=1
        fi
    fi

    if have shfmt; then
        if ((FIX)); then
            shfmt "${SHFMT_ARGS[@]}" -w "$file"
        elif ! shfmt "${SHFMT_ARGS[@]}" -d "$file"; then
            fail "${file}: formatting (run with FIX=1 to apply)"
            file_failed=1
        fi
    fi

    ((file_failed)) || ok "$file"
    return 0
}

main() {
    local -a roots=("$@")
    ((${#roots[@]})) || roots=(.)

    have shellcheck || log "warning: shellcheck not installed, skipping"
    have shfmt || log "warning: shfmt not installed, skipping"

    local found=0 file
    local root
    for root in "${roots[@]}"; do
        [[ -e "$root" ]] || {
            fail "no such path: ${root}"
            continue
        }

        while IFS= read -r -d '' file; do
            found=$((found + 1))
            check_file "$file" || true
        done < <(collect_scripts "$root")
    done

    printf '\n%s: checked %d file(s), %d failure(s)\n' \
        "$SCRIPT_NAME" "$found" "$failures" >&2

    ((failures == 0))
}

main "$@"
