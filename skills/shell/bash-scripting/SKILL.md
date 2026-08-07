---
name: bash-scripting
description: "Write portable, safe Bash scripts that fail loudly."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [bash, shell, scripting, posix, automation]
    category: shell
    related_skills: [bash-error-handling, shell-cli-design, shell-testing-linting, shell-text-processing]
---
# Bash Scripting

Writing Bash that survives contact with production: strict mode, correct
quoting, arrays, and parameter expansion. Covers Bash 4+ specifically — where
POSIX `sh` compatibility matters, that is called out inline.

This skill is about *writing* scripts. Failure handling and traps live in
[bash-error-handling](../bash-error-handling/SKILL.md); argument parsing and
UX live in [shell-cli-design](../shell-cli-design/SKILL.md).

## When to Use

Use when writing or reviewing a shell script, deciding between Bash and
Python, debugging word-splitting and glob bugs, or hardening an existing
script that grew organically.

## Prerequisites

- Bash 4.0+ (`bash --version`). macOS ships Bash 3.2 — install a modern one
  via Homebrew or write POSIX `sh`.
- `shellcheck` for linting. See
  [shell-testing-linting](../shell-testing-linting/SKILL.md).

## Quick Reference

| Task | Correct form | Why |
| --- | --- | --- |
| Use a variable | `"$var"` | Unquoted values are word-split and glob-expanded |
| Command output | `"$(cmd)"` | `$(...)` nests; backticks do not |
| Arithmetic | `$(( a + b ))` | No `expr`, no subshell |
| Test a string | `[[ "$a" == "$b" ]]` | `[[` does not word-split |
| Test a number | `(( a > b ))` | Numeric context, no `-gt` |
| Default value | `"${var:-default}"` | Empty *or* unset |
| Required value | `"${var:?message}"` | Aborts with a message if unset |
| Array of args | `"${args[@]}"` | Preserves element boundaries |
| Loop over files | `for f in *.txt` | Never `for f in $(ls)` |
| Read lines | `while IFS= read -r line` | Preserves whitespace and backslashes |

## The script skeleton

Every non-trivial script starts from `scripts/template.sh`:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

main() {
    local input="${1:?usage: ${0##*/} <input>}"
    process "$input"
}

process() {
    local input="$1"
    printf 'processing %s\n' "$input"
}

main "$@"
```

Three details that matter:

- `#!/usr/bin/env bash` finds Bash via `PATH`, unlike `/bin/bash`.
- Wrapping logic in `main` means the file parses completely before anything
  runs — editing a script while it executes cannot corrupt a partial read.
- `main "$@"` passes arguments through with boundaries intact.

## Quoting

Word splitting and globbing are the source of most shell bugs. The rule is
simple: **quote every expansion** unless you specifically want splitting.

```bash
file="my report.txt"

rm $file      # WRONG: deletes "my" and "report.txt"
rm "$file"    # correct

files=(*.log)
process $files      # WRONG: only the first element, then split
process "${files[@]}"   # correct: one argument per file
```

`$*` versus `$@` inside quotes:

| Expansion | Result for args `a` `b c` |
| --- | --- |
| `"$@"` | `a`, `b c` — two arguments |
| `"$*"` | `a b c` — one argument, joined by `IFS` |
| `$@` | `a`, `b`, `c` — three arguments (split) |

Use `"$@"` unless you are deliberately building a single string.

See `references/quoting.md` for the full expansion order and the cases where
quoting is not needed.

## Parameter expansion

Bash can do most string manipulation without calling out to `sed` or `cut`,
which is faster and avoids a subshell:

```bash
path="/var/log/nginx/access.log"

"${path##*/}"      # access.log      (basename)
"${path%/*}"       # /var/log/nginx  (dirname)
"${path%.log}"     # /var/log/nginx/access
"${path//\//_}"    # _var_log_nginx_access.log
"${path:5:3}"      # log
"${#path}"         # 29

name="${1:-}"                    # default to empty, safe under `set -u`
count="${COUNT:-10}"             # default if unset or empty
token="${TOKEN:?TOKEN is required}"   # abort with a message
```

`references/parameter-expansion.md` has the complete table including
case conversion, indirection, and the `${var@Q}` quoting operator.

## Arrays

Arrays are the only correct way to build command lines dynamically:

```bash
args=(--verbose --output "$out_dir")
[[ -n "$filter" ]] && args+=(--filter "$filter")

mycommand "${args[@]}"
```

Never build a command in a plain string — quoting is lost on re-expansion:

```bash
cmd="mycommand --output '$out_dir'"
$cmd   # WRONG: quotes are literal, spaces still split
```

Associative arrays (Bash 4+) need an explicit declaration:

```bash
declare -A counts
counts[error]=3
counts[warn]=12

for key in "${!counts[@]}"; do
    printf '%s=%s\n' "$key" "${counts[$key]}"
done
```

## Reading input safely

```bash
# Read a file line by line, preserving whitespace and backslashes.
while IFS= read -r line; do
    printf '%s\n' "$line"
done < "$file"

# Handle a final line with no trailing newline.
while IFS= read -r line || [[ -n "$line" ]]; do
    printf '%s\n' "$line"
done < "$file"

# Filenames with spaces or newlines: NUL-delimited.
while IFS= read -r -d '' file; do
    process "$file"
done < <(find . -name '*.log' -print0)
```

`IFS=` prevents leading and trailing whitespace from being stripped; `-r`
stops backslash interpretation. Both are almost always wanted.

## Subshells and process substitution

A pipeline runs each stage in a subshell, so variable assignments inside it
are lost:

```bash
count=0
find . -name '*.log' | while read -r f; do
    (( count++ ))       # modifies a subshell copy
done
echo "$count"           # still 0

# Correct: process substitution keeps the loop in the current shell.
count=0
while read -r f; do
    (( count++ ))
done < <(find . -name '*.log')
echo "$count"           # correct
```

## Bash vs Python

Reach for Python when a script needs any of the following. Rewriting a
600-line Bash script later is more expensive than starting in Python.

| Signal | Why Bash struggles |
| --- | --- |
| Structured data (JSON, YAML, CSV) | No native parsing; `jq` helps but composes poorly |
| Arithmetic beyond integers | Bash has no floating point |
| More than ~200 lines | No modules, no real data structures |
| Needs unit tests | Testable, but the tooling is thin |
| Concurrency with result collection | `wait -n` exists but is awkward |
| Must run on Windows | Requires WSL or Git Bash |

Bash remains the right tool for process orchestration, glue between CLIs, and
anything that is mostly redirection and pipelines.

## Pitfalls

- **`for f in $(ls)`** — breaks on spaces. Use a glob: `for f in *.txt`.
  Guard against a non-matching glob with `shopt -s nullglob`.
- **`cd` without checking** — `cd "$dir" || exit 1`, or the rest of the script
  runs in the wrong directory.
- **`[ $var = x ]`** — breaks when `$var` is empty or has spaces. Use `[[ ]]`.
- **Unquoted `$(...)` in a test** — same word-splitting problem.
- **`echo "$var"`** with a leading `-` or backslashes is not portable. Use
  `printf '%s\n' "$var"`.
- **Parsing `ls`** — its output is not machine-readable. Use `find` or globs.
- **`sudo cmd > /root/file`** — the redirect happens as *your* user. Use
  `cmd | sudo tee /root/file > /dev/null`.

## Verification

```bash
shellcheck -x script.sh          # static analysis, follows sourced files
bash -n script.sh                # parse without executing
bash -x script.sh                # trace execution
shfmt -d -i 4 -ci script.sh      # formatting diff
```

Run `scripts/lint.sh` to apply all four to a directory tree.

## Reference

- `references/quoting.md` — expansion order, when quoting is optional
- `references/parameter-expansion.md` — complete expansion operator table
- `references/builtins.md` — Bash builtins that replace external commands
- `scripts/template.sh` — production script skeleton
- `scripts/lint.sh` — shellcheck + shfmt + parse check over a tree
- `examples/` — annotated scripts built from these rules

## When NOT to use

- **Tasks over ~200 lines** or with complex data structures — switch to Python.
- **Cross-platform portability** where only POSIX sh is available — avoid Bash-specific features.
- **Error handling / trap patterns** — see [bash-error-handling](../shell/bash-error-handling/SKILL.md) for the dedicated treatment.

## Related skills

- [bash-error-handling](../shell/bash-error-handling/SKILL.md) — set -euo pipefail, traps, cleanup.
- [shell-cli-design](../shell/shell-cli-design/SKILL.md) — argument parsing, usage messages.
- [shell-text-processing](../shell/shell-text-processing/SKILL.md) — awk, sed, jq pipelines.
- [shell-testing-linting](../shell/shell-testing-linting/SKILL.md) — shellcheck, bats.
- [linux-command-line](../linux/linux-command-line/SKILL.md) — pipes, redirection, job control.
