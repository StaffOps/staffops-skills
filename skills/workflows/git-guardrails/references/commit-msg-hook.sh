#!/usr/bin/env bash
# .git/hooks/commit-msg — Enforce Conventional Commits format.
# Install: cp commit-msg-hook.sh .git/hooks/commit-msg && chmod +x .git/hooks/commit-msg

COMMIT_MSG_FILE="$1"
COMMIT_MSG=$(cat "$COMMIT_MSG_FILE")

# Conventional Commits regex:
# type(optional-scope): description
# Optional ! for breaking changes
PATTERN='^(feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert)(\(.+\))?(!)?: .{1,72}$'

# Check first line only
FIRST_LINE=$(head -1 "$COMMIT_MSG_FILE")

if ! echo "$FIRST_LINE" | grep -qE "$PATTERN"; then
  echo "❌ Commit message does not follow Conventional Commits format."
  echo ""
  echo "Expected: <type>(<scope>): <description>"
  echo ""
  echo "Types: feat fix docs style refactor perf test chore ci build revert"
  echo ""
  echo "Examples:"
  echo "  feat(auth): add SSO login flow"
  echo "  fix(api): handle null response from payment gateway"
  echo "  docs(readme): update getting started section"
  echo "  chore(deps): bump opentelemetry to 1.42.1"
  echo ""
  echo "Your message: $FIRST_LINE"
  exit 1
fi

# Check subject line length (max 72 chars)
if [ ${#FIRST_LINE} -gt 72 ]; then
  echo "❌ Subject line too long (${#FIRST_LINE} > 72 chars)."
  echo "   Shorten: $FIRST_LINE"
  exit 1
fi

exit 0
