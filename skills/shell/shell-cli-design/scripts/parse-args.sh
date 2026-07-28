#!/usr/bin/env bash
#
# parse-args.sh — sourceable long/short option parser.
#
# Handles what `getopts` cannot: long options, `--opt=value`, combined short
# flags (-vn), repeated options collected into an array, and `--`.
#
# Usage:
#   source parse-args.sh
#
#   declare -A OPT_SPEC=(
#       [input]="i:"      # trailing colon = takes a value
#       [output]="o:"
#       [tag]="t:*"       # trailing star = repeatable, collects into an array
#       [verbose]="v"     # no colon = boolean flag
#       [dry-run]="n"
#   )
#   parse_args "$@"
#
#   echo "${OPT[input]}"        # value
#   echo "${OPT[verbose]:-0}"   # 1 when present
#   printf '%s\n' "${OPT_tag[@]}"   # repeated values
#   printf '%s\n' "${ARGS[@]}"      # remaining positional arguments
#
# shellcheck shell=bash

# Populated by parse_args and read by the sourcing script.
# shellcheck disable=SC2034  # consumed by the caller, not within this library
declare -A OPT=()
# shellcheck disable=SC2034  # consumed by the caller, not within this library
declare -a ARGS=()

_pa_die() {
    printf '%s: %s\n' "${0##*/}" "$*" >&2
    exit 2
}

# Map a short letter back to its long name using OPT_SPEC.
_pa_long_for_short() {
    local want="$1" name spec
    for name in "${!OPT_SPEC[@]}"; do
        spec="${OPT_SPEC[$name]}"
        [[ "${spec:0:1}" == "$want" ]] && {
            printf '%s' "$name"
            return 0
        }
    done
    return 1
}

_pa_takes_value() { [[ "${OPT_SPEC[$1]}" == *:* ]]; }
_pa_repeatable() { [[ "${OPT_SPEC[$1]}" == *'*' ]]; }

# Record a parsed option. Repeatable options append to OPT_<name>.
_pa_set() {
    local name="$1" value="$2"

    if _pa_repeatable "$name"; then
        local arr="OPT_${name//-/_}"
        declare -g -a "$arr" 2>/dev/null || true
        declare -n _ref="$arr"
        _ref+=("$value")
        unset -n _ref
    else
        OPT["$name"]="$value"
    fi
}

parse_args() {
    OPT=()
    ARGS=()

    while (($#)); do
        case "$1" in
            --)
                shift
                ARGS+=("$@")
                return 0
                ;;

            --*=*)
                local name="${1%%=*}"
                name="${name#--}"
                [[ -v OPT_SPEC[$name] ]] || _pa_die "unknown option: --${name}"
                _pa_takes_value "$name" || _pa_die "--${name} takes no value"
                _pa_set "$name" "${1#*=}"
                shift
                ;;

            --*)
                local name="${1#--}"
                [[ -v OPT_SPEC[$name] ]] || _pa_die "unknown option: --${name}"
                if _pa_takes_value "$name"; then
                    (($# >= 2)) || _pa_die "--${name} requires a value"
                    _pa_set "$name" "$2"
                    shift 2
                else
                    _pa_set "$name" 1
                    shift
                fi
                ;;

            -[!-]*)
                # Combined short flags: -vn, or -i value, or -ivalue.
                local cluster="${1#-}" i ch name
                shift
                for ((i = 0; i < ${#cluster}; i++)); do
                    ch="${cluster:i:1}"
                    name="$(_pa_long_for_short "$ch")" \
                        || _pa_die "unknown option: -${ch}"

                    if _pa_takes_value "$name"; then
                        local rest="${cluster:i+1}"
                        if [[ -n "$rest" ]]; then
                            _pa_set "$name" "$rest" # -ivalue
                        else
                            (($#)) || _pa_die "-${ch} requires a value"
                            _pa_set "$name" "$1" # -i value
                            shift
                        fi
                        break # value consumed the rest
                    fi
                    _pa_set "$name" 1
                done
                ;;

            *)
                ARGS+=("$1")
                shift
                ;;
        esac
    done
}
