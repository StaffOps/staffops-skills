#!/usr/bin/env bash
#
# atomic-deploy.sh — worked example of failure-safe deployment in shell.
#
# Demonstrates, end to end:
#   - single-instance locking (flock)
#   - staging into a temp directory, then an atomic rename
#   - a cleanup stack that runs in reverse order on every exit path
#   - rollback to the previous release when a health check fails
#   - retry with backoff around the network call
#   - correct exit-status propagation through traps
#
# Layout it manages:
#   <root>/releases/<timestamp>/    unpacked releases
#   <root>/current                  symlink -> the active release
#
# Usage:
#   ./atomic-deploy.sh -u URL -r /srv/app [-k 3] [-v]
#   ./atomic-deploy.sh -u file:///tmp/build.tar.gz -r /tmp/demo -v
#
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"

VERBOSE=0
ROOT=""
URL=""
KEEP=3
HEALTH_CMD=""

STAGING=""
PREVIOUS=""
NEW_RELEASE=""
declare -a CLEANUP=()

# ---------------------------------------------------------------------------
# Diagnostics and cleanup
# ---------------------------------------------------------------------------

log() { printf '%s %-5s %s\n' "$(date +'%H:%M:%S')" "$1" "${*:2}" >&2; }
info() { log INFO "$@"; }
warn() { log WARN "$@"; }
error() { log ERROR "$@"; }
debug() { ((VERBOSE)) && log DEBUG "$@" || true; }
die() {
    error "$@"
    exit 1
}

add_cleanup() { CLEANUP+=("$1"); }

