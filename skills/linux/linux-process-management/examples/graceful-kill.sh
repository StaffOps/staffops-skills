#!/usr/bin/env bash
#
# graceful-kill.sh — terminate processes the way an init system does.
#
# Sends SIGTERM, waits for the process to exit, and only then escalates to
# SIGKILL. Handles the cases a naive `kill -9` gets wrong:
#   - D-state processes, which ignore SIGKILL entirely
#   - zombies, which are already dead
#   - PID reuse between the check and the signal
#   - process groups and whole trees
#
# Usage:
#   ./graceful-kill.sh 1234
#   ./graceful-kill.sh -t 30 -n myworker         # match by name
#   ./graceful-kill.sh -g 1234                   # signal the whole process group
#   ./graceful-kill.sh -T 1234                   # signal the process tree
#   ./graceful-kill.sh -d 1234                   # dry run
#
# Exit codes:
#   0  every target exited
#   1  at least one target survived
#   2  usage error
#   3  nothing matched
#
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"

TIMEOUT=10
DRY_RUN=0
GROUP=0
TREE=0
BY_NAME=""
FIRST_SIGNAL="TERM"

die() {
    printf '%s: %s\n' "$SCRIPT_NAME" "$*" >&2
    exit "${2:-1}"
}
info() { printf '%s\n' "$*" >&2; }

usage() {
    cat <<EOF
${SCRIPT_NAME} — SIGTERM, wait, then SIGKILL.

Usage:
  ${SCRIPT_NAME} [options] PID...
  ${SCRIPT_NAME} [options] -n NAME

Options:
  -t SECONDS  Grace period before SIGKILL (default: ${TIMEOUT})
  -s SIGNAL   First signal instead of TERM (e.g. INT, HUP, QUIT)
  -n NAME     Select targets by command-line pattern
  -g          Signal the process GROUP (negative PID)
  -T          Signal the process and all descendants
  -d          Dry run: report what would happen
  -h          Help

Exit codes:
  0 all exited   1 some survived   2 usage error   3 nothing matched
EOF
}

# True while the PID exists and we may signal it. `kill -0` sends nothing.
alive() { kill -0 "$1" 2>/dev/null; }

state_of() {
    awk '{ print $3 }' "/proc/$1/stat" 2>/dev/null \
        || printf '?'
}

# A process's start time distinguishes it from a later PID reuse.
starttime_of() {
    # Field 22 of /proc/<pid>/stat, but comm may contain spaces and
    # parentheses, so split on the LAST ')' first.
    local raw
    raw="$(cat "/proc/$1/stat" 2>/dev/null)" || return 1
    printf '%s' "${raw##*) }" | awk '{ print $20 }'
}

