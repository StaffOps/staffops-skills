#!/usr/bin/env bash
#
# parse-access-log.sh — worked example applying every rule from the skill.
#
# Summarizes an nginx/Apache combined-format access log: request counts by
# status class, the slowest endpoints, and the top client addresses.
#
# Demonstrates:
#   - strict mode and an EXIT trap
#   - arrays for dynamic command lines
#   - associative arrays for counting
#   - `while IFS= read -r` for safe line reading
#   - parameter expansion instead of basename/cut/sed
#   - printf instead of echo
#   - a single awk pass instead of per-line external commands
#
# Usage:
#   ./parse-access-log.sh access.log
#   ./parse-access-log.sh -n 20 access.log
#   gzip -dc access.log.gz | ./parse-access-log.sh -
#
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"
WORKDIR=""

cleanup() {
    local rc=$?
    [[ -n "$WORKDIR" && -d "$WORKDIR" ]] && rm -rf -- "$WORKDIR"
    exit "$rc"
}
trap cleanup EXIT
trap 'printf "%s: interrupted\n" "$SCRIPT_NAME" >&2; exit 130' INT TERM

die() {
    printf '%s: %s\n' "$SCRIPT_NAME" "$*" >&2
    exit 1
}

usage() {
    cat <<EOF
${SCRIPT_NAME} — summarize a combined-format access log.

Usage:
  ${SCRIPT_NAME} [-n TOP] [-s] LOGFILE
  ${SCRIPT_NAME} [-n TOP] -            read from stdin

Options:
  -n TOP   How many rows per section (default: 10)
  -s       Skip the slow-request section
  -h       Help
EOF
}

# ---------------------------------------------------------------------------
# Status classes counted in pure Bash, to show associative arrays.
# ---------------------------------------------------------------------------
summarize_status() {
    local file="$1"
    declare -A classes=()
    local total=0 line status class

    while IFS= read -r line; do
        # Combined format: host - - [time] "METHOD path proto" status bytes ...
        # Strip everything through the closing quote, then take the next field.
        status="${line#*\" }"
        status="${status%% *}"

        [[ "$status" =~ ^[0-9]{3}$ ]] || continue

        class="${status:0:1}xx"
        classes[$class]=$((${classes[$class]:-0} + 1))
        total=$((total + 1))
    done <"$file"

    ((total)) || die 'no parseable log lines found'

    printf '\nRequests by status class (%d total)\n' "$total"
    printf '%s\n' '-----------------------------------'

    local key pct
    for key in $(printf '%s\n' "${!classes[@]}" | sort); do
        # Bash has no floats -- awk does the percentage.
        pct="$(awk -v a="${classes[$key]}" -v b="$total" \
            'BEGIN { printf "%.1f", a / b * 100 }')"
        printf '%-6s %8d  %5s%%\n' "$key" "${classes[$key]}" "$pct"
    done
}

# ---------------------------------------------------------------------------
# One awk pass instead of a pipeline of per-line commands.
# ---------------------------------------------------------------------------
summarize_clients() {
    local file="$1" top="$2"

    printf '\nTop %d client addresses\n' "$top"
    printf '%s\n' '-----------------------------------'

    awk '{ count[$1]++ } END { for (ip in count) printf "%8d  %s\n", count[ip], ip }' \
        "$file" | sort -rn | head -n "$top"
}

summarize_slow() {
    local file="$1" top="$2"

    # $NF is request_time only when the log format appends it. Detect first.
    if ! awk 'NR == 1 { exit ($NF ~ /^[0-9]+\.[0-9]+$/) ? 0 : 1 }' "$file"; then
        printf '\n(no request_time field in this log format, skipping)\n'
        return 0
    fi

    printf '\nSlowest %d requests\n' "$top"
    printf '%s\n' '-----------------------------------'

    awk '{
        # Request is the quoted field; strip the surrounding quotes.
        match($0, /"[^"]*"/)
        req = substr($0, RSTART + 1, RLENGTH - 2)
        printf "%8.3fs  %s\n", $NF, req
    }' "$file" | sort -rn | head -n "$top"
}

main() {
    local top=10 skip_slow=0

    while getopts ':n:sh' opt; do
        case "$opt" in
            n) top="$OPTARG" ;;
            s) skip_slow=1 ;;
            h)
                usage
                exit 0
                ;;
            :) die "option -${OPTARG} requires an argument" ;;
            \?) die "unknown option: -${OPTARG}" ;;
        esac
    done
    shift $((OPTIND - 1))

    (($# == 1)) || {
        usage >&2
        exit 2
    }
    [[ "$top" =~ ^[0-9]+$ ]] || die "-n must be a number, got: ${top}"

    local input="$1" file

    # Reading stdin twice is impossible, so materialize it once.
    if [[ "$input" == "-" ]]; then
        WORKDIR="$(mktemp -d)"
        file="${WORKDIR}/stdin.log"
        cat >"$file"
    else
        [[ -r "$input" ]] || die "cannot read: ${input}"
        file="$input"
    fi

    printf '%s\n' "=== ${input##*/} ==="

    summarize_status "$file"
    summarize_clients "$file" "$top"
    ((skip_slow)) || summarize_slow "$file" "$top"
}

main "$@"
