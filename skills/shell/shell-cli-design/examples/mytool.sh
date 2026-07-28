#!/usr/bin/env bash
#
# mytool.sh — reference CLI implementing every convention from the skill.
#
# Demonstrates:
#   - subcommands, each parsing its own options
#   - data on stdout, diagnostics on stderr
#   - TTY detection for color, plus NO_COLOR
#   - stdin support via `-`
#   - documented exit codes (0 / 1 / 2 / 3 partial)
#   - --dry-run and a --force that skips only the prompt
#   - config precedence: flags > env > config file > defaults
#
# Usage:
#   ./mytool.sh count -i data.txt
#   cat data.txt | ./mytool.sh count -
#   ./mytool.sh list --format json
#   ./mytool.sh delete --dry-run item1 item2
#
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"
readonly VERSION="1.0.0"

# --- configuration precedence: defaults < config file < env < flags ---------
FORMAT="text"
VERBOSE=0
DRY_RUN=0
FORCE=0
COLOR="auto"

CONFIG_FILE="${MYTOOL_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/mytool.conf}"
# shellcheck source=/dev/null
[[ -r "$CONFIG_FILE" ]] && source "$CONFIG_FILE"
FORMAT="${MYTOOL_FORMAT:-$FORMAT}"

# Color variables must exist before any log call, because usage_error() can
# fire while parsing the very option that configures color.
RED="" YELLOW="" DIM="" RESET=""

# --- streams ---------------------------------------------------------------
# Data goes to stdout via emit(); everything else to stderr.
emit() { printf '%s\n' "$*"; }
log() { printf '%s%s%s\n' "${DIM}" "$*" "${RESET}" >&2; }
warn() { printf '%swarning:%s %s\n' "${YELLOW}" "${RESET}" "$*" >&2; }
error() { printf '%serror:%s %s\n' "${RED}" "${RESET}" "$*" >&2; }
debug() { ((VERBOSE)) && log "$@" || true; }
die() {
    error "$*"
    exit "${2:-1}"
}
usage_error() {
    error "$*"
    printf '\n' >&2
    usage >&2
    exit 2
}

# --- color: only when stdout is a terminal and NO_COLOR is unset -----------
setup_color() {
    local enable=0
    case "$COLOR" in
        always) enable=1 ;;
        never) enable=0 ;;
        auto) [[ -t 2 ]] && [[ -z "${NO_COLOR:-}" ]] && enable=1 ;;
        *) usage_error "--color must be auto, always or never" ;;
    esac

    if ((enable)); then
        RED=$'\033[31m'
        YELLOW=$'\033[33m'
        DIM=$'\033[2m'
        RESET=$'\033[0m'
    else
        RED="" YELLOW="" DIM="" RESET=""
    fi
}

usage() {
    cat <<EOF
${SCRIPT_NAME} — reference CLI demonstrating shell tool conventions

Usage:
  ${SCRIPT_NAME} <command> [options] [arguments]

Commands:
  count       Count lines in the input
  list        List items
  delete      Delete items (destructive; supports --dry-run)
  help        Show this help

Global options:
  -v, --verbose        Diagnostics on stderr
  -f, --format FMT     Output format: text|json (default: ${FORMAT})
      --color WHEN     auto|always|never (default: auto)
  -h, --help           This help
      --version        Print the version

Environment:
  MYTOOL_CONFIG        Config file (default: ~/.config/mytool.conf)
  MYTOOL_FORMAT        Default output format
  NO_COLOR             Any value disables color

Exit codes:
  0  success
  1  failure
  2  usage error
  3  partial success (some items failed)

Examples:
  ${SCRIPT_NAME} count -i access.log
  cat access.log | ${SCRIPT_NAME} count -
  ${SCRIPT_NAME} list --format json | jq '.items[]'
  ${SCRIPT_NAME} delete --dry-run old-1 old-2
EOF
}

# Resolve an input argument to a readable path, supporting `-` for stdin.
resolve_input() {
    local input="$1"
    if [[ -z "$input" || "$input" == "-" ]]; then
        [[ -t 0 ]] && usage_error "no input given and stdin is a terminal"
        printf '/dev/stdin'
        return 0
    fi
    [[ -r "$input" ]] || die "cannot read input: ${input}"
    printf '%s' "$input"
}

