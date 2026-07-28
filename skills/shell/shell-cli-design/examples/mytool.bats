#!/usr/bin/env bats
#
# mytool.bats — interface tests for mytool.sh.
#
# These assert on the CLI *contract*: exit codes, which stream carries what,
# and behavior without a TTY. That contract is what other scripts depend on.

setup_file() {
    SUT="${BATS_TEST_DIRNAME}/mytool.sh"
    export SUT
}

setup() {
    TESTDIR="$(mktemp -d)"
    export TESTDIR
    printf 'one\ntwo\nthree\n' >"${TESTDIR}/data.txt"
    # Isolate from any real user config.
    export MYTOOL_CONFIG="${TESTDIR}/none.conf"
    unset MYTOOL_FORMAT NO_COLOR
}

teardown() { rm -rf "$TESTDIR"; }

# --- exit codes ------------------------------------------------------------

@test "no arguments exits 2" {
    run "$SUT"
    [ "$status" -eq 2 ]
}

@test "unknown command exits 2" {
    run "$SUT" frobnicate
    [ "$status" -eq 2 ]
}

@test "unknown option exits 2" {
    run "$SUT" count --bogus
    [ "$status" -eq 2 ]
}

@test "help exits 0" {
    run "$SUT" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage:"* ]]
    [[ "$output" == *"Exit codes:"* ]]
}

@test "version exits 0" {
    run "$SUT" --version
    [ "$status" -eq 0 ]
    [[ "$output" == *"1.0.0"* ]]
}

@test "unreadable input exits 1" {
    run "$SUT" count -i "${TESTDIR}/missing.txt"
    [ "$status" -eq 1 ]
}

# --- stream discipline -----------------------------------------------------

@test "count writes only data to stdout" {
    stdout_only="$("$SUT" count -i "${TESTDIR}/data.txt" 2>/dev/null)"
    [ "$stdout_only" = "3" ]
}

@test "verbose diagnostics do not pollute stdout" {
    stdout_only="$("$SUT" -v count -i "${TESTDIR}/data.txt" 2>/dev/null)"
    [ "$stdout_only" = "3" ]
}

@test "output is usable in a pipeline" {
    run bash -c "'$SUT' list --format json 2>/dev/null | grep -c alpha"
    [ "$status" -eq 0 ]
    [ "$output" -eq 1 ]
}

# --- stdin -----------------------------------------------------------------

@test "reads stdin when given -" {
    run bash -c "printf 'a\nb\n' | '$SUT' count -"
    [ "$status" -eq 0 ]
    [ "$output" = "2" ]
}

# --- formats ---------------------------------------------------------------

@test "json format is valid-looking" {
    run "$SUT" count -i "${TESTDIR}/data.txt" --format json
    [ "$status" -eq 0 ]
    [ "$output" = '{"lines": 3}' ]
}

@test "MYTOOL_FORMAT env is honored" {
    MYTOOL_FORMAT=json run "$SUT" count -i "${TESTDIR}/data.txt"
    [ "$output" = '{"lines": 3}' ]
}

@test "flag overrides the environment variable" {
    MYTOOL_FORMAT=json run "$SUT" count -i "${TESTDIR}/data.txt" --format text
    [ "$output" = "3" ]
}

# --- color -----------------------------------------------------------------

@test "no ANSI codes when stderr is not a terminal" {
    run bash -c "'$SUT' -v count -i '${TESTDIR}/data.txt' 2>&1 >/dev/null"
    [[ "$output" != *$'\033['* ]]
}

@test "--color=never suppresses codes even when forced" {
    run bash -c "'$SUT' --color=never -v count -i '${TESTDIR}/data.txt' 2>&1 >/dev/null"
    [[ "$output" != *$'\033['* ]]
}

@test "invalid --color value is a usage error" {
    run "$SUT" --color=rainbow list
    [ "$status" -eq 2 ]
}

# --- destructive operations ------------------------------------------------

@test "dry run changes nothing and exits 0" {
    run "$SUT" delete --dry-run item1 item2
    [ "$status" -eq 0 ]
    [[ "$output" == *"would delete: item1"* ]]
    [[ "$output" == *"would delete: item2"* ]]
}

@test "delete without a TTY and without --force exits 2" {
    run bash -c "'$SUT' delete item1 < /dev/null"
    [ "$status" -eq 2 ]
    [[ "$output" == *"--force"* ]]
}

@test "--force skips the prompt" {
    run bash -c "'$SUT' delete --force item1 < /dev/null"
    [ "$status" -eq 0 ]
    [[ "$output" == *"deleted: item1"* ]]
}

@test "partial failure exits 3" {
    run bash -c "'$SUT' delete --force good1 bad1 < /dev/null"
    [ "$status" -eq 3 ]
}

@test "total failure exits 1" {
    run bash -c "'$SUT' delete --force bad1 bad2 < /dev/null"
    [ "$status" -eq 1 ]
}

@test "delete with no targets is a usage error" {
    run "$SUT" delete
    [ "$status" -eq 2 ]
}

# --- argument handling -----------------------------------------------------

@test "-- allows arguments that look like options" {
    run "$SUT" delete --dry-run -- --weird-name
    [ "$status" -eq 0 ]
    [[ "$output" == *"would delete: --weird-name"* ]]
}

@test "global options work after the subcommand" {
    run "$SUT" count -i "${TESTDIR}/data.txt" --format json
    [ "$status" -eq 0 ]
    [[ "$output" == *"lines"* ]]
}
