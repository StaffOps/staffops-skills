#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# install.sh — Port this skills catalog into Claude Code or Kiro CLI
# ============================================================================
#
# Claude Code discovers skills as direct children of one flat directory
# (~/.claude/skills/<name>/SKILL.md) — this script symlinks each skill
# individually into that directory, since the catalog itself is organized
# one level deeper (skills/<category>/<name>/SKILL.md).
#
# Kiro CLI needs no install step at all: it reads SKILL.md files straight
# off disk via a `skill://` glob resource declared inside whichever Kiro
# agent JSON you already run — no copying, no symlinking, no flat-namespace
# constraint (Kiro's glob supports the category/name nesting natively). This
# script's `kiro-resource-line` command only prints the exact line to add;
# it never writes to a Kiro agent file it doesn't own.
#
# The Claude-side symlink approach and its safety invariants (collision
# pre-flight, "foreign entry" preservation, ownership-scoped uninstall/
# clean) are ported from a sibling internal project's proven
# `setup-agents.sh`, adapted here for a skills-only, overlay-less catalog.

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE_SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info() { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; }

usage() {
    cat <<EOF
Usage: $(basename "$0") <command> [--dry-run]

Commands:
  install             Symlink every skill into \$CLAUDE_SKILLS_DIR (Claude Code)
  uninstall           Remove only this repo's symlinks from \$CLAUDE_SKILLS_DIR
  status              Report linked / broken / foreign-owned skill entries
  clean               Remove only this repo's BROKEN symlinks (leaves healthy ones)
  kiro-resource-line  Print the skill:// glob line to add to a Kiro agent's
                      "resources" array — prints only, never writes a file
  help                Show this message

Environment:
  CLAUDE_SKILLS_DIR   Claude Code skills directory (default: ~/.claude/skills)

Every command that touches the filesystem runs
"python3 tools/validate_skills.py" first and aborts if it reports any error —
never symlink a broken catalog into a live agent's skill directory.
EOF
}