run_cleanup() {
    local rc=$? i
    for ((i = ${#CLEANUP[@]} - 1; i >= 0; i--)); do
        debug "cleanup: ${CLEANUP[i]}"
        eval "${CLEANUP[i]}" || warn "cleanup failed: ${CLEANUP[i]}"
    done
    exit "$rc"
}
trap run_cleanup EXIT
trap 'error "interrupted"; exit 130' INT TERM

usage() {
    cat <<EOF
${SCRIPT_NAME} — deploy an artifact atomically, with rollback.

Usage:
  ${SCRIPT_NAME} -u URL -r ROOT [-k KEEP] [-c HEALTH_CMD] [-v]

Options:
  -u URL          Artifact URL (tar.gz). file:// is accepted.
  -r ROOT         Deployment root directory
  -k KEEP         Releases to retain (default: 3)
  -c HEALTH_CMD   Health check; non-zero triggers rollback
  -v              Verbose
  -h              Help
EOF
}

# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

acquire_lock() {
    local lockfile="${ROOT}/.deploy.lock"
    mkdir -p -- "$ROOT"

    if ! command -v flock >/dev/null 2>&1; then
        warn "flock unavailable; concurrent deploys are not prevented"
        return 0
    fi

    exec 9>"$lockfile"
    flock -n 9 || die "another deploy is in progress"
    debug "lock acquired: ${lockfile}"
}

fetch_artifact() {
    local dest="$1"
    local attempt=1 delay=1 max=4

    until _fetch_once "$dest"; do
        if ((attempt >= max)); then
            die "download failed after ${max} attempts: ${URL}"
        fi
        warn "download attempt ${attempt}/${max} failed, retrying in ${delay}s"
        sleep "$delay"
        delay=$((delay * 2))
        ((attempt++))
    done
    info "downloaded artifact ($(wc -c <"$dest" | tr -d ' ') bytes)"
}

_fetch_once() {
    local dest="$1"
    case "$URL" in
        file://*) cp -- "${URL#file://}" "$dest" 2>/dev/null ;;
        *) curl -fsSL --max-time 120 -o "$dest" -- "$URL" ;;
    esac
}

stage_release() {
    local tarball="$1"

    # The PID suffix matters: `date` only has second resolution, so two
    # deploys within the same second would otherwise collide -- the second
    # would overwrite the release the first is still serving, and a rollback
    # would then point at a directory that gets pruned.
    NEW_RELEASE="${ROOT}/releases/$(date +%Y%m%d%H%M%S)-$$"
    [[ -e "$NEW_RELEASE" ]] && die "release directory already exists: ${NEW_RELEASE}"
    STAGING="${NEW_RELEASE}.staging"

    mkdir -p -- "$STAGING"
    # If anything fails before the rename, remove the partial directory.
    # `rm -rf` on a missing path exits 0, so this action is idempotent and
    # stays silent on the success path where the directory was renamed away.
    add_cleanup "rm -rf -- '${STAGING}'"

    tar -xzf "$tarball" -C "$STAGING" \
        || die "artifact is not a valid tar.gz"

    [[ -n "$(ls -A "$STAGING")" ]] || die "artifact is empty"

    # Atomic within the same filesystem: either the release exists complete,
    # or it does not exist at all. No reader ever sees a partial tree.
    mv -- "$STAGING" "$NEW_RELEASE"
    STAGING=""
    info "staged release: ${NEW_RELEASE##*/}"
}

# Point a symlink at a new target, replacing any existing one.
#
# Portability note: GNU `mv -T` performs rename(2) on the symlink itself,
# which is genuinely atomic -- readers see either the old or the new target,
# never a missing link. BSD/macOS `mv` has no -T and, when the destination is
# a symlink to a directory, moves the source *into* that directory instead of
# replacing the link. So the fallback unlinks first, trading atomicity for
# correctness. Prefer GNU coreutils on deployment hosts.
atomic_symlink() {
    local target="$1" link="$2"
    local tmp="${link}.tmp.$$"

    ln -s -- "$target" "$tmp"

    if mv -T -- "$tmp" "$link" 2>/dev/null; then
        return 0
    fi

    if [[ -L "$link" ]]; then
        rm -f -- "$link"
    elif [[ -e "$link" ]]; then
        rm -f -- "$tmp"
        die "refusing to replace non-symlink path: ${link}"
    fi

    mv -- "$tmp" "$link"
}

activate_release() {
    local link="${ROOT}/current"

    if [[ -L "$link" ]]; then
        PREVIOUS="$(readlink -- "$link")"
        debug "previous release: ${PREVIOUS##*/}"
    fi

    atomic_symlink "$NEW_RELEASE" "$link"
    info "activated ${NEW_RELEASE##*/}"
}

health_check() {
    [[ -n "$HEALTH_CMD" ]] || {
        debug "no health check configured"
        return 0
    }

    info "running health check"
    local attempt=1 max=3
    until (cd "${ROOT}/current" && eval "$HEALTH_CMD"); do
        if ((attempt >= max)); then
            return 1
        fi
        warn "health check ${attempt}/${max} failed, retrying"
        sleep 2
        ((attempt++))
    done
    info "health check passed"
}

rollback() {
    [[ -n "$PREVIOUS" ]] || die "health check failed and there is no previous release"

    warn "rolling back to ${PREVIOUS##*/}"
    atomic_symlink "$PREVIOUS" "${ROOT}/current"

    # Defensive: never delete the directory we just rolled back onto.
    if [[ "$NEW_RELEASE" != "$PREVIOUS" ]]; then
        rm -rf -- "$NEW_RELEASE"
    fi
    die "deploy failed; rolled back to ${PREVIOUS##*/}"
}

prune_releases() {
    local dir="${ROOT}/releases" keep="$KEEP"
    [[ -d "$dir" ]] || return 0

    local -a old=()
    # Newest first, skip the ones being kept, never touch the active one.
    while IFS= read -r release; do
        [[ "$release" == "$(readlink -- "${ROOT}/current" 2>/dev/null)" ]] && continue
        old+=("$release")
    done < <(find "$dir" -mindepth 1 -maxdepth 1 -type d | sort -r | tail -n +"$((keep + 1))")

    ((${#old[@]})) || return 0
    info "pruning ${#old[@]} old release(s)"
    rm -rf -- "${old[@]}"
}

main() {
    local opt
    while getopts ':u:r:k:c:vh' opt; do
        case "$opt" in
            u) URL="$OPTARG" ;;
            r) ROOT="$OPTARG" ;;
            k) KEEP="$OPTARG" ;;
            c) HEALTH_CMD="$OPTARG" ;;
            v) VERBOSE=1 ;;
            h)
                usage
                exit 0
                ;;
            :) die "option -${OPTARG} requires an argument" ;;
            \?) die "unknown option: -${OPTARG}" ;;
        esac
    done

    [[ -n "$URL" && -n "$ROOT" ]] || {
        usage >&2
        exit 2
    }
    [[ "$KEEP" =~ ^[0-9]+$ ]] || die "-k must be a number"

    acquire_lock

    local workdir
    workdir="$(mktemp -d)"
    add_cleanup "rm -rf -- '${workdir}'"

    mkdir -p -- "${ROOT}/releases"

    fetch_artifact "${workdir}/artifact.tar.gz"
    stage_release "${workdir}/artifact.tar.gz"
    activate_release

    if ! health_check; then
        rollback
    fi

    prune_releases
    info "deploy complete: ${NEW_RELEASE##*/}"
}

main "$@"
