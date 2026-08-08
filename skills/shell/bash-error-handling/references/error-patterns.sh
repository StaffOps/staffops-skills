#!/usr/bin/env bash
# Bash Error Handling Patterns

# ═══ STRICT MODE (always use) ═══════════════════════════════════
set -euo pipefail
# -e: exit on error
# -u: error on unset variables
# -o pipefail: pipe fails if any command fails (not just last)

# ═══ TRAP PATTERNS ══════════════════════════════════════════════
# Cleanup on exit (any reason)
trap 'rm -rf "$tmpdir"' EXIT

# Cleanup + error reporting
trap 'echo "ERROR at line $LINENO: $BASH_COMMAND" >&2' ERR

# Full cleanup function
cleanup() {
  local exit_code=$?
  set +e  # don't exit on error during cleanup
  [[ -f "$lockfile" ]] && rm -f "$lockfile"
  [[ -d "$tmpdir" ]] && rm -rf "$tmpdir"
  [[ $exit_code -ne 0 ]] && echo "FAILED (exit $exit_code)" >&2
  exit $exit_code
}
trap cleanup EXIT INT TERM

# ═══ SAFE PATTERNS ══════════════════════════════════════════════
# Default values (avoids -u errors)
name="${1:-default}"
env="${ENVIRONMENT:-dev}"

# Check if variable is set
if [[ -z "${API_KEY:-}" ]]; then
  echo "ERROR: API_KEY not set" >&2; exit 1
fi

# Safe command execution with error message
curl -sf "http://api/health" || { echo "Health check failed" >&2; exit 1; }

# Retry with backoff
retry() {
  local max_attempts=3 delay=2 attempt=1
  while true; do
    "$@" && return 0
    [[ $attempt -ge $max_attempts ]] && return 1
    echo "Attempt $attempt failed, retrying in ${delay}s..." >&2
    sleep $delay
    ((attempt++))
    ((delay*=2))
  done
}
retry curl -sf "http://flaky-service/api"

# ═══ PIPEFAIL GOTCHAS ══════════════════════════════════════════
# This fails with pipefail if grep finds nothing:
# set -o pipefail
# cat file | grep "pattern" | wc -l   # exits 1 if no match!

# Fix: allow grep to return 1 (no match)
count=$(grep -c "pattern" file || true)
# Or:
if grep -q "pattern" file; then
  echo "found"
fi

# ═══ SUBSHELL vs CURRENT SHELL ═════════════════════════════════
# Pipe creates subshell — variable changes lost!
# WRONG:
echo "hello" | read -r var   # $var empty after this line

# CORRECT:
var=$(echo "hello")
# Or:
read -r var <<< "hello"

# ═══ COMMON TRAPS ══════════════════════════════════════════════
# set -e does NOT catch:
# - commands in if/while conditions: if cmd; then ... (expected)
# - commands with || : cmd || true (expected)
# - subshells that fail inside $(): var=$(failing_cmd) DOES exit
# - background jobs: cmd & (never caught)

# ═══ LOCKFILE (prevent concurrent runs) ════════════════════════
lockfile="/var/run/myscript.lock"
exec 200>"$lockfile"
flock -n 200 || { echo "Already running" >&2; exit 1; }

# ═══ TEMP FILES (safe creation) ════════════════════════════════
tmpdir=$(mktemp -d)
tmpfile=$(mktemp)
# Always clean up via trap EXIT (see above)
