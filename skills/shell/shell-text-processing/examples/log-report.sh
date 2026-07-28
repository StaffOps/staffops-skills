#!/usr/bin/env bash
#
# log-report.sh — worked example composing grep, awk, sort and uniq into a
# single report over a combined-format access log.
#
# Demonstrates:
#   - one awk pass instead of a long pipeline (and when each is preferable)
#   - associative arrays for grouping
#   - awk for floating-point math that Bash cannot do
#   - `sort | uniq -c | sort -rn` frequency counting
#   - LC_ALL=C for reproducible ordering
#   - passing shell values in with -v rather than interpolating
#
# Usage:
#   ./log-report.sh access.log
#   ./log-report.sh -t 0.5 -n 5 access.log     # slow threshold 500ms, top 5
#   ./log-report.sh --self-test                # run built-in assertions
#
set -Eeuo pipefail

# Byte-order sorting, locale-independent and reproducible.
export LC_ALL=C

readonly SCRIPT_NAME="${0##*/}"

TOP=10
SLOW_THRESHOLD=1.0

die() {
    printf '%s: %s\n' "$SCRIPT_NAME" "$*" >&2
    exit 1
}

usage() {
    cat <<EOF
${SCRIPT_NAME} — summarize a combined-format access log.

Usage:
  ${SCRIPT_NAME} [-n TOP] [-t SECONDS] LOGFILE

Options:
  -n TOP       Rows per section (default: ${TOP})
  -t SECONDS   Slow-request threshold (default: ${SLOW_THRESHOLD})
  --self-test  Run assertions against generated fixture data
  -h           Help

Expected format (nginx combined + \$request_time):
  IP - - [time] "METHOD path proto" status bytes "ref" "ua" rtime
EOF
}

rule() { printf '%s\n' '--------------------------------------------------'; }

# ---------------------------------------------------------------------------
# Section 1 — status classes.
#
# Single awk pass: group, then compute percentages in END. Bash has no floats,
# so the percentage must happen inside awk.
# ---------------------------------------------------------------------------
report_status() {
    local file="$1"

    printf '\nStatus classes\n'
    rule
    awk '
        $9 ~ /^[0-9]{3}$/ { class[substr($9, 1, 1) "xx"]++; total++ }
        END {
            if (!total) { print "no parseable records"; exit }
            for (c in class)
                printf "%-6s %8d  %6.2f%%\n", c, class[c], class[c] / total * 100
        }
    ' "$file" | sort
}

# ---------------------------------------------------------------------------
# Section 2 — top endpoints by request count.
#
# The request is field 7 in the quoted "METHOD path proto" group. Query
# strings are stripped so /a?id=1 and /a?id=2 aggregate together.
# ---------------------------------------------------------------------------
report_endpoints() {
    local file="$1" top="$2"

    printf '\nTop %d endpoints\n' "$top"
    rule
    awk '{ sub(/\?.*/, "", $7); count[$7]++ }
         END { for (p in count) printf "%8d  %s\n", count[p], p }' "$file" \
        | sort -rn | head -n "$top"
}

# ---------------------------------------------------------------------------
# Section 3 — error rate per endpoint.
#
# Shows why one awk pass beats a pipeline here: two counters per key would
# otherwise need two passes and a join.
# ---------------------------------------------------------------------------
report_error_rate() {
    local file="$1" top="$2"

    printf '\nEndpoints by error rate (5xx)\n'
    rule
    awk -v top="$top" '
        {
            sub(/\?.*/, "", $7)
            total[$7]++
            if ($9 ~ /^5/) errors[$7]++
        }
        END {
            for (p in total) {
                e = (p in errors) ? errors[p] : 0
                if (e > 0)
                    printf "%6.2f%%  %5d/%-5d  %s\n", e / total[p] * 100, e, total[p], p
            }
        }
    ' "$file" | sort -rn | head -n "$top"
}

# ---------------------------------------------------------------------------
# Section 4 — latency percentiles.
#
# Percentiles need the values sorted, so this is a genuine two-stage pipeline:
# extract with awk, sort numerically, then index in a second awk.
# ---------------------------------------------------------------------------
report_latency() {
    local file="$1"

    # Only run if the log actually carries a request-time field.
    if ! awk 'NR == 1 { exit ($NF ~ /^[0-9]+(\.[0-9]+)?$/) ? 0 : 1 }' "$file"; then
        printf '\n(no request_time field; skipping latency)\n'
        return 0
    fi

    printf '\nLatency\n'
    rule
    awk '{ print $NF }' "$file" \
        | sort -n \
        | awk '
            { v[NR] = $1; sum += $1 }
            END {
                if (!NR) exit
                printf "%-6s %8.3fs\n", "min",  v[1]
                printf "%-6s %8.3fs\n", "avg",  sum / NR
                printf "%-6s %8.3fs\n", "p50",  v[int(NR * 0.50) + (NR > 1)]
                printf "%-6s %8.3fs\n", "p95",  v[int(NR * 0.95) + (NR > 1)]
                printf "%-6s %8.3fs\n", "p99",  v[int(NR * 0.99) + (NR > 1)]
                printf "%-6s %8.3fs\n", "max",  v[NR]
            }
        '
}

