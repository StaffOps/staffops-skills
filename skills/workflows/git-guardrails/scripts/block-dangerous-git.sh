#!/usr/bin/env bash
#
# block-dangerous-git.sh - Claude Code PreToolUse hook for the Bash tool.
#
# Reads the hook JSON payload on stdin ({"tool_input":{"command":"..."}}),
# splits the command into individual chained statements, and blocks (exit 2)
# any statement that matches a destructive git (or repo-destroying rm)
# pattern. Anything else exits 0 and the Bash tool call proceeds normally.
#
# Each statement is tokenized with a small quote-aware word-splitter (see
# `tokenize` below) before any rule runs against it, so wrapping a flag in
# quotes (`git push "--force" origin main`) does not change how it matches.
# One level of `bash -c "..."` / `sh -c "..."` / `eval "..."` indirection is
# unwrapped and the inner string is re-scanned against the same rules. Any
# `$(...)` or backtick command substitution is treated as suspicious on its
# own and blocked for human review, because this hook does not execute
# anything to see what a substitution would actually produce. See
# "Known limitations" in SKILL.md for the reasoning behind that tradeoff and
# for what is deliberately NOT handled (nested indirection beyond one level,
# process substitution, variable-held commands, etc).
#
# This script intentionally avoids bash 4+ features (mapfile, associative
# arrays, ${var,,}) so it runs unmodified on macOS's stock bash 3.2 as well
# as Linux/WSL bash 4/5.
#
# Config (optional): <repo>/.claude/git-guardrails.json
#   {
#     "disable_rules": ["tag-delete-local"],
#     "allow_patterns": ["^git clean -fdx build/dist/?$"]
#   }
# See ../references/example-config.json and the SKILL.md for the schema.
#
# Escape hatch: set GIT_GUARDRAILS_DISABLE=1 in the environment Claude Code
# was launched from to bypass every rule for the session. This is meant for
# a human directly supervising a recovery operation, not for an agent to set
# on its own behalf.

set -u

RAW_INPUT=$(cat)

# ---------------------------------------------------------------------------
# 1. Pull tool_input.command out of the hook payload.
# ---------------------------------------------------------------------------
if command -v jq >/dev/null 2>&1; then
  COMMAND=$(printf '%s' "$RAW_INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
else
  # jq missing: fall back to a plain-text extraction. This assumes the
  # command value has no embedded, unescaped double quotes - true for the
  # large majority of Bash tool calls. If the fallback can't confidently
  # extract a command, we fail OPEN (exit 0) rather than block unrelated
  # Bash calls just because jq isn't installed - this hook is one layer of
  # defense, not the only one (see the git-conventions steering rules that
  # apply at the model level regardless of this hook).
  COMMAND=$(printf '%s' "$RAW_INPUT" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\(.*\)".*/\1/p' | head -n 1)
fi

RAW_COMMAND="$COMMAND"

[ -z "$COMMAND" ] && exit 0

# Cheap early exit: only commands that mention "git" or "rm" can possibly
# match any rule below. Skips the rest of the script for the common case
# (curl, npm test, kubectl get, ...).
case "$COMMAND" in
  *git*|*rm*) ;;
  *) exit 0 ;;
esac

# Full bypass, explicit and visible (not silent) - see header comment.
if [ "${GIT_GUARDRAILS_DISABLE:-0}" = "1" ]; then
  echo "git-guardrails: GIT_GUARDRAILS_DISABLE=1 set, skipping all checks for: $COMMAND" >&2
  exit 0
fi

# ---------------------------------------------------------------------------
# 2. Load per-repo overrides.
# ---------------------------------------------------------------------------
CONFIG_FILE="${CLAUDE_PROJECT_DIR:-.}/.claude/git-guardrails.json"

DISABLED_RULES=()
ALLOW_PATTERNS=()

