#!/usr/bin/env bats
#
# myscript.bats — a complete bats suite demonstrating the patterns from the
# skill: `run` assertions, fixtures, PATH stubbing, sourcing for unit tests,
# and failure-path coverage.
#
# Run with:
#   bats examples/myscript.bats
#
# The script under test is the template from the bash-scripting skill.

setup_file() {
    # Resolve the script under test once for the whole file.
    SUT="${BATS_TEST_DIRNAME}/../../bash-scripting/scripts/template.sh"
    export SUT
}

setup() {
    # A fresh temp directory per test; teardown removes it.
    TESTDIR="$(mktemp -d)"
    export TESTDIR

    printf 'hello world\nsecond line\n' >"${TESTDIR}/input.txt"

    # Stub directory takes precedence over real commands on PATH.
    STUB_DIR="${TESTDIR}/stubs"
    mkdir -p "$STUB_DIR"
    export STUB_DIR
}

teardown() {
    rm -rf "$TESTDIR"
}

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

@test "exits 0 and uppercases input" {
    run "$SUT" -i "${TESTDIR}/input.txt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"HELLO WORLD"* ]]
    [[ "$output" == *"SECOND LINE"* ]]
}

@test "writes to the output file when -o is given" {
    run "$SUT" -i "${TESTDIR}/input.txt" -o "${TESTDIR}/out.txt"
    [ "$status" -eq 0 ]
    [ -f "${TESTDIR}/out.txt" ]
    grep -q 'HELLO WORLD' "${TESTDIR}/out.txt"
}

@test "dry run does not create the output file" {
    run "$SUT" -n -i "${TESTDIR}/input.txt" -o "${TESTDIR}/out.txt"
    [ "$status" -eq 0 ]
    [ ! -f "${TESTDIR}/out.txt" ]
}

@test "help exits 0 and prints usage" {
    run "$SUT" -h
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage:"* ]]
}

# ---------------------------------------------------------------------------
# Failure paths -- the part most shell test suites omit
# ---------------------------------------------------------------------------

@test "missing required argument exits 2" {
    run "$SUT"
    [ "$status" -eq 2 ]
}

@test "unreadable input exits 1 with a message on stderr" {
    run "$SUT" -i "${TESTDIR}/does-not-exist.txt"
    [ "$status" -eq 1 ]
    [[ "$output" == *"not readable"* ]]
}

@test "unknown option exits non-zero" {
    run "$SUT" -Z
    [ "$status" -ne 0 ]
}

@test "leaves no temp directories behind on failure" {
    local before after
    before="$(find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'tmp.*' 2>/dev/null | wc -l)"
    run "$SUT" -i "${TESTDIR}/does-not-exist.txt"
    [ "$status" -eq 1 ]
    after="$(find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'tmp.*' 2>/dev/null | wc -l)"
    [ "$before" -eq "$after" ]
}

# ---------------------------------------------------------------------------
# Output stream separation
# ---------------------------------------------------------------------------

@test "diagnostics go to stderr, data to stdout" {
    # Capture only stdout; log lines must not appear in it.
    stdout_only="$("$SUT" -i "${TESTDIR}/input.txt" 2>/dev/null)"
    [[ "$stdout_only" == *"HELLO WORLD"* ]]
    [[ "$stdout_only" != *"INFO"* ]]
}

@test "stdout is usable in a pipeline" {
    run bash -c "'$SUT' -i '${TESTDIR}/input.txt' 2>/dev/null | grep -c ."
    [ "$status" -eq 0 ]
    [ "$output" -eq 2 ]
}

# ---------------------------------------------------------------------------
# PATH stubbing -- replace an external command with a fake
# ---------------------------------------------------------------------------

@test "fails cleanly when a required command is missing" {
    # Note: making a stub non-executable does NOT work here. `command -v`
    # skips non-executable files and keeps searching, so the real `tr` further
    # along PATH is still found. To exercise the missing-command path, PATH
    # must be replaced entirely with a directory that lacks the command.
    local minimal="${TESTDIR}/minimal-path"
    mkdir -p "$minimal"

    # Everything the script (and its `#!/usr/bin/env bash` shebang) needs,
    # except `tr`. Omitting `bash` here would make the shebang itself fail
    # with 127 before a single line of the script ran.
    local cmd
    for cmd in bash mktemp date rm mv cat; do
        ln -s "$(command -v "$cmd")" "${minimal}/${cmd}"
    done

    PATH="$minimal" run "$SUT" -i "${TESTDIR}/input.txt"
    [ "$status" -ne 0 ]
    [[ "$output" == *"tr"* ]]
}

@test "stubbed command is called instead of the real one" {
    cat >"${STUB_DIR}/tr" <<'EOF'
#!/usr/bin/env bash
echo "STUBBED"
EOF
    chmod +x "${STUB_DIR}/tr"

    PATH="${STUB_DIR}:${PATH}" run "$SUT" -i "${TESTDIR}/input.txt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"STUBBED"* ]]
}

# ---------------------------------------------------------------------------
# Unit-testing individual functions by sourcing
#
# Requires the script to guard its entry point:
#   if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then main "$@"; fi
# ---------------------------------------------------------------------------

@test "sourcing exposes functions without running main" {
    # template.sh calls main unconditionally, so sourcing it runs the script.
    # This test documents the requirement rather than asserting on it.
    skip "template.sh does not guard its entry point; see the skill's 'Making scripts testable'"

    source "$SUT"
    run process /dev/null "" 1
    [ "$status" -eq 0 ]
}
