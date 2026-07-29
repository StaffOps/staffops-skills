#!/usr/bin/env bash
#
# bulk-rename.sh — rename files in bulk, safely.
#
# Worked example of the rules from the skill: NUL-delimited traversal, globs
# instead of `ls`, dry-run by default, collision detection, and refusing to
# clobber. Filenames with spaces, newlines, quotes and leading dashes all work.
#
# Usage:
#   ./bulk-rename.sh -m 's/ /_/g' .                 # dry run (default)
#   ./bulk-rename.sh -m 's/ /_/g' --apply .
#   ./bulk-rename.sh -p 'IMG_' -e '.jpeg:.jpg' --apply ./photos
#   ./bulk-rename.sh -l --apply .                   # lowercase every name
#
# Operations are applied in this order: sed expression, extension swap,
# prefix, lowercase.
#
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"

APPLY=0
RECURSIVE=0
LOWERCASE=0
SED_EXPR=""
PREFIX=""
EXT_SWAP=""

die() {
    printf '%s: %s\n' "$SCRIPT_NAME" "$*" >&2
    exit 1
}
usage_error() {
    printf '%s: %s\n\n' "$SCRIPT_NAME" "$*" >&2
    usage >&2
    exit 2
}
info() { printf '%s\n' "$*" >&2; }

usage() {
    cat <<EOF
${SCRIPT_NAME} — bulk rename files safely.

Usage:
  ${SCRIPT_NAME} [options] DIRECTORY

Options:
  -m EXPR        sed expression applied to the basename (e.g. 's/ /_/g')
  -p PREFIX      Prepend a prefix
  -e OLD:NEW     Replace the extension (e.g. '.jpeg:.jpg')
  -l             Lowercase the whole name
  -r             Recurse into subdirectories
      --apply    Actually rename (default is a dry run)
  -h             Help

Exit codes:
  0  success (or dry run completed)
  1  one or more renames failed or would collide
  2  usage error
EOF
}

# Build the new basename from the old one by applying each enabled operation.
new_name_for() {
    # Two separate `local` statements: within a single `local`, later
    # assignments cannot see earlier ones on the same line (shellcheck SC2318).
    local old="$1"
    local new="$old"

    if [[ -n "$SED_EXPR" ]]; then
        new="$(printf '%s' "$new" | sed -E "$SED_EXPR")" \
            || die "sed expression failed: ${SED_EXPR}"
    fi

    if [[ -n "$EXT_SWAP" ]]; then
        local from="${EXT_SWAP%%:*}" to="${EXT_SWAP#*:}"
        [[ "$new" == *"$from" ]] && new="${new%"$from"}${to}"
    fi

    [[ -n "$PREFIX" ]] && new="${PREFIX}${new}"
    ((LOWERCASE)) && new="${new,,}"

    printf '%s' "$new"
}

main() {
    local -a args=()
    while (($#)); do
        case "$1" in
            -m)
                SED_EXPR="${2:?-m requires an expression}"
                shift 2
                ;;
            -p)
                PREFIX="${2:?-p requires a prefix}"
                shift 2
                ;;
            -e)
                EXT_SWAP="${2:?-e requires OLD:NEW}"
                shift 2
                ;;
            -l)
                LOWERCASE=1
                shift
                ;;
            -r)
                RECURSIVE=1
                shift
                ;;
            --apply)
                APPLY=1
                shift
                ;;
            -h | --help)
                usage
                exit 0
                ;;
            --)
                shift
                args+=("$@")
                break
                ;;
            -*) usage_error "unknown option: $1" ;;
            *)
                args+=("$1")
                shift
                ;;
        esac
    done

    ((${#args[@]} == 1)) || usage_error "exactly one directory is required"
    local dir="${args[0]}"
    [[ -d "$dir" ]] || die "not a directory: ${dir}"

    [[ -n "$SED_EXPR$PREFIX$EXT_SWAP" ]] || ((LOWERCASE)) \
        || usage_error "no operation given (-m, -p, -e or -l)"

    [[ -n "$EXT_SWAP" && "$EXT_SWAP" != *:* ]] \
        && usage_error "-e must be OLD:NEW, got: ${EXT_SWAP}"

    # NUL-delimited traversal: the only way to survive arbitrary filenames.
    local -a find_args=("$dir")
    ((RECURSIVE)) || find_args+=(-maxdepth 1)
    find_args+=(-type f -print0)

    local -a planned_old=() planned_new=()
    declare -A target_count=()

    local path base new
    while IFS= read -r -d '' path; do
        base="${path##*/}"
        new="$(new_name_for "$base")"

        [[ "$new" == "$base" ]] && continue
        [[ -n "$new" ]] || {
            info "skip (empty result): ${path}"
            continue
        }
        [[ "$new" == */* ]] && {
            info "skip (result contains a slash): ${path}"
            continue
        }

        planned_old+=("$path")
        planned_new+=("${path%/*}/${new}")
        target_count["${path%/*}/${new}"]=$((${target_count["${path%/*}/${new}"]:-0} + 1))
    done < <(find "${find_args[@]}")

    ((${#planned_old[@]})) || {
        info "nothing to rename"
        return 0
    }

    # Refuse to run if two sources would land on the same target, or if the
    # target already exists and is not one of the sources.
    local rc=0 i src dst
    for i in "${!planned_old[@]}"; do
        src="${planned_old[i]}"
        dst="${planned_new[i]}"

        if ((target_count["$dst"] > 1)); then
            info "COLLISION: multiple files would become ${dst}"
            rc=1
            continue
        fi
        if [[ -e "$dst" ]]; then
            info "EXISTS: ${dst} is already present"
            rc=1
            continue
        fi

        if ((APPLY)); then
            if mv -n -- "$src" "$dst"; then
                printf '%s -> %s\n' "$src" "$dst"
            else
                info "FAILED: ${src}"
                rc=1
            fi
        else
            printf 'would rename: %s -> %s\n' "$src" "$dst"
        fi
    done

    ((APPLY)) || info "dry run; pass --apply to perform ${#planned_old[@]} rename(s)"
    return "$rc"
}

main "$@"
