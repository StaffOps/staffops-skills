#!/usr/bin/env bash
#
# unit-doctor.sh — diagnose a systemd unit: static checks first, then
# (optionally) reload/restart and report exactly where it fails.
#
# Runs, in order, stopping at the first failure and explaining it:
#   1. the unit file exists and systemd knows about it
#   2. systemd-analyze verify (syntax, missing ExecStart, bad references)
#   3. daemon-reload
#   4. restart
#   5. is-active, with a wait loop for units that take time to report ready
#   6. on failure: status, recent journal, and the Result= classification
#
# Usage:
#   ./unit-doctor.sh myapp.service
#   ./unit-doctor.sh -n myapp.service          # static checks only, no restart
#   ./unit-doctor.sh -t 30 myapp.service       # wait up to 30s for active
#   ./unit-doctor.sh --user myapp.service      # user unit
#
# Requires systemctl and journalctl (i.e. an actual systemd, not a
# container without an init system).
#
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"

NO_RESTART=0
TIMEOUT=15
USER_FLAG=""

die() {
    printf '%s: %s\n' "$SCRIPT_NAME" "$*" >&2
    exit "${2:-1}"
}

usage() {
    cat <<EOF
${SCRIPT_NAME} — verify, reload, restart and diagnose a systemd unit.

Usage:
  ${SCRIPT_NAME} [-n] [-t SECONDS] [--user] UNIT

Options:
  -n         Static checks only (verify + cat); do not reload or restart
  -t N       Seconds to wait for the unit to report active (default: ${TIMEOUT})
  --user     Operate on a --user unit instead of the system manager
  -h         Help

Exit codes:
  0  the unit is active
  1  the unit failed, with diagnostics printed
  2  usage error, or systemctl is unavailable
EOF
}

sc() { systemctl $USER_FLAG "$@"; }
jc() { journalctl $USER_FLAG "$@"; }

step() { printf '\n==> %s\n' "$*" >&2; }
ok() { printf '    ok: %s\n' "$*" >&2; }
warn() { printf '    warn: %s\n' "$*" >&2; }
fail() { printf '    FAIL: %s\n' "$*" >&2; }

explain_result() {
    local unit="$1" result
    result="$(sc show -p Result --value "$unit" 2>/dev/null)"

    case "$result" in
        exit-code) fail "the process exited non-zero -- check ExecStart's own error output" ;;
        signal) fail "killed by a signal -- check for a crash (segfault) or an external kill" ;;
        timeout) fail "exceeded TimeoutStartSec or TimeoutStopSec -- is the readiness check (Type=) correct?" ;;
        oom-kill) fail "the unit's OWN MemoryMax was hit -- this is a self-inflicted limit, not host OOM" ;;
        watchdog) fail "missed an sd_notify watchdog ping -- WatchdogSec may be too tight, or the app hung" ;;
        start-limit-hit) fail "StartLimitBurst exhausted -- run: systemctl ${USER_FLAG} reset-failed ${unit}" ;;
        "") warn "no Result= reported yet" ;;
        *) fail "Result=${result}" ;;
    esac
}

main() {
    while (($#)); do
        case "$1" in
            -n)
                NO_RESTART=1
                shift
                ;;
            -t)
                TIMEOUT="${2:?-t requires a value}"
                shift 2
                ;;
            --user)
                USER_FLAG="--user"
                shift
                ;;
            -h | --help)
                usage
                exit 0
                ;;
            -*) die "unknown option: $1" 2 ;;
            *) break ;;
        esac
    done

    (($# == 1)) || {
        usage >&2
        exit 2
    }
    local unit="$1"

    command -v systemctl >/dev/null 2>&1 || die "systemctl not found -- is this a systemd system?" 2
    [[ "$TIMEOUT" =~ ^[0-9]+$ ]] || die "-t must be a number" 2

    step "checking systemd knows this unit"
    if ! sc cat "$unit" >/dev/null 2>&1; then
        fail "systemd has no unit named ${unit}"
        printf '    searched: /etc/systemd/system, /run/systemd/system, /lib/systemd/system\n' >&2
        printf '    if the file was just added, run: systemctl %s daemon-reload\n' "$USER_FLAG" >&2
        return 1
    fi
    ok "unit is known"

    step "static verification (systemd-analyze verify)"
    local verify_output
    if verify_output="$(systemd-analyze $USER_FLAG verify "$unit" 2>&1)"; then
        ok "no static errors"
    else
        # verify's output IS the diagnosis -- surface it directly rather than
        # re-deriving it.
        fail "systemd-analyze verify reported problems:"
        printf '%s\n' "$verify_output" | sed 's/^/      /' >&2
        return 1
    fi

    if ((NO_RESTART)); then
        step "effective unit (base + drop-ins)"
        sc cat "$unit" | sed 's/^/    /'
        return 0
    fi

    step "daemon-reload"
    sc daemon-reload && ok "reloaded"

    step "restart"
    if ! sc restart "$unit"; then
        fail "systemctl restart returned non-zero"
        explain_result "$unit"
        step "recent journal"
        jc -u "$unit" -n 30 --no-pager 2>&1 | sed 's/^/    /' || true
        return 1
    fi
    ok "restart command accepted"

    step "waiting up to ${TIMEOUT}s for active"
    local waited=0 state
    while ((waited < TIMEOUT)); do
        state="$(sc is-active "$unit" 2>/dev/null || true)"
        case "$state" in
            active)
                ok "active after ${waited}s"
                sc status "$unit" --no-pager -l | head -10 | sed 's/^/    /'
                return 0
                ;;
            failed)
                fail "entered failed state after ${waited}s"
                break
                ;;
        esac
        sleep 1
        waited=$((waited + 1))
    done

    if [[ "$state" != active ]]; then
        fail "did not become active within ${TIMEOUT}s (state: ${state:-unknown})"
        explain_result "$unit"
        step "status"
        # `systemctl status` intentionally returns non-zero for a non-active
        # unit (its own exit-code convention: 3 = not running). Under
        # `set -e -o pipefail` that status propagates through the pipe and
        # aborts THIS script immediately, skipping the journal section below
        # and returning systemctl's code (3) instead of ours (1). The `|| true`
        # is required, not decorative -- verified by running against a
        # deliberately failing unit, which exited 3 and dropped the journal
        # output before this guard was added.
        sc status "$unit" --no-pager -l 2>&1 | sed 's/^/    /' || true
        step "recent journal"
        jc -u "$unit" -n 30 --no-pager 2>&1 | sed 's/^/    /' || true
        return 1
    fi
}

main "$@"