# Only prompts when there is a terminal; --force skips the prompt, never the
# validation.
confirm() {
    ((FORCE)) && return 0
    if [[ ! -t 0 ]]; then
        die "refusing to prompt without a terminal; pass --force" 2
    fi
    local reply
    read -r -p "$1 [y/N] " reply
    [[ "$reply" == [yY]* ]]
}

# --- subcommands -----------------------------------------------------------

cmd_count() {
    local input=""
    while (($#)); do
        case "$1" in
            -i | --input)
                input="${2:?--input requires a value}"
                shift 2
                ;;
            --input=*)
                input="${1#*=}"
                shift
                ;;
            --)
                shift
                break
                ;;
            -)
                input="-"
                shift
                ;;
            -*) usage_error "unknown option for count: $1" ;;
            *)
                input="$1"
                shift
                ;;
        esac
    done

    local path count
    path="$(resolve_input "$input")"
    debug "counting lines in ${path}"
    count="$(wc -l <"$path" | tr -d ' ')"

    case "$FORMAT" in
        json) emit "{\"lines\": ${count}}" ;;
        text) emit "$count" ;;
        *) usage_error "unknown format: ${FORMAT}" ;;
    esac
}

cmd_list() {
    local -a items=("alpha" "beta" "gamma")

    case "$FORMAT" in
        json)
            local joined="" item
            for item in "${items[@]}"; do
                joined+="${joined:+,}\"${item}\""
            done
            emit "{\"items\": [${joined}]}"
            ;;
        text) printf '%s\n' "${items[@]}" ;;
        *) usage_error "unknown format: ${FORMAT}" ;;
    esac
}

cmd_delete() {
    local -a targets=()
    while (($#)); do
        case "$1" in
            -n | --dry-run)
                DRY_RUN=1
                shift
                ;;
            --force)
                FORCE=1
                shift
                ;;
            --)
                shift
                targets+=("$@")
                break
                ;;
            -*) usage_error "unknown option for delete: $1" ;;
            *)
                targets+=("$1")
                shift
                ;;
        esac
    done

    ((${#targets[@]})) || usage_error "delete requires at least one target"

    if ((DRY_RUN)); then
        local t
        for t in "${targets[@]}"; do
            emit "would delete: ${t}"
        done
        return 0
    fi

    confirm "Delete ${#targets[@]} item(s)?" || die "aborted by user"

    local failed=0 total=0 t
    for t in "${targets[@]}"; do
        total=$((total + 1))
        # Simulated work: names starting with "bad" fail.
        if [[ "$t" == bad* ]]; then
            warn "could not delete: ${t}"
            failed=$((failed + 1))
            continue
        fi
        emit "deleted: ${t}"
    done

    ((failed == 0)) && return 0
    ((failed == total)) && return 1
    warn "${failed}/${total} deletions failed"
    return 3 # documented partial-success code
}

main() {
    local -a rest=()

    # Global options may appear before or after the subcommand.
    while (($#)); do
        case "$1" in
            -v | --verbose)
                VERBOSE=1
                shift
                ;;
            -f | --format)
                FORMAT="${2:?--format requires a value}"
                shift 2
                ;;
            --format=*)
                FORMAT="${1#*=}"
                shift
                ;;
            --color)
                COLOR="${2:?--color requires a value}"
                shift 2
                ;;
            --color=*)
                COLOR="${1#*=}"
                shift
                ;;
            --no-color)
                COLOR="never"
                shift
                ;;
            -h | --help)
                setup_color
                usage
                exit 0
                ;;
            --version)
                printf '%s %s\n' "$SCRIPT_NAME" "$VERSION"
                exit 0
                ;;
            --)
                # Keep the marker: the subcommand needs it to treat the
                # remaining words as operands rather than options.
                rest+=("$@")
                break
                ;;
            *)
                rest+=("$1")
                shift
                ;;
        esac
    done

    setup_color

    ((${#rest[@]})) || {
        usage >&2
        exit 2
    }

    local cmd="${rest[0]}"
    rest=("${rest[@]:1}")

    case "$cmd" in
        count) cmd_count "${rest[@]+"${rest[@]}"}" ;;
        list) cmd_list "${rest[@]+"${rest[@]}"}" ;;
        delete) cmd_delete "${rest[@]+"${rest[@]}"}" ;;
        help) usage ;;
        *) usage_error "unknown command: ${cmd}" ;;
    esac
}

main "$@"
