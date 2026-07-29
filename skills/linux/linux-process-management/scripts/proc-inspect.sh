#!/usr/bin/env bash
#
# proc-inspect.sh — one-shot diagnostic report for a running process.
#
# Gathers, from /proc and cgroup files, everything usually needed to answer
# "what is this process doing and why is it unhealthy":
#   identity, state and blocking function, memory (RSS vs anon), descriptors
#   against the real limit, thread count, context switches, I/O, cgroup limits
#   and OOM counters, plus the child tree.
#
# Usage:
#   ./proc-inspect.sh 1234
#   ./proc-inspect.sh -n nginx          # first match by name
#   ./proc-inspect.sh -a -n nginx       # every match
#
# Exit codes:
#   0  process found and reported
#   1  process not found
#   2  usage error
#
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"

ALL=0
BY_NAME=""

die() {
    printf '%s: %s\n' "$SCRIPT_NAME" "$*" >&2
    exit "${2:-1}"
}

usage() {
    cat <<EOF
${SCRIPT_NAME} — diagnostic report for a process.

Usage:
  ${SCRIPT_NAME} PID
  ${SCRIPT_NAME} -n NAME [-a]

Options:
  -n NAME  Look the process up by name/pattern
  -a       With -n, report every match instead of the first
  -h       Help
EOF
}

kv() { printf '  %-22s %s\n' "$1" "$2"; }

# Read "Key: value" style fields out of /proc/<pid>/status.
status_field() {
    local pid="$1" key="$2"
    awk -v k="^${key}:" '$0 ~ k { $1=""; sub(/^[ \t]+/, ""); print; exit }' \
        "/proc/${pid}/status" 2>/dev/null
}

human_kb() {
    local kb="${1:-0}"
    [[ "$kb" =~ ^[0-9]+$ ]] || {
        printf '%s' "${1:-n/a}"
        return
    }
    awk -v k="$kb" 'BEGIN {
        if (k >= 1048576) printf "%.2f GiB", k/1048576
        else if (k >= 1024) printf "%.1f MiB", k/1024
        else printf "%d KiB", k
    }'
}

human_bytes() {
    local b="${1:-0}"
    [[ "$b" =~ ^[0-9]+$ ]] || {
        printf '%s' "${1:-n/a}"
        return
    }
    awk -v b="$b" 'BEGIN {
        if (b >= 1073741824) printf "%.2f GiB", b/1073741824
        else if (b >= 1048576) printf "%.1f MiB", b/1048576
        else if (b >= 1024) printf "%.1f KiB", b/1024
        else printf "%d B", b
    }'
}

section() { printf '\n--- %s\n' "$1"; }

report_identity() {
    local pid="$1"
    section "identity"
    kv "pid" "$pid"
    kv "name" "$(status_field "$pid" Name)"
    kv "ppid" "$(status_field "$pid" PPid)"
    kv "uid" "$(status_field "$pid" Uid | awk '{print $1}')"

    local cmd
    cmd="$(tr '\0' ' ' <"/proc/${pid}/cmdline" 2>/dev/null)"
    kv "cmdline" "${cmd:-<kernel thread>}"

    local exe
    exe="$(readlink "/proc/${pid}/exe" 2>/dev/null || printf 'n/a')"
    kv "exe" "$exe"
    [[ "$exe" == *"(deleted)" ]] \
        && printf '  %-22s %s\n' "" "WARNING: binary replaced on disk; restart to pick it up"

    kv "cwd" "$(readlink "/proc/${pid}/cwd" 2>/dev/null || printf 'n/a')"
    kv "started" "$(ps -p "$pid" -o lstart= 2>/dev/null | sed 's/^ *//')"
    kv "elapsed" "$(ps -p "$pid" -o etime= 2>/dev/null | sed 's/^ *//')"
}