# extract_json_string_array FILE KEY
# Minimal fallback for when jq is unavailable: pulls the flat JSON array of
# strings for the given top-level key, e.g. "disable_rules": ["a", "b"].
# This is NOT a JSON parser - it does not handle escaped quotes, nested
# arrays/objects, or a key name that also appears inside a string value
# elsewhere in the file. It exists to keep the documented example schema
# working when jq is missing, not to replace jq. See "Known limitations".
extract_json_string_array() {
  local file="$1" key="$2" flat section
  flat=$(tr '\n' ' ' < "$file" 2>/dev/null)
  section=$(printf '%s' "$flat" | sed -nE "s/.*\"$key\"[[:space:]]*:[[:space:]]*\[([^]]*)\].*/\1/p")
  [ -z "$section" ] && return 0
  printf '%s' "$section" | grep -oE '"[^"]*"' | sed -E 's/^"//; s/"$//'
}

if [ -f "$CONFIG_FILE" ]; then
  if command -v jq >/dev/null 2>&1; then
    while IFS= read -r line; do
      [ -n "$line" ] && DISABLED_RULES+=("$line")
    done < <(jq -r '.disable_rules[]? // empty' "$CONFIG_FILE" 2>/dev/null)

    while IFS= read -r line; do
      [ -n "$line" ] && ALLOW_PATTERNS+=("$line")
    done < <(jq -r '.allow_patterns[]? // empty' "$CONFIG_FILE" 2>/dev/null)
  else
    echo "git-guardrails: jq not found, using a minimal fallback parser for $CONFIG_FILE (flat string-array schema only - see SKILL.md 'Known limitations'). Install jq for reliable config overrides." >&2

    while IFS= read -r line; do
      [ -n "$line" ] && DISABLED_RULES+=("$line")
    done < <(extract_json_string_array "$CONFIG_FILE" "disable_rules")

    while IFS= read -r line; do
      [ -n "$line" ] && ALLOW_PATTERNS+=("$line")
    done < <(extract_json_string_array "$CONFIG_FILE" "allow_patterns")
  fi
fi

is_disabled() {
  # $1 = rule id
  local id="$1" d
  for d in "${DISABLED_RULES[@]:-}"; do
    [ "$d" = "$id" ] && return 0
  done
  return 1
}

# allow_patterns match against the FULL raw command (pre-split, pre-quote-
# stripping), so a narrowly scoped, human-reviewed exception can cover an
# entire chained command in one entry.
for pat in "${ALLOW_PATTERNS[@]:-}"; do
  [ -z "$pat" ] && continue
  if printf '%s' "$RAW_COMMAND" | grep -qE "$pat"; then
    exit 0
  fi
done

# ---------------------------------------------------------------------------
# 3. Tokenizer and helpers
# ---------------------------------------------------------------------------

# TOKENS holds the result of the last `tokenize` call: one array element per
# shell word of the statement being evaluated, with surrounding single or
# double quotes removed. This is a deliberately narrow subset of real shell
# word-splitting - it does not process backslash escapes, ANSI-C $'...'
# quoting, or variable/command expansion - but it is enough to make
# `git push "--force" origin main` tokenize identically to
# `git push --force origin main`, which a plain whitespace split cannot do.
# Content that was inside quotes (including any spaces in it) stays part of
# the SAME token, exactly like real shell word-splitting, so a quoted
# `bash -c "git push --force origin main"` argument comes out as one token
# rather than being re-split on its internal spaces.
TOKENS=()

tokenize() {
  local s="$1" i=0 len c cur in_squote=0 in_dquote=0
  TOKENS=()
  cur=""
  len=${#s}
  while [ "$i" -lt "$len" ]; do
    c="${s:$i:1}"
    if [ "$in_squote" -eq 1 ]; then
      if [ "$c" = "'" ]; then
        in_squote=0
      else
        cur="$cur$c"
      fi
    elif [ "$in_dquote" -eq 1 ]; then
      if [ "$c" = '"' ]; then
        in_dquote=0
      else
        cur="$cur$c"
      fi
    else
      case "$c" in
        "'") in_squote=1 ;;
        '"') in_dquote=1 ;;
        " "|$'\t')
          if [ -n "$cur" ]; then
            TOKENS+=("$cur")
            cur=""
          fi
          ;;
        *) cur="$cur$c" ;;
      esac
    fi
    i=$((i + 1))
  done
  [ -n "$cur" ] && TOKENS+=("$cur")
  return 0
}

