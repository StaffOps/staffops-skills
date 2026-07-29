#!/usr/bin/env bash
#
# explain-pipeline.sh — run a shell pipeline stage by stage and report what
# each stage did: line count, byte count, exit status, and elapsed time.
#
# Useful when a long pipeline produces nothing and you need to find which
# stage dropped the data.
#
# Usage:
#   ./explain-pipeline.sh 'cat access.log | grep 500 | awk "{print \$1}" | sort -u'
#   ./explain-pipeline.sh -i input.txt 'grep error | cut -d" " -f1 | sort'
#   ./explain-pipeline.sh -s 'cmd1 | cmd2'      # also show a sample of output
#
# Notes:
#   Stages are split on top-level '|' only -- pipes inside quotes are kept.
#   Each stage is re-run against the previous stage's captured output, so this
#   is only meaningful for deterministic, side-effect-free pipelines.
#
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"

INPUT=""
SHOW_SAMPLE=0
SAMPLE_LINES=3
WORKDIR=""

cleanup() {
    local rc=$?
    [[ -n "$WORKDIR" ]] && rm -rf -- "$WORKDIR"
    exit "$rc"
}
trap cleanup EXIT

die() {
    printf '%s: %s\n' "$SCRIPT_NAME" "$*" >&2
    exit 1
}

usage() {
    cat <<EOF
${SCRIPT_NAME} — show what each stage of a pipeline produces.

Usage:
  ${SCRIPT_NAME} [-i INPUT] [-s] [-n N] 'stage1 | stage2 | ...'

Options:
  -i INPUT   Feed this file into the first stage (default: stdin or nothing)
  -s         Show a sample of each stage's output
  -n N       Sample size in lines (default: ${SAMPLE_LINES})
  -h         Help

Exit codes:
  0  every stage exited 0
  1  at least one stage exited non-zero
  2  usage error
EOF
}

# Split a pipeline on '|' that are not inside single or double quotes.
split_stages() {
    local line="$1"
    local -a out=()
    local cur="" ch quote=""
    local i

    for ((i = 0; i < ${#line}; i++)); do
        ch="${line:i:1}"

        if [[ -n "$quote" ]]; then
            [[ "$ch" == "$quote" ]] && quote=""
            cur+="$ch"
            continue
        fi

        case "$ch" in
            "'" | '"')
                quote="$ch"
                cur+="$ch"
                ;;
            '|')
                out+=("$cur")
                cur=""
                ;;
            *) cur+="$ch" ;;
        esac
    done
    out+=("$cur")

    printf '%s\0' "${out[@]}"
}

trim() {
    local s="$1"
    s="${s#"${s%%[![:space:]]*}"}"
    s="${s%"${s##*[![:space:]]}"}"
    printf '%s' "$s"
}

main() {
    local opt
    while getopts ':i:sn:h' opt; do
        case "$opt" in
            i) INPUT="$OPTARG" ;;
            s) SHOW_SAMPLE=1 ;;
            n) SAMPLE_LINES="$OPTARG" ;;
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
    [[ "$SAMPLE_LINES" =~ ^[0-9]+$ ]] || die "-n must be a number"

    local pipeline="$1"
    WORKDIR="$(mktemp -d)"

    local -a stages=()
    mapfile -t -d '' stages < <(split_stages "$pipeline")

    # Seed the first stage's input.
    local current="${WORKDIR}/stage0.out"
    if [[ -n "$INPUT" ]]; then
        [[ -r "$INPUT" ]] || die "cannot read: ${INPUT}"
        cp -- "$INPUT" "$current"
    elif [[ ! -t 0 ]]; then
        cat >"$current"
    else
        : >"$current"
    fi

    printf '%-3s %-40s %10s %10s %7s %8s\n' \
        '#' 'STAGE' 'LINES' 'BYTES' 'EXIT' 'TIME' >&2
    printf '%s\n' \
        '----------------------------------------------------------------------------------' >&2

    local in_lines in_bytes
    in_lines="$(wc -l <"$current" | tr -d ' ')"
    in_bytes="$(wc -c <"$current" | tr -d ' ')"
    printf '%-3s %-40s %10s %10s %7s %8s\n' \
        '0' '(input)' "$in_lines" "$in_bytes" '-' '-' >&2

    local i stage label out err rc start elapsed overall=0
    for i in "${!stages[@]}"; do
        stage="$(trim "${stages[i]}")"
        [[ -n "$stage" ]] || continue

        out="${WORKDIR}/stage$((i + 1)).out"
        err="${WORKDIR}/stage$((i + 1)).err"

        start="$(date +%s%N 2>/dev/null || printf '0')"
        set +e
        eval "$stage" <"$current" >"$out" 2>"$err"
        rc=$?
        set -e

        if [[ "$start" != "0" ]]; then
            elapsed="$((($(date +%s%N) - start) / 1000000))ms"
        else
            elapsed='-'
        fi

        ((rc != 0)) && overall=1

        label="$stage"
        ((${#label} > 40)) && label="${label:0:37}..."

        printf '%-3s %-40s %10s %10s %7s %8s\n' \
            "$((i + 1))" "$label" \
            "$(wc -l <"$out" | tr -d ' ')" \
            "$(wc -c <"$out" | tr -d ' ')" \
            "$rc" "$elapsed" >&2

        if [[ -s "$err" ]]; then
            printf '    stderr: %s\n' "$(head -1 "$err")" >&2
        fi

        if ((SHOW_SAMPLE)) && [[ -s "$out" ]]; then
            sed "s/^/    | /" <(head -n "$SAMPLE_LINES" "$out") >&2
        fi

        current="$out"
    done

    printf '\n' >&2
    cat "$current"
    return "$overall"
}

main "$@"
