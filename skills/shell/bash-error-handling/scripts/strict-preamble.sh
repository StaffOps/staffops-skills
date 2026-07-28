#!/usr/bin/env bash
#
# strict-preamble.sh — sourceable strict-mode, logging, and cleanup boilerplate.
#
# Source this near the top of a script:
#
#   source "$(dirname "${BASH_SOURCE[0]}")/strict-preamble.sh"
#
# Provides:
#   log/info/warn/error/debug/die   diagnostics on stderr
#   add_cleanup CMD                 register a cleanup action (LIFO)
#   make_workdir                    temp dir, auto-removed at exit
#   require_command CMD...          abort unless every command exists
#   acquire_lock [PATH]             single-instance guard via flock
#
# Notes:
#   - This file deliberately does NOT `set -e` at the top level when sourced
#     into an interactive shell, because that would kill the user's session.
#   - Sets shell options only when sourced from a script.
#
# shellcheck shell=bash

# Refuse to run directly -- this file is a library.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    printf 'strict-preamble.sh is meant to be sourced, not executed\n' >&2
    exit 2
fi

# Only tighten options for non-interactive shells.
if [[ ! $- =~ i ]]; then
    set -Eeuo pipefail
    shopt -s inherit_errexit 2>/dev/null || true
fi

: "${VERBOSE:=0}"
: "${LOG_TIMESTAMPS:=1}"

_SCRIPT_NAME="${0##*/}"

# ---------------------------------------------------------------------------
# Logging -- everything to stderr so stdout stays usable in a pipeline.
# ---------------------------------------------------------------------------

log() {
    local level="$1"
    shift
    if ((LOG_TIMESTAMPS)); then
        printf '%s %-5s [%s] %s\n' \
            "$(date +'%Y-%m-%dT%H:%M:%S%z')" "$level" "$_SCRIPT_NAME" "$*" >&2
    else
        printf '%-5s [%s] %s\n' "$level" "$_SCRIPT_NAME" "$*" >&2
    fi
}

info() { log INFO "$@"; }
warn() { log WARN "$@"; }
error() { log ERROR "$@"; }
debug() { ((VERBOSE)) && log DEBUG "$@" || true; }

die() {
    error "$@"
    exit 1
}

# ---------------------------------------------------------------------------
# Cleanup stack -- actions run in reverse registration order at exit.
# ---------------------------------------------------------------------------

declare -a _CLEANUP_ACTIONS=()

add_cleanup() {
    _CLEANUP_ACTIONS+=("$1")
}

_run_cleanup() {
    local rc=$? i
    for ((i = ${#_CLEANUP_ACTIONS[@]} - 1; i >= 0; i--)); do
        debug "cleanup: ${_CLEANUP_ACTIONS[i]}"
        # Never let a cleanup failure mask the original status.
        eval "${_CLEANUP_ACTIONS[i]}" || warn "cleanup step failed: ${_CLEANUP_ACTIONS[i]}"
    done
    exit "$rc"
}

_on_error() {
    local rc=$? line="$1"
    error "failed with status ${rc} at line ${line}"
    local frame=0 l f s
    while read -r l f s < <(caller "$frame"); do
        error "  at ${f}() ${s}:${l}"
        ((frame++))
    done
}

trap '_on_error $LINENO' ERR
trap _run_cleanup EXIT
trap 'error "interrupted"; exit 130' INT
trap 'error "terminated"; exit 143' TERM

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

require_command() {
    local cmd missing=()
    for cmd in "$@"; do
        command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
    done
    ((${#missing[@]} == 0)) || die "missing required command(s): ${missing[*]}"
}

# Creates WORKDIR and registers its removal.
make_workdir() {
    WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/${_SCRIPT_NAME%.sh}.XXXXXX")" \
        || die "could not create a temporary directory"
    add_cleanup "rm -rf -- '${WORKDIR}'"
    debug "workdir: ${WORKDIR}"
}

# Single-instance guard. The lock is released when the process exits.
acquire_lock() {
    local lockfile="${1:-${TMPDIR:-/tmp}/${_SCRIPT_NAME%.sh}.lock}"

    command -v flock >/dev/null 2>&1 || {
        warn "flock not available, skipping lock"
        return 0
    }

    exec 9>"$lockfile" || die "cannot open lock file: ${lockfile}"
    flock -n 9 || die "another instance is already running (${lockfile})"
    debug "acquired lock: ${lockfile}"
}
