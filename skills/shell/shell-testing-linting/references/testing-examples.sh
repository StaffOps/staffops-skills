#!/usr/bin/env bash
# Shell Testing & Linting — shellcheck + bats examples

# ═══ SHELLCHECK ═══════════════════════════════════════════════
# Install: apt install shellcheck / brew install shellcheck
# Run:
shellcheck script.sh                     # lint single file
shellcheck -x script.sh                  # follow source'd files
shellcheck -s bash script.sh            # explicit shell dialect
shellcheck -f diff script.sh            # output as patch
shellcheck -e SC2086 script.sh          # exclude specific rule
find . -name "*.sh" -exec shellcheck {} + # lint all scripts

# Common issues:
# SC2086: Double quote to prevent globbing/splitting: "$var"
# SC2046: Quote command substitution: "$(cmd)"
# SC2155: Declare and assign separately: local var; var=$(cmd)
# SC2034: Variable appears unused (might be exported/sourced)
# SC2068: Double quote array expansion: "${array[@]}"

# ═══ BATS (Bash Automated Testing System) ═════════════════════
# Install: git clone https://github.com/bats-core/bats-core.git
#          ./bats-core/install.sh /usr/local

# --- Example test file: tests/deploy.bats ---
# #!/usr/bin/env bats
#
# setup() {
#   # Runs before each test
#   export PATH="$BATS_TEST_DIRNAME/../bin:$PATH"
#   TMPDIR="$(mktemp -d)"
# }
#
# teardown() {
#   # Runs after each test
#   rm -rf "$TMPDIR"
# }
#
# @test "deploy requires --env flag" {
#   run deploy.sh
#   [ "$status" -eq 1 ]
#   [[ "$output" =~ "Missing required --env" ]]
# }
#
# @test "deploy accepts valid environment" {
#   run deploy.sh --env dev --dry-run myservice
#   [ "$status" -eq 0 ]
#   [[ "$output" =~ "DRY-RUN" ]]
# }
#
# @test "deploy rejects invalid environment" {
#   run deploy.sh --env invalid myservice
#   [ "$status" -eq 1 ]
#   [[ "$output" =~ "Invalid env" ]]
# }
#
# @test "version flag works" {
#   run deploy.sh --version
#   [ "$status" -eq 0 ]
#   [[ "$output" =~ ^[0-9]+\.[0-9]+\.[0-9]+ ]]
# }

# Run bats:
# bats tests/                            # run all tests in dir
# bats tests/deploy.bats                # run specific file
# bats --tap tests/                      # TAP output (CI friendly)

# ═══ SHUNIT2 (alternative — xUnit style) ═══════════════════════
# testMyFunction() {
#   result=$(my_function "input")
#   assertEquals "expected" "$result"
# }
# . shunit2

# ═══ CI INTEGRATION ═══════════════════════════════════════════
# .gitlab-ci.yml:
# lint-shell:
#   image: koalaman/shellcheck-alpine:latest
#   script:
#     - find . -name "*.sh" -exec shellcheck -x {} +
#
# test-shell:
#   image: bats/bats:latest
#   script:
#     - bats tests/

# ═══ PRE-COMMIT HOOK ═════════════════════════════════════════
# .pre-commit-config.yaml:
# - repo: https://github.com/shellcheck-py/shellcheck-py
#   rev: v0.10.0.1
#   hooks:
#     - id: shellcheck
#       args: ["-x"]
