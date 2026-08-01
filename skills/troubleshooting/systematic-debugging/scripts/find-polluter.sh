#!/usr/bin/env bash
# find-polluter.sh -- bisect which test file creates an unwanted artifact
# (a stray file, a leftover process, a listening socket, a lock).
#
# Runner-agnostic: the third argument is a command template with `{}`
# standing in for the test file path, so this works with `go test`,
# `pytest`, `dotnet test --filter`, or anything that can run one test
# file/class in isolation.
#
# Usage:
#   ./find-polluter.sh <artifact_path> <test_glob> <run_template>
#
# Examples:
#   ./find-polluter.sh /tmp/leaked.sock 'internal/**/*_test.go' 'go test {}'
#   ./find-polluter.sh ./scratch/out.json 'tests/**/*_test.py' 'pytest {}'
#   ./find-polluter.sh /tmp/lockfile 'Tests/**/*Tests.cs' 'dotnet test --filter FullyQualifiedName~{}'
#
# See SKILL.md Phase 1, step 5 (trace data flow backward) -- this script is
# for the specific case where the "backward trace" is across test files
# rather than across a call stack.

set -Eeuo pipefail

if [ "$#" -ne 3 ]; then
  echo "Usage: $0 <artifact_path> <test_glob> <run_template>" >&2
  echo "Example: $0 /tmp/leaked.sock 'internal/**/*_test.go' 'go test {}'" >&2
  exit 1
fi

ARTIFACT="$1"
GLOB="$2"
TEMPLATE="$3"

echo "Searching for the test that creates: $ARTIFACT"
echo "Test glob: $GLOB"
echo "Run template: $TEMPLATE"
echo

# find -path can't match '**/' against zero directory levels, so a glob
# like tests/**/*_test.py would skip tests/top_test.py directly under the
# base dir -- also try the glob with '**/' collapsed to cover that case.
GLOB="${GLOB#./}"
mapfile -t TEST_FILES < <(
  find . \( -path "./$GLOB" -o -path "./${GLOB//\*\*\//}" \) | sort -u
)

TOTAL="${#TEST_FILES[@]}"
echo "Found $TOTAL test files"
echo

if [ "$TOTAL" -eq 0 ]; then
  echo "No test files matched the glob -- nothing to bisect." >&2
  exit 2
fi

if [ -e "$ARTIFACT" ]; then
  echo "Artifact already exists before any test ran -- clean it up first," >&2
  echo "otherwise every test will look like the polluter." >&2
  exit 2
fi

count=0
for test_file in "${TEST_FILES[@]}"; do
  count=$((count + 1))
  echo "[$count/$TOTAL] Running: $test_file"

  cmd="${TEMPLATE//\{\}/$test_file}"
  eval "$cmd" > /dev/null 2>&1 || true

  if [ -e "$ARTIFACT" ]; then
    echo
    echo "FOUND POLLUTER"
    echo "  Test:    $test_file"
    echo "  Created: $ARTIFACT"
    echo
    ls -la "$ARTIFACT"
    echo
    echo "To confirm in isolation:"
    printf '  %s\n' "${TEMPLATE//\{\}/$test_file}"
    exit 1
  fi
done

echo
echo "No polluter found -- all tests clean."
exit 0
