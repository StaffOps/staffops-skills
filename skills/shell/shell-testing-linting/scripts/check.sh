#!/usr/bin/env bash
#
# check.sh — combined shell quality gate: parse, lint, format.
#
# Designed to be the single command CI runs. Returns non-zero if any stage
# fails, and prints a summary of every failing file.
#
# Usage:
#   ./check.sh [path ...]              default: current directory
#   SEVERITY=style ./check.sh          shellcheck minimum severity
#   FIX=1 ./check.sh                   apply shfmt formatting instead of diffing
#   SKIP_FORMAT=1 ./check.sh           lint only
#
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"
readonly SHFMT_ARGS=(-i 4 -ci -bn)

SEVERITY="${SEVERITY:-warning}"
FIX="${FIX:-0}"
SKIP_FORMAT="${SKIP_FORMAT:-0}"

declare -a FAILED_PARSE=()
declare -a FAILED_LINT=()
declare -a FAILED_FORMAT=()

have() { command -v "$1" >/dev/null 2>&1; }
note() { printf '%s\n' "$*" >&2; }

# Emit NUL-delimited shell scripts under the given roots, skipping VCS and
# vendor directories.
collect() {
    local root
    for root in "$@"; do
        find "$root" \
            \( -name .git -o -name node_modules -o -name vendor \) -prune -o \
            -type f -name '*.sh' -print0
    done | sort -zu
}

main() {
    local -a roots=("$@")
    ((${#roots[@]})) || roots=(.)

    have shellcheck || note "warning: shellcheck not found, lint stage skipped"
    have shfmt || note "warning: shfmt not found, format stage skipped"

    local file total=0
    while IFS= read -r -d '' file; do
        total=$((total + 1))

        if ! bash -n "$file" 2>/dev/null; then
            FAILED_PARSE+=("$file")
            bash -n "$file" 2>&1 | sed 's/^/    /' >&2 || true
            continue
        fi

        if have shellcheck; then
            if ! shellcheck -x -S "$SEVERITY" "$file"; then
                FAILED_LINT+=("$file")
            fi
        fi

        if have shfmt && ((!SKIP_FORMAT)); then
            if ((FIX)); then
                shfmt "${SHFMT_ARGS[@]}" -w "$file"
            elif ! shfmt "${SHFMT_ARGS[@]}" -d "$file"; then
                FAILED_FORMAT+=("$file")
            fi
        fi
    done < <(collect "${roots[@]}")

    printf '\n%s: %d file(s) checked\n' "$SCRIPT_NAME" "$total" >&2

    local rc=0
    report() {
        local label="$1"
        shift
        (($#)) || return 0
        printf '  %s: %d\n' "$label" "$#" >&2
        printf '    %s\n' "$@" >&2
        rc=1
    }

    report "syntax errors" "${FAILED_PARSE[@]+"${FAILED_PARSE[@]}"}"
    report "lint failures" "${FAILED_LINT[@]+"${FAILED_LINT[@]}"}"
    report "format failures (run FIX=1 to apply)" \
        "${FAILED_FORMAT[@]+"${FAILED_FORMAT[@]}"}"

    ((rc)) || printf '  all clean\n' >&2
    return "$rc"
}

main "$@"