report_state() {
    local pid="$1"
    section "state"
    local state
    state="$(status_field "$pid" State)"
    kv "state" "$state"

    case "$state" in
        D*) printf '  %-22s %s\n' "" "uninterruptible sleep: blocked in the kernel, SIGKILL will NOT work" ;;
        Z*) printf '  %-22s %s\n' "" "zombie: already dead; fix the parent, which is not reaping" ;;
        T*) printf '  %-22s %s\n' "" "stopped: send SIGCONT to resume" ;;
    esac

    local wchan
    wchan="$(cat "/proc/${pid}/wchan" 2>/dev/null || true)"
    [[ -n "$wchan" && "$wchan" != "0" ]] && kv "blocked in" "$wchan"

    kv "threads" "$(status_field "$pid" Threads)"
    kv "ctx switches (vol)" "$(status_field "$pid" voluntary_ctxt_switches)"
    kv "ctx switches (invol)" "$(status_field "$pid" nonvoluntary_ctxt_switches)"
    printf '  %-22s %s\n' "" "high involuntary = CPU contention; high voluntary = waiting on I/O or locks"
}

report_memory() {
    local pid="$1"
    section "memory"
    kv "VmRSS (resident)" "$(human_kb "$(status_field "$pid" VmRSS | awk '{print $1}')")"
    kv "RssAnon (heap/stack)" "$(human_kb "$(status_field "$pid" RssAnon | awk '{print $1}')")"
    kv "RssFile (page cache)" "$(human_kb "$(status_field "$pid" RssFile | awk '{print $1}')")"
    kv "VmSwap" "$(human_kb "$(status_field "$pid" VmSwap | awk '{print $1}')")"
    kv "VmSize (virtual)" "$(human_kb "$(status_field "$pid" VmSize | awk '{print $1}')")"
    printf '  %-22s %s\n' "" "alert on RssAnon, not VmSize"
    kv "oom_score" "$(cat "/proc/${pid}/oom_score" 2>/dev/null || printf 'n/a')"
    kv "oom_score_adj" "$(cat "/proc/${pid}/oom_score_adj" 2>/dev/null || printf 'n/a')"
}

report_fds() {
    local pid="$1"
    section "file descriptors"
    local count limit
    # `find`, not `ls`: consistent with the rule these skills teach, and it
    # does not choke if the directory disappears mid-read.
    count="$(find "/proc/${pid}/fd" -maxdepth 1 -mindepth 1 2>/dev/null | wc -l | tr -d ' ')"
    limit="$(awk '/Max open files/ { print $4 }' "/proc/${pid}/limits" 2>/dev/null)"
    kv "open" "$count"
    kv "soft limit" "${limit:-unknown}"

    if [[ "$limit" =~ ^[0-9]+$ ]] && ((limit > 0)); then
        local pct=$((count * 100 / limit))
        kv "utilization" "${pct}%"
        ((pct >= 80)) && printf '  %-22s %s\n' "" "WARNING: approaching the descriptor limit"
    fi

    local socks pipes
    socks="$(find "/proc/${pid}/fd" -maxdepth 1 -type l -lname 'socket:*' 2>/dev/null | wc -l | tr -d ' ')"
    pipes="$(find "/proc/${pid}/fd" -maxdepth 1 -type l -lname 'pipe:*' 2>/dev/null | wc -l | tr -d ' ')"
    kv "sockets" "$socks"
    kv "pipes" "$pipes"
}

report_io() {
    local pid="$1"
    [[ -r "/proc/${pid}/io" ]] || return 0
    section "io"
    kv "read (syscalls)" "$(human_bytes "$(awk '/^rchar/ {print $2}' "/proc/${pid}/io")")"
    kv "written (syscalls)" "$(human_bytes "$(awk '/^wchar/ {print $2}' "/proc/${pid}/io")")"
    kv "read (device)" "$(human_bytes "$(awk '/^read_bytes/ {print $2}' "/proc/${pid}/io")")"
    kv "written (device)" "$(human_bytes "$(awk '/^write_bytes/ {print $2}' "/proc/${pid}/io")")"
    printf '  %-22s %s\n' "" "syscall >> device means the page cache is absorbing it"
}

