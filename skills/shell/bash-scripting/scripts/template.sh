#!/usr/bin/env bash
#
# template.sh — production-grade Bash script skeleton.
#
# Copy this file as the starting point for any non-trivial script. It wires up
# strict mode, an error trap with a stack trace, cleanup on exit, logging that
# respects stderr, and argument parsing.
#
# Usage:
#   ./template.sh [-v] [-n] -i INPUT [-o OUTPUT]
#
set -Eeuo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

readonly SCRIPT_NAME="${0##*/}"

# Absolute path to this script's directory, so sibling files can be sourced
# regardless of the caller's working directory.
#
# Uses parameter expansion rather than `dirname` so this works before the
# dependency check runs -- and because a builtin costs no fork. When the path
# has no slash (invoked as `./script.sh` resolved via PATH), `%/*` leaves it
# unchanged and `cd` fails, so fall back to the current directory.
# Assigned separately from `readonly` so the substitution's exit status is not
# masked (SC2155).
SCRIPT_DIR="$(cd -- "${BASH_SOURCE[0]%/*}" 2>/dev/null && pwd)" || SCRIPT_DIR="$PWD"
# shellcheck disable=SC2034  # provided for scripts built from this template
readonly SCRIPT_DIR

# Populated by init_workspace, cleaned up by the EXIT trap.
WORKDIR=""

# ---------------------------------------------------------------------------
# Logging
#
# All diagnostics go to stderr so stdout stays clean for actual output --
# this is what makes a script safe to use in a pipeline.
# ---------------------------------------------------------------------------

VERBOSE=0

log() { printf '%s [%s] %s\n' "$(date +'%Y-%m-%dT%H:%M:%S%z')" "$1" "${*:2}" >&2; }
info() { log INFO "$@"; }
warn() { log WARN "$@"; }
error() { log ERROR "$@"; }
debug() { ((VERBOSE)) && log DEBUG "$@" || true; }

die() {
    error "$@"
    exit 1
}

# ---------------------------------------------------------------------------
# Traps
# ---------------------------------------------------------------------------

# Print a stack trace when any command fails. Requires `set -E` so the trap
# is inherited by functions, subshells, and command substitutions.
on_error() {
    local exit_code=$?
    local line_no=$1
    error "failed with status ${exit_code} at line ${line_no}"

    local frame=0 line func file
    while read -r line func file < <(caller "$frame"); do
        error "  at ${func}() ${file}:${line}"
        ((frame++))
    done
    exit "$exit_code"
}

# Runs on every exit path, including errors and signals.
on_exit() {
    local exit_code=$?
    if [[ -n "$WORKDIR" && -d "$WORKDIR" ]]; then
        debug "removing workdir ${WORKDIR}"
        rm -rf -- "$WORKDIR"
    fi
    exit "$exit_code"
}

trap 'on_error $LINENO' ERR
trap on_exit EXIT
trap 'die "interrupted"' INT TERM

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

usage() {
    cat <<EOF
${SCRIPT_NAME} — one-line description of what this does.

Usage:
  ${SCRIPT_NAME} [options] -i INPUT

Options:
  -i INPUT     Input file (required)
  -o OUTPUT    Output file (default: stdout)
  -n           Dry run; show what would happen without doing it
  -v           Verbose output
  -h           Show this help

Exit codes:
  0  success
  1  general error
  2  invalid usage
EOF
}

require_command() {
    local cmd
    for cmd in "$@"; do
        command -v "$cmd" >/dev/null 2>&1 \
            || die "required command not found: ${cmd}"
    done
}

init_workspace() {
    WORKDIR="$(mktemp -d)" || die "could not create a temporary directory"
    debug "workdir is ${WORKDIR}"
}

# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

process() {
    local input="$1"
    local output="$2"
    local dry_run="$3"

    [[ -r "$input" ]] || die "input is not readable: ${input}"

    if ((dry_run)); then
        info "dry run: would process ${input} -> ${output:-<stdout>}"
        return 0
    fi

    info "processing ${input}"

    # Real work goes here. Writing through a temp file inside WORKDIR means a
    # failure never leaves a half-written output in place.
    local staged="${WORKDIR}/staged.out"
    tr '[:lower:]' '[:upper:]' <"$input" >"$staged"

    if [[ -n "$output" ]]; then
        mv -- "$staged" "$output"
        info "wrote ${output}"
    else
        cat -- "$staged"
    fi
}

main() {
    local input="" output="" dry_run=0

    while getopts ':i:o:nvh' opt; do
        case "$opt" in
            i) input="$OPTARG" ;;
            o) output="$OPTARG" ;;
            n) dry_run=1 ;;
            v) VERBOSE=1 ;;
            h)
                usage
                exit 0
                ;;
            :)
                usage >&2
                die "option -${OPTARG} requires an argument"
                ;;
            \?)
                usage >&2
                die "unknown option: -${OPTARG}"
                ;;
        esac
    done
    shift $((OPTIND - 1))

    [[ -n "$input" ]] || {
        usage >&2
        exit 2
    }

    require_command tr mktemp
    init_workspace
    process "$input" "$output" "$dry_run"
}

main "$@"