# ---------------------------------------------------------------------------
# Section 5 — slow requests.
#
# -v passes the shell threshold in safely; interpolating it into the program
# text would break on quoting and allow injection.
# ---------------------------------------------------------------------------
report_slow() {
    local file="$1" top="$2" threshold="$3"

    printf '\nRequests slower than %ss\n' "$threshold"
    rule
    awk -v t="$threshold" '
        $NF ~ /^[0-9]+(\.[0-9]+)?$/ && $NF + 0 > t {
            match($0, /"[^"]*"/)
            printf "%8.3fs  %s\n", $NF, substr($0, RSTART + 1, RLENGTH - 2)
        }
    ' "$file" | sort -rn | head -n "$top"
}

# ---------------------------------------------------------------------------
# Section 6 — classic frequency count.
#
# `sort | uniq -c | sort -rn` is the idiomatic pipeline. uniq only collapses
# ADJACENT duplicates, which is why the first sort is mandatory.
# ---------------------------------------------------------------------------
report_clients() {
    local file="$1" top="$2"

    printf '\nTop %d clients\n' "$top"
    rule
    awk '{ print $1 }' "$file" \
        | sort \
        | uniq -c \
        | sort -rn \
        | head -n "$top" \
        | awk '{ printf "%8d  %s\n", $1, $2 }'
}

# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
self_test() {
    local tmp
    tmp="$(mktemp -d)"
    # Deliberately not a RETURN trap: in Bash that trap is global, so it would
    # also fire when main() returns, by which point $tmp is out of scope and
    # `set -u` aborts. Cleanup happens explicitly at the end of this function.

    local log="${tmp}/access.log"
    cat >"$log" <<'EOF'
10.0.0.1 - - [01/Jan/2026:00:00:00 +0000] "GET /api/users?id=1 HTTP/1.1" 200 120 "-" "curl" 0.050
10.0.0.1 - - [01/Jan/2026:00:00:01 +0000] "GET /api/users?id=2 HTTP/1.1" 200 118 "-" "curl" 0.060
10.0.0.2 - - [01/Jan/2026:00:00:02 +0000] "POST /api/orders HTTP/1.1" 500 44 "-" "curl" 2.300
10.0.0.2 - - [01/Jan/2026:00:00:03 +0000] "POST /api/orders HTTP/1.1" 500 44 "-" "curl" 1.900
10.0.0.3 - - [01/Jan/2026:00:00:04 +0000] "GET /health HTTP/1.1" 200 2 "-" "kube" 0.001
10.0.0.1 - - [01/Jan/2026:00:00:05 +0000] "GET /missing HTTP/1.1" 404 9 "-" "curl" 0.010
EOF

    local failures=0
    # Compare with runs of whitespace collapsed, so column padding changes do
    # not break the assertions.
    check() {
        local desc="$1" expected="$2" actual="$3"
        local norm_expected norm_actual
        norm_expected="$(printf '%s' "$expected" | tr -s '[:space:]' ' ')"
        norm_actual="$(printf '%s' "$actual" | tr -s '[:space:]' ' ')"
        if [[ "$norm_actual" == *"$norm_expected"* ]]; then
            printf 'ok    %s\n' "$desc"
        else
            printf 'FAIL  %s\n      expected to contain: %s\n      got: %s\n' \
                "$desc" "$expected" "$actual" >&2
            failures=$((failures + 1))
        fi
    }

    check "3 requests are 2xx" \
        "2xx          3" "$(report_status "$log")"
    check "/api/orders has 2 requests" \
        "2  /api/orders" "$(report_endpoints "$log" 10)"
    check "/api/orders is 100% errors" \
        "100.00%" "$(report_error_rate "$log" 10)"
    check "query strings are stripped" \
        "2  /api/users" "$(report_endpoints "$log" 10)"
    check "10.0.0.1 is the top client with 3" \
        "3  10.0.0.1" "$(report_clients "$log" 10)"
    check "max latency is 2.3s" \
        "2.300s" "$(report_latency "$log")"
    check "two requests exceed 1s" \
        "2.300s" "$(report_slow "$log" 10 1.0)"

    rm -rf -- "$tmp"

    printf '\n%d failure(s)\n' "$failures"
    return $((failures > 0))
}

main() {
    if [[ "${1:-}" == "--self-test" ]]; then
        self_test
        return
    fi

    local opt
    while getopts ':n:t:h' opt; do
        case "$opt" in
            n) TOP="$OPTARG" ;;
            t) SLOW_THRESHOLD="$OPTARG" ;;
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
    local file="$1"
    [[ -r "$file" ]] || die "cannot read: ${file}"

    printf '=== %s ===\n' "${file##*/}"
    report_status "$file"
    report_endpoints "$file" "$TOP"
    report_error_rate "$file" "$TOP"
    report_clients "$file" "$TOP"
    report_latency "$file"
    report_slow "$file" "$TOP" "$SLOW_THRESHOLD"
}

main "$@"
