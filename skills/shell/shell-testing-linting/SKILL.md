---
name: shell-testing-linting
description: "Lint with shellcheck and test scripts with bats."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [shellcheck, shfmt, bats, testing, linting, ci]
    category: shell
    related_skills: [bash-scripting, bash-error-handling, shell-cli-design]
---
# Shell Testing and Linting

Making shell scripts verifiable: `shellcheck` for static analysis, `shfmt` for
formatting, and `bats` for behavioral tests. Shell is the language where
"it ran once" is most often mistaken for "it works".

## When to Use

Use when adding a script to CI, reviewing shell in a pull request, silencing a
shellcheck warning correctly, or writing tests for a script that already
exists.

## Prerequisites

```bash
# Debian/Ubuntu
apt-get install -y shellcheck
# macOS
brew install shellcheck shfmt bats-core
# Container, no install
docker run --rm -v "$PWD:/mnt" koalaman/shellcheck:stable /mnt/script.sh
```

`shfmt` and `bats-core` are Go/Bash projects and can also be vendored into a
repo or fetched in CI.

## shellcheck

```bash
shellcheck script.sh              # analyze one file
shellcheck -x script.sh           # follow `source`d files (usually wanted)
shellcheck -S warning script.sh   # minimum severity: error|warning|info|style
shellcheck -f gcc script.sh       # compact output for CI annotations
shellcheck -e SC2086 script.sh    # exclude a check globally
shellcheck -o all script.sh       # enable every optional check
shellcheck --shell=sh script.sh   # analyze as POSIX sh, flagging bashisms
```

`-x` matters: without it, shellcheck cannot see variables and functions
defined in sourced libraries and reports false positives.

### Severity levels

| Level | Meaning | CI policy |
| --- | --- | --- |
| `error` | Almost certainly a bug | Always fail |
| `warning` | Likely a bug | Fail |
| `info` | Suboptimal but works | Fail on new code |
| `style` | Readability | Optional |

A reasonable gate is `-S warning` for existing repositories and `-S style` for
new ones.

### The checks that matter most

| Code | Problem | Fix |
| --- | --- | --- |
| SC2086 | Unquoted variable — word splitting and globbing | `"$var"` |
| SC2046 | Unquoted command substitution | `"$(cmd)"` |
| SC2155 | `local x=$(cmd)` masks the exit status | Split declaration and assignment |
| SC2164 | `cd` without checking | `cd "$d" \|\| exit` |
| SC2181 | `if [ $? -ne 0 ]` | Test the command directly |
| SC2115 | `rm -rf "$a/$b"` with a possibly empty variable | `"${a:?}/${b:?}"` |
| SC2068 | Unquoted `$@` | `"$@"` |
| SC2012 | Parsing `ls` | Use `find` or a glob |
| SC2059 | Variable in a `printf` format string | `printf '%s' "$var"` |
| SC1090 | Cannot follow a dynamic `source` | `# shellcheck source=path` |

`references/shellcheck-codes.md` explains each with a before/after.

### Suppressing correctly

Suppress narrowly, on the line above the offending command, and always with a
reason:

```bash
# shellcheck disable=SC2086  # word splitting is intended: $FLAGS holds several args
run_tool $FLAGS
```

The directive applies to the **next command only**. Placing it above a
comment, a blank line, or a multi-line construct silently does nothing —
verify by re-running shellcheck rather than assuming.

File-wide suppressions belong in `.shellcheckrc`, and each needs a comment
justifying it:

```
# .shellcheckrc
disable=SC2312   # command-substitution exit codes are checked via pipefail
source-path=SCRIPTDIR/lib
external-sources=true
```

## shfmt

```bash
shfmt -d script.sh                  # diff (non-zero exit when unformatted)
shfmt -w script.sh                  # rewrite in place
shfmt -l .                          # list unformatted files
shfmt -i 4 -ci -bn -sr script.sh    # 4-space indent, indent cases, binary
                                    # ops at line start, redirect spacing
```

Pick one option set, record it in `.editorconfig` or a Makefile, and enforce
it in CI. The specific style matters far less than it being automatic — the
goal is to remove formatting from code review entirely.

```ini
# .editorconfig — shfmt reads this
[*.sh]
indent_style = space
indent_size = 4
switch_case_indent = true
binary_next_line = true
```

