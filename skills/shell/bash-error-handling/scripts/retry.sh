#!/usr/bin/env bash
#
# retry.sh — run a command with bounded exponential backoff and jitter.
#
# Usage:
#   retry.sh [options] -- COMMAND [ARG ...]
#
# Options:
#   -a, --attempts N     Maximum attempts (default: 5)
#   -d, --delay SECONDS  Initial delay (default: 1)
#   -m, --max-delay SEC  Delay ceiling (default: 60)
#   -f, --factor N       Backoff multiplier (default: 2)
#   -j, --no-jitter      Disable randomized jitter
#   -r, --retry-on LIST  Comma-separated exit codes that are retryable.
#                        Default: retry on any non-zero status.
#   -q, --quiet          Suppress per-attempt diagnostics
#   -h, --help           Show this help
#
# Exit status:
#   The command's status from its final attempt, or 2 for a usage error.
#
# Examples:
#   retry.sh -- curl -fsS https://example.com/health
#   retry.sh -a 10 -d 2 -m 30 -- ./flaky-migration.sh
#   retry.sh --retry-on 7,28 -- curl -fsS "$url"     # only connect/timeout
#
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"

ATTEMPTS=5
DELAY=1
MAX_DELAY=60
FACTOR=2
JITTER=1
QUIET=0
RETRY_ON=""

die() {
    printf '%s: %s\n' "$SCRIPT_NAME" "$*" >&2
    exit 2
}

note() {
    ((QUIET)) || printf '%s: %s\n' "$SCRIPT_NAME" "$*" >&2
}

usage() {
    sed -n '3,28p' "$0" | sed 's/^# \{0,1\}//'
}

# Is $1 in the comma-separated RETRY_ON list? Empty list means "retry on any".
is_retryable() {
    local code="$1" candidate
    [[ -z "$RETRY_ON" ]] && return 0
    IFS=',' read -ra candidate <<<"$RETRY_ON"
    local c
    for c in "${candidate[@]}"; do
        [[ "$code" == "${c// /}" ]] && return 0
    done
    return 1
}

main() {
    while (($#)); do
        case "$1" in
            -a | --attempts)
                ATTEMPTS="${2:?--attempts needs a value}"
                shift 2
                ;;
            -d | --delay)
                DELAY="${2:?--delay needs a value}"
                shift 2
                ;;
            -m | --max-delay)
                MAX_DELAY="${2:?--max-delay needs a value}"
                shift 2
                ;;
            -f | --factor)
                FACTOR="${2:?--factor needs a value}"
                shift 2
                ;;
            -r | --retry-on)
                RETRY_ON="${2:?--retry-on needs a value}"
                shift 2
                ;;
            -j | --no-jitter)
                JITTER=0
                shift
                ;;
            -q | --quiet)
                QUIET=1
                shift
                ;;
            -h | --help)
                usage
                exit 0
                ;;
            --)
                shift
                break
                ;;
            -*) die "unknown option: $1" ;;
            *) break ;;
        esac
    done

    (($#)) || die "no command given (did you forget '--'?)"

    require_positive_int() {
        local name="$1" value="$2"
        if ! [[ "$value" =~ ^[0-9]+$ ]] || ((value < 1)); then
            die "${name} must be a positive integer, got: ${value}"
        fi
    }
    require_non_negative_int() {
        local name="$1" value="$2"
        if ! [[ "$value" =~ ^[0-9]+$ ]]; then
            die "${name} must be a non-negative integer, got: ${value}"
        fi
    }

    require_positive_int --attempts "$ATTEMPTS"
    require_positive_int --factor "$FACTOR"
    require_non_negative_int --delay "$DELAY"
    require_non_negative_int --max-delay "$MAX_DELAY"

    local attempt=1 delay="$DELAY" status=0 sleep_for

    while :; do
        # Temporarily disable errexit so a failure is captured, not fatal.
        set +e
        "$@"
        status=$?
        set -e

        ((status == 0)) && return 0

        if ! is_retryable "$status"; then
            note "exit ${status} is not retryable, giving up"
            return "$status"
        fi

        if ((attempt >= ATTEMPTS)); then
            note "attempt ${attempt}/${ATTEMPTS} failed (exit ${status}), giving up"
            return "$status"
        fi

        sleep_for="$delay"
        # Full jitter: sleep a random duration in [0, delay]. Spreads a
        # thundering herd far better than a fixed backoff.
        ((JITTER)) && sleep_for=$((RANDOM % (delay + 1)))
        ((sleep_for < 1)) && sleep_for=1

        note "attempt ${attempt}/${ATTEMPTS} failed (exit ${status}), retrying in ${sleep_for}s"
        sleep "$sleep_for"

        delay=$((delay * FACTOR))
        ((delay > MAX_DELAY)) && delay="$MAX_DELAY"
        ((attempt++))
    done
}

main "$@"