# token_is TOKEN - exact match against any element currently in TOKENS.
token_is() {
  local want="$1" t
  for t in "${TOKENS[@]:-}"; do
    [ "$t" = "$want" ] && return 0
  done
  return 1
}

CONFIG_HINT="$CONFIG_FILE"
CURRENT_STATEMENT=""

block() {
  local rule_id="$1" reason="$2"
  {
    echo "BLOCKED by git-guardrails: rule '$rule_id'"
    echo "Command:  $RAW_COMMAND"
    if [ -n "$CURRENT_STATEMENT" ] && [ "$CURRENT_STATEMENT" != "$RAW_COMMAND" ]; then
      echo "Matched:  $CURRENT_STATEMENT"
    fi
    echo "Why:      $reason"
    echo ""
    echo "This is a request for human review, not a permanent ban:"
    echo "  - Run the command yourself in your own shell, or"
    echo "  - Add \"$rule_id\" to disable_rules in $CONFIG_HINT, or"
    echo "  - Add a narrowly-scoped regex for this exact case to allow_patterns in $CONFIG_HINT, or"
    echo "  - Set GIT_GUARDRAILS_DISABLE=1 for this session to bypass every rule"
    echo "    (only while a human is directly supervising a recovery operation)."
    echo "See skills/workflows/git-guardrails for the full rule list and config schema."
  } >&2
  exit 2
}

# ---------------------------------------------------------------------------
# 4. -C / --git-dir / --work-tree resolution, for rules that need a live
#    `git` check to run against the repo the intercepted command actually
#    targets, not wherever this hook process happens to have its cwd.
# ---------------------------------------------------------------------------

TARGET_REPO_DIR="."
TARGET_REPO_MODE="-C"
TARGET_REPO_ERR=""

# resolve_target_repo_dir - reads TOKENS, sets TARGET_REPO_DIR/TARGET_REPO_MODE.
# Returns 1 (with TARGET_REPO_ERR set) when -C/--git-dir/--work-tree was
# present but did not resolve to an existing directory - callers must fail
# closed in that case rather than silently falling back to the hook's own
# cwd, which would run the live check against the wrong repository.
resolve_target_repo_dir() {
  local i n=${#TOKENS[@]} tok val="" found=0 mode="-C"
  TARGET_REPO_DIR="."
  TARGET_REPO_MODE="-C"
  TARGET_REPO_ERR=""
  i=0
  while [ "$i" -lt "$n" ]; do
    tok="${TOKENS[$i]}"
    case "$tok" in
      -C)
        if [ "$((i + 1))" -lt "$n" ]; then
          val="${TOKENS[$((i + 1))]}"
          found=1
          mode="-C"
        else
          TARGET_REPO_ERR="-C given with no path argument"
          return 1
        fi
        ;;
      -C?*)
        val="${tok#-C}"
        found=1
        mode="-C"
        ;;
      --git-dir=*)
        val="${tok#--git-dir=}"
        found=1
        mode="--git-dir"
        ;;
      --work-tree=*)
        val="${tok#--work-tree=}"
        found=1
        mode="-C"
        ;;
    esac
    i=$((i + 1))
  done

  [ "$found" -eq 0 ] && return 0

  if [ -z "$val" ]; then
    TARGET_REPO_ERR="empty path after -C/--git-dir/--work-tree"
    return 1
  fi
  if [ ! -d "$val" ]; then
    TARGET_REPO_ERR="path '$val' does not exist or is not a directory"
    return 1
  fi

  TARGET_REPO_DIR="$val"
  TARGET_REPO_MODE="$mode"
  return 0
}