report_cgroup() {
    local pid="$1"
    local path
    path="$(awk -F: '$1 == "0" { print $3 }' "/proc/${pid}/cgroup" 2>/dev/null)"
    [[ -n "$path" ]] || return 0

    section "cgroup"
    kv "path" "$path"

    local base="/sys/fs/cgroup${path}"
    [[ -d "$base" ]] || {
        printf '  %-22s %s\n' "" "(not readable from this namespace)"
        return 0
    }

    local f
    for f in memory.current memory.high memory.max; do
        [[ -r "${base}/${f}" ]] && kv "$f" "$(human_bytes "$(cat "${base}/${f}")" 2>/dev/null || cat "${base}/${f}")"
    done

    if [[ -r "${base}/memory.events" ]]; then
        local oom_kill high
        oom_kill="$(awk '/^oom_kill/ {print $2}' "${base}/memory.events")"
        high="$(awk '/^high/ {print $2}' "${base}/memory.events")"
        kv "oom_kill count" "${oom_kill:-0}"
        kv "high (throttled)" "${high:-0}"
        [[ "${oom_kill:-0}" != "0" ]] \
            && printf '  %-22s %s\n' "" "this cgroup HAS been OOM-killed (exit 137)"
        [[ "${high:-0}" != "0" ]] \
            && printf '  %-22s %s\n' "" "hitting memory.high: reclaim throttling, shows up as latency"
    fi

    if [[ -r "${base}/cpu.stat" ]]; then
        local periods throttled
        periods="$(awk '/^nr_periods/ {print $2}' "${base}/cpu.stat")"
        throttled="$(awk '/^nr_throttled/ {print $2}' "${base}/cpu.stat")"
        kv "cpu periods" "${periods:-0}"
        kv "cpu throttled" "${throttled:-0}"
        if [[ "${periods:-0}" =~ ^[0-9]+$ ]] && ((periods > 0)); then
            local pct=$((throttled * 100 / periods))
            kv "throttled %" "${pct}%"
            ((pct >= 5)) && printf '  %-22s %s\n' "" "WARNING: CPU quota is too low for this workload"
        fi
    fi
}

report_children() {
    local pid="$1"
    section "children"
    if command -v pstree >/dev/null 2>&1; then
        pstree -p "$pid" 2>/dev/null | head -20 | sed 's/^/  /'
    else
        ps --ppid "$pid" -o pid,stat,cmd --no-headers 2>/dev/null | sed 's/^/  /' \
            || printf '  none\n'
    fi
}

inspect() {
    local pid="$1"
    [[ -d "/proc/${pid}" ]] || die "no such process: ${pid}"

    printf '==================== PID %s ====================\n' "$pid"
    report_identity "$pid"
    report_state "$pid"
    report_memory "$pid"
    report_fds "$pid"
    report_io "$pid"
    report_cgroup "$pid"
    report_children "$pid"
    printf '\n'
}

main() {
    local opt
    while getopts ':n:ah' opt; do
        case "$opt" in
            n) BY_NAME="$OPTARG" ;;
            a) ALL=1 ;;
            h)
                usage
                exit 0
                ;;
            :) die "option -${OPTARG} requires an argument" 2 ;;
            \?) die "unknown option: -${OPTARG}" 2 ;;
        esac
    done
    shift $((OPTIND - 1))

    local -a pids=()

    if [[ -n "$BY_NAME" ]]; then
        mapfile -t pids < <(pgrep -f -- "$BY_NAME" 2>/dev/null || true)
        ((${#pids[@]})) || die "no process matching: ${BY_NAME}"
        ((ALL)) || pids=("${pids[0]}")
    else
        (($# == 1)) || {
            usage >&2
            exit 2
        }
        [[ "$1" =~ ^[0-9]+$ ]] || die "not a PID: $1" 2
        pids=("$1")
    fi

    local pid
    for pid in "${pids[@]}"; do
        inspect "$pid"
    done
}

main "$@"
