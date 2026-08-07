---
name: shell-cli-design
description: "Design CLI tools with sane flags, streams and codes."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [cli, getopts, ux, stdout, stderr, exit-codes, arguments]
    category: shell
    related_skills: [bash-scripting, bash-error-handling, shell-testing-linting]
---
# Shell CLI Design

The interface contract of a command-line tool: argument parsing, stream
discipline, exit codes, and behavior under automation. A script that prints
diagnostics to stdout cannot be used in a pipeline — that single mistake
disqualifies more scripts than any parsing bug.

## When to Use

Use when writing a script other people (or other scripts) will invoke, adding
flags to an existing tool, deciding what to print where, or making a tool
behave correctly in CI and in pipes.

## The stream contract

| Stream | Carries | Rule |
| --- | --- | --- |
| stdout | The tool's **data** — the thing it produces | Machine-readable, nothing else |
| stderr | Diagnostics: logs, progress, warnings, errors | Never data |
| exit code | Success or the *category* of failure | 0 only on success |

This is what makes composition work:

```bash
./report.sh --json | jq '.total'      # stdout is pure data
./report.sh 2>/dev/null               # suppress noise, keep output
./report.sh > out.json 2> run.log     # separate cleanly
```

If progress messages go to stdout, every one of those breaks. Log helpers must
redirect:

```bash
log()  { printf '%s\n' "$*" >&2; }
emit() { printf '%s\n' "$*"; }        # data only
```

## Argument parsing

### getopts — short options, POSIX, built in

```bash
usage() { cat <<EOF
${0##*/} — description

Usage: ${0##*/} [-v] [-n] -i INPUT [-o OUTPUT]
EOF
}

verbose=0 dry_run=0 input="" output=""

while getopts ':i:o:nvh' opt; do
    case "$opt" in
        i) input="$OPTARG" ;;
        o) output="$OPTARG" ;;
        n) dry_run=1 ;;
        v) verbose=1 ;;
        h) usage; exit 0 ;;
        :)  printf 'option -%s requires an argument\n' "$OPTARG" >&2; exit 2 ;;
        \?) printf 'unknown option: -%s\n' "$OPTARG" >&2; exit 2 ;;
    esac
done
shift $(( OPTIND - 1 ))       # leaves positional arguments in "$@"
```

The **leading colon** in `':i:o:nvh'` enables silent error handling, which is
what lets you emit your own messages via the `:` and `\?` cases. Without it
`getopts` prints its own text to stderr and you get duplicates.

`getopts` cannot do long options. That is its only real limitation.

### Manual loop — long options

```bash
while (( $# )); do
    case "$1" in
        -i|--input)   input="${2:?--input requires a value}"; shift 2 ;;
        -o|--output)  output="${2:?--output requires a value}"; shift 2 ;;
        --input=*)    input="${1#*=}"; shift ;;
        --output=*)   output="${1#*=}"; shift ;;
        -n|--dry-run) dry_run=1; shift ;;
        -v|--verbose) verbose=1; shift ;;
        -h|--help)    usage; exit 0 ;;
        --)           shift; break ;;
        -*)           printf 'unknown option: %s\n' "$1" >&2; exit 2 ;;
        *)            break ;;
    esac
done
```

Support both `--input value` and `--input=value`; users expect both. Handle
`--` as the end-of-options marker so filenames beginning with `-` work.

`scripts/parse-args.sh` is a complete, sourceable implementation including
combined short flags (`-vn`) and repeated options into an array.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | General failure |
| 2 | Usage error — bad or missing arguments |
| 3-125 | Application-specific, documented in `--help` |
| 126 | Found but not executable |
| 127 | Command not found |
| 128+N | Killed by signal N (130 Ctrl-C, 143 SIGTERM) |

Distinguishing 1 from 2 matters: a caller can tell "you invoked me wrong" from
"the operation failed". Document any application-specific codes:

```
Exit codes:
  0  all checks passed
  1  one or more checks failed
  2  invalid usage
  3  could not reach the target
```

## Behaving well under automation

**Detect a TTY before decorating output.** Colors and progress bars corrupt
piped output and CI logs:

```bash
if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
    RED=$'\033[31m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
    RED=""; BOLD=""; RESET=""
fi
```

`[[ -t 1 ]]` tests whether stdout is a terminal. Honor the `NO_COLOR`
convention, and offer `--color=auto|always|never`.

**Read from stdin when no file is given.** This is what makes a tool
composable:

```bash
if (( $# == 0 )) || [[ "$1" == "-" ]]; then
    input=/dev/stdin
else
    input="$1"
fi
```

**Never prompt without a TTY.** An interactive prompt in CI hangs the job:

```bash
confirm() {
    (( FORCE )) && return 0
    [[ -t 0 ]] || die "refusing to prompt without a terminal; pass --force"
    read -r -p "Proceed? [y/N] " reply
    [[ "$reply" == [yY]* ]]
}
```

**Offer `--dry-run` for anything destructive**, and make it print exactly what
would happen.

## Help output

`--help` should be complete enough that the reader never needs the source:

```
mytool — one-line description of what it does

Usage:
  mytool [options] <input>
  mytool --list

Options:
  -i, --input FILE     Input file (use - for stdin)
  -o, --output FILE    Output file (default: stdout)
  -f, --format FMT     Output format: json|text (default: text)
  -n, --dry-run        Show what would happen, change nothing
  -v, --verbose        Verbose diagnostics on stderr
      --no-color       Disable colored output
  -h, --help           This help
      --version        Print the version

Environment:
  MYTOOL_CONFIG        Config file path (default: ~/.config/mytool.conf)
  NO_COLOR             Any value disables color

Exit codes:
  0 success   1 failure   2 usage error

Examples:
  mytool -i data.csv -f json
  cat data.csv | mytool - -f json | jq '.rows'
```

Write it to stdout for `--help` (the user asked for it) and to stderr when
rejecting bad usage.

## Configuration precedence

Highest to lowest, which is what users expect:

1. Command-line flags
2. Environment variables
3. Config file
4. Built-in defaults

```bash
: "${MYTOOL_FORMAT:=text}"                  # env or default
[[ -r "$config" ]] && source "$config"      # config file
[[ -n "$flag_format" ]] && format="$flag_format"   # flag wins
```

Prefix environment variables with the tool name to avoid collisions.

## Subcommands

```bash
main() {
    local cmd="${1:-}"
    [[ -n "$cmd" ]] || { usage >&2; exit 2; }
    shift

    case "$cmd" in
        list)   cmd_list "$@" ;;
        create) cmd_create "$@" ;;
        delete) cmd_delete "$@" ;;
        help|--help|-h) usage ;;
        *) printf 'unknown command: %s\n' "$cmd" >&2; usage >&2; exit 2 ;;
    esac
}
```

Each `cmd_*` function parses its own options, so subcommands can have distinct
flags. Once a tool has more than a handful of subcommands with shared state,
it has outgrown shell — see `python-cli-tools`.

## Pitfalls

- **Diagnostics on stdout** — breaks every pipeline. Route logs to stderr.
- **Exit 0 on failure** — callers cannot detect the error. Return non-zero.
- **Colors without a TTY check** — escape codes end up in logs and files.
- **Prompting in CI** — the job hangs until it times out. Check `[[ -t 0 ]]`.
- **`getopts` without a leading colon** — duplicate error messages.
- **Forgetting `shift $(( OPTIND - 1 ))`** — positional arguments still
  contain the flags.
- **No `--` handling** — files named `-foo` become unusable.
- **Silent success on a no-op** — if nothing matched, say so on stderr.
- **`--force` that skips validation instead of just the prompt** — it should
  bypass confirmation, not safety checks.

## Verification

```bash
./tool.sh --help                       # complete, exits 0
./tool.sh; echo $?                     # usage error -> 2
./tool.sh --bogus; echo $?             # unknown option -> 2
./tool.sh -i in.txt | wc -l            # stdout is pure data
./tool.sh -i in.txt 2>/dev/null | ...  # still works with stderr dropped
./tool.sh -i in.txt > /dev/null        # no color codes leak into files
echo data | ./tool.sh -                # stdin path works
```

`examples/mytool.sh` implements everything above and is exercised by
`examples/mytool.bats`.

## Reference

- `references/exit-codes.md` — conventions, sysexits.h, signal codes
- `scripts/parse-args.sh` — sourceable long/short option parser
- `examples/mytool.sh` — complete tool with subcommands, TTY detection, config
- `examples/mytool.bats` — interface tests for the above

## When NOT to use

- **Internal helper functions** that are never called by a user — skip the full CLI UX.
- **Python CLIs** (click/typer/argparse) — different patterns; this skill is Bash-focused.
- **Script internals** (loops, arrays, quoting) — see [bash-scripting](../shell/bash-scripting/SKILL.md).

## Related skills

- [bash-scripting](../shell/bash-scripting/SKILL.md) — script body implementation.
- [bash-error-handling](../shell/bash-error-handling/SKILL.md) — exit codes and cleanup.
- [shell-testing-linting](../shell/shell-testing-linting/SKILL.md) — testing CLI argument combinations.
- [conventional-commits](../workflows/conventional-commits/SKILL.md) — consistent naming in automation scripts.