git_in_target() {
  if [ "$TARGET_REPO_MODE" = "--git-dir" ]; then
    git --git-dir="$TARGET_REPO_DIR" "$@"
  else
    git -C "$TARGET_REPO_DIR" "$@"
  fi
}

# ---------------------------------------------------------------------------
# 5. Rules. Each reads the global TOKENS (already tokenized for the current
#    statement) and returns 0 (block) or 1 (allow). Statements are split on
#    chain/pipe operators below so a dangerous command later in a chain
#    (e.g. `git rebase main && git push --force`) is caught even though the
#    first statement is harmless.
# ---------------------------------------------------------------------------

# force-push: overwrites the remote branch, discarding commits a teammate
# (or a parallel agent, or your past self from another machine) pushed after
# your last fetch. --force-with-lease / --force-if-includes refuse to push
# when the remote has moved since you last saw it, so they are exempt. The
# `+refspec` shorthand (`git push origin +main`, `+feature:main`) is
# equivalent to --force for that ref and is checked the same way.
rule_force_push() {
  local tok
  token_is "git" || return 1
  token_is "push" || return 1
  token_is "--force" && return 0
  token_is "-f" && return 0
  for tok in "${TOKENS[@]:-}"; do
    case "$tok" in
      +?*) return 0 ;;
    esac
  done
  return 1
}

# reset-hard: discards uncommitted changes AND unpushed commits with no
# reflog entry for the working-tree edits. If anything else in the tree had
# uncommitted work, it is simply gone.
rule_reset_hard() {
  token_is "git" || return 1
  token_is "reset" || return 1
  token_is "--hard" && return 0
  return 1
}

# branch-force-delete: -D removes a branch even with unmerged commits -
# those commits become unreachable and, once gc runs, unrecoverable. -d
# (lowercase) refuses to delete a branch with unmerged work, which is what
# you almost always want.
rule_branch_force_delete() {
  token_is "git" || return 1
  token_is "branch" || return 1
  token_is "-D" && return 0
  if token_is "--delete" && token_is "--force"; then
    return 0
  fi
  return 1
}

# clean-force: permanently deletes untracked files and directories - build
# artifacts AND any uncommitted new file. clean does not use the reflog, so
# there is no undo.
rule_clean_force() {
  local tok
  token_is "git" || return 1
  token_is "clean" || return 1
  token_is "--force" && return 0
  for tok in "${TOKENS[@]:-}"; do
    case "$tok" in
      --*) : ;;
      -*)
        case "$tok" in *f*|*F*) return 0 ;; esac
        ;;
    esac
  done
  return 1
}

# checkout-discard: `git checkout -- <path>` (or bare `git checkout .`)
# silently overwrites the working-tree copy of a file with its last
# committed version. Unstaged edits are gone with no reflog entry - reflog
# tracks commits, not working-tree content.
rule_checkout_discard() {
  token_is "git" || return 1
  token_is "checkout" || return 1
  token_is "--" && return 0
  token_is "." && return 0
  return 1
}

# restore-discard: `git restore <path>` does the same thing as checkout --
# for the working tree. `git restore --staged` only unstages (touches the
# index, not the working tree) and is safe, so it is exempt unless
# --worktree is also present.
rule_restore_discard() {
  token_is "git" || return 1
  token_is "restore" || return 1
  if token_is "--staged" && ! token_is "--worktree"; then
    return 1
  fi
  return 0
}

# skip-hooks: --no-verify skips pre-commit/pre-push hooks (lint, secret
# scanning, tests). --no-gpg-sign / commit.gpgsign=false bypasses commit
# signing. Both are covered by this org's git-conventions steering rule:
# hooks and signing are never skipped without an explicit human request.
rule_skip_hooks() {
  local tok
  token_is "git" || return 1
  token_is "--no-verify" && return 0
  token_is "--no-gpg-sign" && return 0
  for tok in "${TOKENS[@]:-}"; do
    case "$tok" in *gpgsign=false*) return 0 ;; esac
  done
  return 1
}