## bats

`bats` runs test files where each `@test` block is a script; the block fails
if any command in it fails.

```bash
#!/usr/bin/env bats

setup() {
    load '../scripts/helpers.bash'
    TMPDIR_TEST="$(mktemp -d)"
}

teardown() {
    rm -rf "$TMPDIR_TEST"
}

@test "exits 0 on valid input" {
    run ./myscript.sh -i fixtures/good.txt
    [ "$status" -eq 0 ]
}

@test "reports a usage error without arguments" {
    run ./myscript.sh
    [ "$status" -eq 2 ]
    [[ "$output" == *"Usage:"* ]]
}

@test "writes the output file" {
    run ./myscript.sh -i fixtures/good.txt -o "$TMPDIR_TEST/out"
    [ "$status" -eq 0 ]
    [ -f "$TMPDIR_TEST/out" ]
}
```

`run` captures the exit status into `$status`, combined output into `$output`,
and per-line output into `${lines[@]}`. Without `run`, a non-zero exit fails
the test immediately — which is what you want for setup steps and not for the
command under test.

```bash
bats test/                # run a directory
bats -t test/             # TAP output for CI
bats -f 'usage' test/     # filter by test name
bats --jobs 4 test/       # parallel
```

### Making scripts testable

A script that runs work at the top level cannot be sourced for unit testing.
Guard the entry point so the file can be sourced to expose its functions:

```bash
# At the bottom of the script:
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
```

Then a test can source it and call individual functions:

```bash
@test "parse_version extracts the minor number" {
    source ./myscript.sh
    run parse_version "1.24.3"
    [ "$output" = "24" ]
}
```

Other things that make shell testable: take paths as parameters rather than
hardcoding them, write output to stdout instead of fixed files, and put
external commands behind small wrapper functions that tests can stub.

## Stubbing external commands

Prepend a directory of fakes to `PATH`:

```bash
setup() {
    STUB_DIR="$(mktemp -d)"
    cat > "$STUB_DIR/curl" <<'EOF'
#!/usr/bin/env bash
echo '{"status":"ok"}'
EOF
    chmod +x "$STUB_DIR/curl"
    PATH="$STUB_DIR:$PATH"
}
```

This works because the script calls `curl` by name and the shell resolves it
through `PATH`. Scripts that hardcode `/usr/bin/curl` cannot be stubbed this
way — another reason to call commands by bare name.

## CI wiring

```yaml
# .github/workflows/shell.yml
name: shell
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: shellcheck
        run: |
          sudo apt-get update && sudo apt-get install -y shellcheck
          find . -name '*.sh' -print0 | xargs -0 shellcheck -x -S warning
      - name: shfmt
        run: |
          go install mvdan.cc/sh/v3/cmd/shfmt@latest
          "$(go env GOPATH)/bin/shfmt" -d -i 4 -ci -bn .
      - name: bats
        run: |
          sudo apt-get install -y bats
          bats -t test/
```

Run all three; they catch disjoint classes of problem. `shellcheck` finds
quoting and logic bugs, `shfmt` removes style debate, `bats` verifies actual
behavior.

## Pitfalls

- **`shellcheck` without `-x`** — false positives on sourced variables.
- **Blanket `disable=SC2086` at the top of a file** — hides every real
  quoting bug in it.
- **A disable directive not immediately above the command** — silently
  ineffective.
- **Tests that depend on the network or the real filesystem** — stub through
  `PATH` and use `mktemp -d`.
- **`bats` tests without `run`** — the test aborts on the first non-zero exit
  instead of asserting on it.
- **Testing only the happy path** — the failure paths are exactly where shell
  scripts break; assert on exit codes and stderr.
- **Formatting checks that only run locally** — enforce in CI or they decay.

## Verification

```bash
shellcheck -x -S style script.sh && echo "lint clean"
shfmt -d -i 4 -ci -bn script.sh && echo "format clean"
bats -t test/
```

`scripts/check.sh` runs all three over a tree and returns a single status.

## Reference

- `references/shellcheck-codes.md` — the frequent codes with before/after
- `scripts/check.sh` — combined lint, format, and parse gate for CI
- `examples/myscript.bats` — a complete bats suite with stubbing