# A symlink is "ours" iff its recorded target path resolves inside this repo
# — checked by prefix match on the readlink target, not by name, so a
# same-named skill some other tool installed is never mistaken for ours.
# readlink works on a broken symlink itself; the target need not exist.
_is_within_repo() {
    local path="$1"
    [[ "$path" == "$REPO_DIR" || "$path" == "$REPO_DIR"/* ]]
}

_validate_catalog() {
    info "Validating catalog (tools/validate_skills.py)..."
    if ! python3 "$REPO_DIR/tools/validate_skills.py"; then
        err "Catalog validation failed — aborting before touching $CLAUDE_SKILLS_DIR"
        exit 1
    fi
}

# Populates the caller's skill_names/skill_dirs arrays (declared by the
# caller with -a) and aborts on any cross-category name collision — Claude's
# flat namespace means two skills sharing a name would silently clobber one
# symlink with the other, whichever alphabetically sorts last.
_collect_skills() {
    local -n _names_ref=$1
    local -n _dirs_ref=$2
    local skill_md skill_dir skill_name

    while IFS= read -r skill_md; do
        skill_dir=$(dirname "$skill_md")
        skill_name=$(basename "$skill_dir")
        _names_ref+=("$skill_name")
        _dirs_ref+=("$skill_dir")
    done < <(find "$REPO_DIR/skills" -name SKILL.md 2>/dev/null | sort)

    local i j collisions=0
    for ((i = 0; i < ${#_names_ref[@]}; i++)); do
        for ((j = i + 1; j < ${#_names_ref[@]}; j++)); do
            if [[ "${_names_ref[$i]}" == "${_names_ref[$j]}" ]]; then
                err "Skill name collision: '${_names_ref[$i]}' at both ${_dirs_ref[$i]} and ${_dirs_ref[$j]}"
                collisions=$((collisions + 1))
            fi
        done
    done
    if [[ $collisions -gt 0 ]]; then
        err "$collisions skill name collision(s) found — aborting before creating any symlink"
        exit 1
    fi
}

cmd_install() {
    local dry_run="${1:-false}"
    _validate_catalog

    local -a skill_names=() skill_dirs=()
    _collect_skills skill_names skill_dirs

    if [[ "$dry_run" != "true" ]]; then
        mkdir -p "$CLAUDE_SKILLS_DIR"
    fi

    local linked=0 skipped=0 i skill_name skill_dir link_path existing_target
    for ((i = 0; i < ${#skill_names[@]}; i++)); do
        skill_name="${skill_names[$i]}"
        skill_dir="${skill_dirs[$i]}"
        link_path="$CLAUDE_SKILLS_DIR/$skill_name"

        if [[ -e "$link_path" || -L "$link_path" ]]; then
            existing_target=""
            [[ -L "$link_path" ]] && existing_target=$(readlink "$link_path")
            if [[ ! -L "$link_path" ]] || ! _is_within_repo "$existing_target"; then
                warn "skill '$skill_name' already exists at $link_path (not ours), skipping"
                skipped=$((skipped + 1))
                continue
            fi
        fi

        if [[ "$dry_run" == "true" ]]; then
            echo -e "  ${YELLOW}would link${NC} $skill_name -> $skill_dir"
        else
            ln -sfn "$skill_dir" "$link_path"
        fi
        linked=$((linked + 1))
    done

    if [[ "$dry_run" == "true" ]]; then
        ok "Dry run: would link $linked skill(s) into $CLAUDE_SKILLS_DIR ($skipped foreign entries would be preserved)"
    else
        ok "Linked $linked skill(s) -> $CLAUDE_SKILLS_DIR ($skipped foreign entries preserved)"
    fi
}

cmd_uninstall() {
    local dry_run="${1:-false}"
    local removed=0 sf target

    if [[ ! -d "$CLAUDE_SKILLS_DIR" ]]; then
        warn "Not found: $CLAUDE_SKILLS_DIR (nothing to uninstall)"
        return 0
    fi

    for sf in "$CLAUDE_SKILLS_DIR"/*; do
        [[ -L "$sf" ]] || continue
        target=$(readlink "$sf")
        _is_within_repo "$target" || continue
        if [[ "$dry_run" == "true" ]]; then
            echo -e "  ${YELLOW}would remove${NC} $(basename "$sf") -> $target"
        else
            rm -f "$sf" && ok "Removed: $(basename "$sf")"
        fi
        removed=$((removed + 1))
    done

    if [[ "$dry_run" == "true" ]]; then
        ok "Dry run: would remove $removed repo-owned symlink(s) from $CLAUDE_SKILLS_DIR"
    else
        ok "Removed $removed repo-owned symlink(s) from $CLAUDE_SKILLS_DIR"
    fi
}

cmd_status() {
    if [[ ! -d "$CLAUDE_SKILLS_DIR" ]]; then
        warn "Not found: $CLAUDE_SKILLS_DIR"
        return 0
    fi

    local sf target linked=0 broken=0 foreign=0
    for sf in "$CLAUDE_SKILLS_DIR"/*; do
        [[ -e "$sf" || -L "$sf" ]] || continue
        if [[ -L "$sf" ]]; then
            target=$(readlink "$sf")
            if _is_within_repo "$target"; then
                if [[ -e "$sf" ]]; then
                    linked=$((linked + 1))
                else
                    err "BROKEN: $(basename "$sf") -> $target"
                    broken=$((broken + 1))
                fi
                continue
            fi
        fi
        foreign=$((foreign + 1))
    done

    ok "$CLAUDE_SKILLS_DIR: $linked repo-owned symlink(s) resolving, $broken broken, $foreign foreign entries untouched"
}

cmd_clean() {
    local dry_run="${1:-false}"
    local sf target removed=0

    if [[ ! -d "$CLAUDE_SKILLS_DIR" ]]; then
        warn "Not found: $CLAUDE_SKILLS_DIR"
        return 0
    fi

    for sf in "$CLAUDE_SKILLS_DIR"/*; do
        [[ -L "$sf" ]] || continue
        [[ -e "$sf" ]] && continue # only broken links are in scope
        target=$(readlink "$sf")
        _is_within_repo "$target" || continue
        if [[ "$dry_run" == "true" ]]; then
            echo -e "  ${YELLOW}would remove orphan${NC} $(basename "$sf") -> $target"
        else
            rm -f "$sf" && ok "Removed orphan: $(basename "$sf")"
        fi
        removed=$((removed + 1))
    done

    ok "$([[ "$dry_run" == "true" ]] && echo "Dry run: would remove" || echo "Removed") $removed broken repo-owned symlink(s)"
}

cmd_kiro_resource_line() {
    cat <<EOF
Kiro CLI reads SKILL.md files directly off disk via a skill:// glob resource
declared inside an agent's JSON "resources" array -- no install step, no
symlinking, no flat-namespace constraint (the glob below matches the
category/name nesting this catalog already uses). Add this line to the
"resources" array of whichever Kiro agent you want these skills available
in:

  "skill://${REPO_DIR}/skills/**/SKILL.md"

This script does not write to any Kiro agent file -- it has no agent of its
own to own, and patching a file it doesn't own is out of scope here. Add the
line by hand, or by whatever mechanism generates your own agent JSON.
EOF
}

main() {
    local cmd="${1:-help}"
    local dry_run="false"
    [[ "${2:-}" == "--dry-run" ]] && dry_run="true"

    case "$cmd" in
        install) cmd_install "$dry_run" ;;
        uninstall) cmd_uninstall "$dry_run" ;;
        status) cmd_status ;;
        clean) cmd_clean "$dry_run" ;;
        kiro-resource-line) cmd_kiro_resource_line ;;
        help|-h|--help) usage ;;
        *)
            err "Unknown command: $cmd"
            usage
            exit 1
            ;;
    esac
}

main "$@"