# rewrite-pushed-history: `git commit --amend` or `git rebase` rewrite
# commits. Rewriting is safe when the commits only exist locally, and
# dangerous the moment a clone (a teammate's, CI's, or your own from
# another machine) already has them. This rule does a live check instead of
# guessing from the command text: if the current branch's HEAD is exactly
# equal to its upstream tracking ref, every commit here is already
# mirrored on the remote, and amending or rebasing now rewrites shared
# history. When there is no upstream (a local-only branch), the check
# can't fire - there is nothing "already pushed" to protect.
#
# If the command targets another repo via `-C <path>`, `--git-dir=<path>`,
# or `--work-tree=<path>`, the live check runs against THAT repo (see
# resolve_target_repo_dir / git_in_target), not the hook's own cwd. If the
# target path can't be resolved to an existing directory, or the live check
# fails for a reason other than "no upstream configured", this fails
# CLOSED (blocks) rather than silently allowing a rewrite it never actually
# verified.
rule_rewrite_pushed_history() {
  local rewrites=0 upstream_head local_head rc err

  token_is "git" || return 1
  token_is "--amend" && rewrites=1

  if token_is "rebase"; then
    if token_is "--abort" || token_is "--continue" || token_is "--skip" || token_is "--quit"; then
      : # these only manage an in-progress rebase, they don't start a new rewrite
    else
      rewrites=1
    fi
  fi

  [ "$rewrites" -eq 1 ] || return 1

  if ! resolve_target_repo_dir; then
    block "rewrite-pushed-history" "Could not resolve a usable repository from -C/--git-dir/--work-tree in this command ($TARGET_REPO_ERR). Refusing to guess whether this rewrite is safe against the wrong (or a nonexistent) repository - run it yourself after confirming HEAD is not already on the remote."
  fi

  upstream_head=$(git_in_target rev-parse '@{u}' 2>/dev/null)
  rc=$?
  if [ "$rc" -ne 0 ]; then
    err=$(git_in_target rev-parse '@{u}' 2>&1 >/dev/null)
    case "$err" in
      *[Nn]o\ upstream*|*[Uu]nknown\ revision*|*[Nn]o\ such\ branch*)
        return 1 # legitimately no upstream configured - nothing pushed yet, safe
        ;;
      *)
        block "rewrite-pushed-history" "Could not determine the upstream of the target repository ($TARGET_REPO_DIR): $err. Failing closed rather than assuming this rewrite is safe."
        ;;
    esac
  fi

  local_head=$(git_in_target rev-parse HEAD 2>/dev/null)
  rc=$?
  if [ "$rc" -ne 0 ] || [ -z "$local_head" ]; then
    block "rewrite-pushed-history" "Could not resolve HEAD in the target repository ($TARGET_REPO_DIR). Failing closed rather than assuming this rewrite is safe."
  fi

  [ -n "$upstream_head" ] && [ "$upstream_head" = "$local_head" ] && return 0
  return 1
}

# tag-delete-local: deleting a local tag is harmless if the tag was never
# pushed, but this hook has no reliable offline way to tell (checking the
# remote would mean a network call inside a hook that fires on every Bash
# command - too slow, and it can hang). Flagged for human confirmation
# either way; see rule_remote_ref_delete for the part that is unambiguously
# destructive (removing a tag other people already have).
rule_tag_delete_local() {
  token_is "git" || return 1
  token_is "tag" || return 1
  token_is "-d" && return 0
  token_is "--delete" && return 0
  return 1
}