descendants() {
    local root="$1"
    local -a queue=("$root") out=()
    local pid child

    while ((${#queue[@]})); do
        pid="${queue[0]}"
        queue=("${queue[@]:1}")
        out+=("$pid")
        while read -r child; do
            [[ -n "$child" ]] && queue+=("$child")
        done < <(pgrep -P "$pid" 2>/dev/null || true)
    done

    # Children first, so parents cannot respawn them mid-shutdown.
    local i
    for ((i = ${#out[@]} - 1; i >= 0; i--)); do
        printf '%s\n' "${out[i]}"
    done
}

# Send a signal, honoring -g (process group) and dry-run mode.
signal_target() {
    local pid="$1" sig="$2"
    local target="$pid"
    ((GROUP)) && target="-$pid"

    if ((DRY_RUN)); then
        info "  would send SIG${sig} to ${target}"
        return 0
    fi
    kill -"$sig" "$target" 2>/dev/null || return 1
}

terminate() {
    local pid="$1"
    local start_before state

    if ! alive "$pid"; then
        info "pid ${pid}: not running"
        return 0
    fi

    start_before="$(starttime_of "$pid" || true)"
    state="$(state_of "$pid")"

    case "$state" in
        Z)
            info "pid ${pid}: zombie -- already dead; its parent is not reaping it"
            info "  parent: $(awk '{print $4}' "/proc/${pid}/stat" 2>/dev/null)"
            return 0
            ;;
        D)
            info "pid ${pid}: uninterruptible sleep (blocked in $(cat "/proc/${pid}/wchan" 2>/dev/null))"
            info "  SIGKILL will NOT work; resolve the blocking I/O instead"
            ;;
    esac

    info "pid ${pid}: sending SIG${FIRST_SIGNAL} ($(tr '\0' ' ' <"/proc/${pid}/cmdline" 2>/dev/null | cut -c1-60))"
    signal_target "$pid" "$FIRST_SIGNAL" || {
        info "  could not signal (permission?)"
        return 1
    }

    ((DRY_RUN)) && {
        info "  would wait up to ${TIMEOUT}s, then SIGKILL"
        return 0
    }

    local waited=0
    while ((waited < TIMEOUT)); do
        alive "$pid" || {
            info "  exited after ${waited}s"
            return 0
        }
        # A zombie counts as exited for our purposes.
        [[ "$(state_of "$pid")" == "Z" ]] && {
            info "  exited (now a zombie awaiting reap) after ${waited}s"
            return 0
        }
        sleep 1
        waited=$((waited + 1))
    done

    # Guard against PID reuse: only escalate if it is still the SAME process.
    local start_after
    start_after="$(starttime_of "$pid" || true)"
    if [[ -n "$start_before" && "$start_before" != "$start_after" ]]; then
        info "  pid ${pid} was reused by a different process; not escalating"
        return 0
    fi

    info "  still alive after ${TIMEOUT}s, sending SIGKILL"
    signal_target "$pid" KILL || true

    sleep 1
    if alive "$pid" && [[ "$(state_of "$pid")" != "Z" ]]; then
        info "  SURVIVED SIGKILL (state $(state_of "$pid")) -- almost certainly stuck in the kernel"
        return 1
    fi

    info "  killed"
    return 0
}

main() {
    local opt
    while getopts ':t:s:n:gTdh' opt; do
        case "$opt" in
            t) TIMEOUT="$OPTARG" ;;
            s) FIRST_SIGNAL="${OPTARG#SIG}" ;;
            n) BY_NAME="$OPTARG" ;;
            g) GROUP=1 ;;
            T) TREE=1 ;;
            d) DRY_RUN=1 ;;
            h)
                usage
                exit 0
                ;;
            :) die "option -${OPTARG} requires an argument" 2 ;;
            \?) die "unknown option: -${OPTARG}" 2 ;;
        esac
    done
    shift $((OPTIND - 1))

    [[ "$TIMEOUT" =~ ^[0-9]+$ ]] || die "-t must be a number" 2

    local -a targets=()
    if [[ -n "$BY_NAME" ]]; then
        mapfile -t targets < <(pgrep -f -- "$BY_NAME" 2>/dev/null || true)
        ((${#targets[@]})) || {
            info "no process matching: ${BY_NAME}"
            exit 3
        }
        # Never signal ourselves OR any ancestor.
        #
        # `pgrep -f` matches the pattern anywhere in a command line, which
        # includes the shell that invoked this script -- the pattern is
        # literally an argument on it. Without this filter, searching for a
        # name that does not exist kills the caller instead of reporting
        # "nothing matched". Verified: it terminated the test harness.
        local -A excluded=()
        local anc="$$"
        while [[ -n "$anc" && "$anc" != "0" ]]; do
            excluded["$anc"]=1
            anc="$(awk '{print $4}' "/proc/${anc}/stat" 2>/dev/null || true)"
        done

        local -a filtered=()
        local p cmdline
        for p in "${targets[@]}"; do
            [[ -n "${excluded[$p]:-}" ]] && continue

            # Drop matches that already exited -- pgrep itself and the
            # subshells created for command substitution routinely appear in
            # its own output and are gone microseconds later.
            alive "$p" || continue

            # Drop any process running this very script.
            cmdline="$(tr '\0' ' ' <"/proc/${p}/cmdline" 2>/dev/null || true)"
            [[ "$cmdline" == *"$SCRIPT_NAME"* ]] && continue

            filtered+=("$p")
        done
        targets=("${filtered[@]}")

        ((${#targets[@]})) || {
            info "no process matching: ${BY_NAME} (excluding this script's own ancestry)"
            exit 3
        }
    else
        (($#)) || {
            usage >&2
            exit 2
        }
        targets=("$@")
    fi

    ((${#targets[@]})) || {
        info "nothing to do"
        exit 3
    }

    if ((TREE)); then
        local -a expanded=()
        local root
        for root in "${targets[@]}"; do
            mapfile -t -O "${#expanded[@]}" expanded < <(descendants "$root")
        done
        targets=("${expanded[@]}")
        info "tree expands to ${#targets[@]} process(es)"
    fi

    local rc=0 pid
    for pid in "${targets[@]}"; do
        [[ "$pid" =~ ^[0-9]+$ ]] || {
            info "skipping non-PID: ${pid}"
            continue
        }
        terminate "$pid" || rc=1
    done

    return "$rc"
}

main "$@"
