#!/usr/bin/env bash
# .git/hooks/pre-commit — Install: cp pre-commit .git/hooks/ && chmod +x .git/hooks/pre-commit
# Or use pre-commit framework: https://pre-commit.com
#
# This hook runs BEFORE `git commit` and blocks if any check fails.
# Exit 0 = allow commit. Exit 1 = block commit.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0

echo "🔍 Running pre-commit checks..."

# ─── 1. Block secrets ───────────────────────────────────────────────────────
# Check staged files for common secret patterns
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM)

SECRET_PATTERNS=(
  'AKIA[0-9A-Z]{16}'                    # AWS Access Key
  'password\s*=\s*["\x27][^"\x27]+'     # Inline passwords
  'BEGIN (RSA|DSA|EC|OPENSSH) PRIVATE'   # Private keys
  'ghp_[a-zA-Z0-9]{36}'                 # GitHub PAT
  'glpat-[a-zA-Z0-9\-]{20}'            # GitLab PAT
  'sk-[a-zA-Z0-9]{48}'                  # OpenAI key
)

for file in $STAGED_FILES; do
  [ -f "$file" ] || continue
  for pattern in "${SECRET_PATTERNS[@]}"; do
    if git diff --cached -- "$file" | grep -qEi "$pattern"; then
      echo -e "${RED}❌ Potential secret in: $file (pattern: $pattern)${NC}"
      ERRORS=$((ERRORS + 1))
    fi
  done
done

# ─── 2. Block large files ──────────────────────────────────────────────────
MAX_FILE_SIZE=5242880  # 5MB

for file in $STAGED_FILES; do
  [ -f "$file" ] || continue
  file_size=$(wc -c < "$file")
  if [ "$file_size" -gt "$MAX_FILE_SIZE" ]; then
    echo -e "${RED}❌ File too large ($(( file_size / 1024 / 1024 ))MB): $file${NC}"
    ERRORS=$((ERRORS + 1))
  fi
done

# ─── 3. Block .env files ───────────────────────────────────────────────────
for file in $STAGED_FILES; do
  case "$file" in
    .env|.env.*|*.env)
      if [[ "$file" != ".env.example" && "$file" != ".env.template" ]]; then
        echo -e "${RED}❌ Blocked .env file: $file (use .env.example instead)${NC}"
        ERRORS=$((ERRORS + 1))
      fi
      ;;
  esac
done

# ─── 4. Lint staged files (optional — uncomment what applies) ──────────────

# Python
# if echo "$STAGED_FILES" | grep -q '\.py$'; then
#   echo "  Running ruff..."
#   docker run --rm -v "$(pwd):/src" -w /src ghcr.io/astral-sh/ruff:latest check \
#     $(echo "$STAGED_FILES" | grep '\.py$') || ERRORS=$((ERRORS + 1))
# fi

# YAML (Helm values, configs)
# if echo "$STAGED_FILES" | grep -q '\.ya\?ml$'; then
#   echo "  Validating YAML..."
#   for f in $(echo "$STAGED_FILES" | grep '\.ya\?ml$'); do
#     python3 -c "import yaml; yaml.safe_load(open('$f'))" 2>/dev/null || {
#       echo -e "${RED}❌ Invalid YAML: $f${NC}"
#       ERRORS=$((ERRORS + 1))
#     }
#   done
# fi

# ─── 5. Conventional commit message format (commit-msg hook alternative) ───
# Note: This check is better in .git/hooks/commit-msg, but shown here for reference.
# Move to commit-msg hook if using this.

# ─── Result ────────────────────────────────────────────────────────────────
if [ "$ERRORS" -gt 0 ]; then
  echo ""
  echo -e "${RED}✗ Pre-commit failed with $ERRORS error(s). Fix and retry.${NC}"
  echo -e "${YELLOW}  To bypass (emergencies only): git commit --no-verify${NC}"
  exit 1
fi

echo -e "${GREEN}✓ All pre-commit checks passed.${NC}"
exit 0