# remote-ref-delete: `git push --delete` (or the `:refs/tags/...` /
# `:branch` colon shorthand) removes a ref on the remote outright. For a
# released tag this breaks anyone who already pulled it and any release
# automation pinned to it; for a branch it can orphan commits others have
# based work on. The command text alone can't reliably distinguish "tag"
# from "branch" here, so both are flagged.
rule_remote_ref_delete() {
  local tok
  token_is "git" || return 1
  token_is "push" || return 1
  token_is "--delete" && return 0
  for tok in "${TOKENS[@]:-}"; do
    case "$tok" in
      :refs/tags/*|:refs/heads/*) return 0 ;;
    esac
  done
  return 1
}

# rm-rf-git: rm targeting .git, the repo root, or the whole current
# directory with BOTH a recursive flag (-r/-R/--recursive) and a force flag
# (-f/-F/--force) present destroys the object database and all local
# history. The two flags do not need to be combined in one token or one
# case - `rm -r -f .git`, `rm -Rf .git`, and `rm -rf .git` are all the same
# effective command. Unlike git reset --hard, there is no reflog to fall
# back on - the reflog IS one of the things being deleted.
rule_rm_rf_git() {
  local tok has_recursive=0 has_force=0

  token_is "rm" || return 1

  for tok in "${TOKENS[@]:-}"; do
    case "$tok" in
      --recursive) has_recursive=1 ;;
      --force) has_force=1 ;;
      --*) : ;; # other long flags don't affect recursive/force detection
      -*)
        case "$tok" in *r*|*R*) has_recursive=1 ;; esac
        case "$tok" in *f*|*F*) has_force=1 ;; esac
        ;;
    esac
  done

  [ "$has_recursive" -eq 1 ] && [ "$has_force" -eq 1 ] || return 1

  for tok in "${TOKENS[@]:-}"; do
    case "$tok" in
      .git|.git/|.git/*|*/.git|*/.git/*|.|./|/) return 0 ;;
    esac
  done
  return 1
}

# ---------------------------------------------------------------------------
# 6. bash -c / sh -c / eval unwrapping.
# ---------------------------------------------------------------------------

# extract_wrapped_command - reads TOKENS (already populated by tokenize for
# the current statement). If a `bash`/`sh` token is directly followed by a
# `-c` token, or an `eval` token appears, prints the joined remaining
# tokens (the literal inner command string, quotes already stripped by
# tokenize) and returns 0. Returns 1 if no such wrapper is present.
extract_wrapped_command() {
  local i n=${#TOKENS[@]} tok j joined
  i=0
  while [ "$i" -lt "$n" ]; do
    tok="${TOKENS[$i]}"
    case "$tok" in
      bash|sh)
        if [ "$((i + 1))" -lt "$n" ] && [ "${TOKENS[$((i + 1))]}" = "-c" ]; then
          joined=""
          j=$((i + 2))
          while [ "$j" -lt "$n" ]; do
            joined="$joined${TOKENS[$j]} "
            j=$((j + 1))
          done
          printf '%s' "$joined"
          return 0
        fi
        ;;
      eval)
        joined=""
        j=$((i + 1))
        while [ "$j" -lt "$n" ]; do
          joined="$joined${TOKENS[$j]} "
          j=$((j + 1))
        done
        printf '%s' "$joined"
        return 0
        ;;
    esac
    i=$((i + 1))
  done
  return 1
}

# ---------------------------------------------------------------------------
# 7. Evaluate one statement: command-substitution check, tokenize, run every
#    rule, then (one level only) unwrap bash -c / sh -c / eval and recurse.
# ---------------------------------------------------------------------------

evaluate_statement() {
  local raw="$1" depth="${2:-0}" inner inner_statements istmt

  raw="$(printf '%s' "$raw" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
  [ -z "$raw" ] && return 0

  CURRENT_STATEMENT="$raw"

  # $(...) / `...` command substitution: this hook does not execute
  # anything to see what a substitution would produce, and a false "safe"
  # read here (allowing `git $(echo push --force) origin main` through
  # unevaluated) is worse than an occasional false positive on a command
  # that happens to use `$(date)` in a commit message. See SKILL.md "Known
  # limitations" for the tradeoff this makes explicit.
  case "$raw" in
    *'$('*|*'`'*)
      if ! is_disabled "command-substitution"; then
        block "command-substitution" "This statement contains \$(...) or backtick command substitution. git-guardrails does not statically evaluate what a substitution will produce, so it cannot confirm the result is safe - flagging for human review instead of silently allowing a possibly-wrapped destructive command through unevaluated."
      fi
      ;;
  esac

  tokenize "$raw"

  ! is_disabled "force-push"              && rule_force_push              && block "force-push" "git push --force/-f (or a +refspec) overwrites the remote branch, discarding commits a teammate pushed after your last fetch. Use --force-with-lease or --force-if-includes instead."
  ! is_disabled "reset-hard"               && rule_reset_hard              && block "reset-hard" "git reset --hard discards uncommitted changes and unpushed commits with no reflog entry for the working-tree edits."
  ! is_disabled "branch-force-delete"      && rule_branch_force_delete     && block "branch-force-delete" "git branch -D deletes a branch even with unmerged commits; they become unreachable and eventually unrecoverable. Use -d unless you are certain."
  ! is_disabled "clean-force"              && rule_clean_force             && block "clean-force" "git clean -f/-fd permanently deletes untracked files and directories with no reflog to recover them."
  ! is_disabled "checkout-discard"         && rule_checkout_discard        && block "checkout-discard" "git checkout -- <path> (or checkout .) silently overwrites unstaged edits with the last committed version."
  ! is_disabled "restore-discard"          && rule_restore_discard         && block "restore-discard" "git restore (without --staged only) overwrites unstaged working-tree edits with the last committed version."
  ! is_disabled "skip-hooks"               && rule_skip_hooks              && block "skip-hooks" "--no-verify / --no-gpg-sign bypasses pre-commit/pre-push hooks or commit signing. Per git-conventions steering, hooks are never skipped without an explicit human request."
  ! is_disabled "rewrite-pushed-history"   && rule_rewrite_pushed_history  && block "rewrite-pushed-history" "HEAD is identical to its upstream tracking ref - every commit here is already on the remote. Amending or rebasing now rewrites history a clone may already have fetched."
  ! is_disabled "tag-delete-local"         && rule_tag_delete_local        && block "tag-delete-local" "Deleting a local tag is safe only if it was never pushed; this hook cannot verify that offline."
  ! is_disabled "remote-ref-delete"        && rule_remote_ref_delete       && block "remote-ref-delete" "git push --delete removes a ref (tag or branch) on the remote outright - anyone who already fetched it, or automation pinned to it, breaks."
  ! is_disabled "rm-rf-git"                && rule_rm_rf_git               && block "rm-rf-git" "rm with both a recursive flag and a force flag, targeting .git or the repo root, destroys the object database and all local history. There is no reflog fallback - the reflog is part of what gets deleted."

  # One level of bash -c / sh -c / eval indirection: extract the literal
  # inner command string and re-run this exact same evaluation against it.
  # Deliberately not recursive beyond one level - see "Known limitations".
  if [ "$depth" -eq 0 ]; then
    inner="$(extract_wrapped_command)"
    if [ -n "$inner" ]; then
      inner_statements=$(printf '%s\n' "$inner" | sed -E 's/(&&|\|\||[;|])/\n/g')
      while IFS= read -r istmt; do
        evaluate_statement "$istmt" 1
      done <<INNEREOF
$inner_statements
INNEREOF
    fi
  fi

  return 0
}

# ---------------------------------------------------------------------------
# 8. Split on chain/pipe operators and evaluate each statement independently.
# ---------------------------------------------------------------------------

STATEMENTS=$(printf '%s\n' "$COMMAND" | sed -E 's/(&&|\|\||[;|])/\n/g')

while IFS= read -r stmt; do
  evaluate_statement "$stmt" 0
done <<EOF
$STATEMENTS
EOF

exit 0
