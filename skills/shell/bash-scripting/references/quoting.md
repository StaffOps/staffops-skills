# Quoting and Expansion Reference

Most shell bugs are quoting bugs. This document explains *why* they happen —
the order in which Bash transforms a command line — so the rules become
derivable rather than memorized.

## Expansion order

Bash processes every command line in this order. Understanding it explains
almost every surprising behavior.

1. **Brace expansion** — `{a,b}` → `a b`. Purely textual, happens first.
2. **Tilde expansion** — `~` → `$HOME`.
3. **Parameter expansion** — `$var`, `${var}`.
4. **Command substitution** — `$(cmd)`.
5. **Arithmetic expansion** — `$(( ... ))`.
6. **Word splitting** — the result of steps 3-5 is split on `IFS`.
7. **Pathname expansion (globbing)** — `*`, `?`, `[...]` match filenames.
8. **Quote removal** — the quotes themselves are stripped.

Steps **6 and 7 are the dangerous ones**, and they are exactly what double
quotes suppress. This is the entire reason `"$var"` is the default.

```bash
files="a.txt b.txt"

ls $files     # split into two words → ls a.txt b.txt
ls "$files"   # one word → ls "a.txt b.txt" → No such file
```

Note what does *not* happen: **word splitting never applies to a literal**.
`ls "a.txt b.txt"` and `ls a.txt\ b.txt` are the same. Splitting only affects
the *result* of an expansion — which is why quoting the expansion fixes it.

## The three quoting contexts

| Context | Expansions performed | Use for |
| --- | --- | --- |
| `'single'` | None. Everything is literal. | Regexes, `awk`/`sed` programs, passwords |
| `"double"` | `$var`, `$(cmd)`, `$((...))`, `` \` `` | Almost everything |
| unquoted | All, including splitting and globbing | Deliberate splitting only |

```bash
name="world"

echo 'hello $name'    # hello $name
echo "hello $name"    # hello world
```

Single quotes cannot contain a single quote — not even escaped. To include
one, end the quote, add an escaped quote, and reopen:

```bash
echo 'it'\''s here'   # it's here
```

## Where quoting is not needed

These contexts do not word-split, so quoting is optional (though harmless and
often clearer):

```bash
[[ $var == value ]]        # [[ ]] does not split
(( count > 10 ))           # arithmetic context
var=$other                 # right side of a plain assignment
case $var in ... esac      # case word
${var:-$default}           # inside an expansion's default
```

Everything else — command arguments, `[ ]` tests, redirect targets, array
elements — needs quotes.

Note that `[ ]` (single bracket) is a *command*, so it **does** split:

```bash
var=""
[ $var = x ]     # becomes [ = x ] → syntax error
[[ $var == x ]]  # fine
```

## Globs and the empty-match problem

When a glob matches nothing, Bash leaves the pattern **literal** by default:

```bash
for f in *.nomatch; do
    echo "$f"        # prints the literal string *.nomatch
done
```

Fix with `nullglob` (expand to nothing) or guard explicitly:

```bash
shopt -s nullglob
for f in *.log; do ...; done     # loop body never runs if no matches

# Or, without changing shell options:
for f in *.log; do
    [[ -e "$f" ]] || continue
    ...
done
```

Related options:

| Option | Effect |
| --- | --- |
| `nullglob` | Non-matching globs expand to nothing |
| `failglob` | Non-matching globs are an error |
| `dotglob` | `*` also matches files starting with `.` |
| `globstar` | Enables `**` for recursive matching |
| `nocaseglob` | Case-insensitive matching |

## IFS: what actually splits

`IFS` (Internal Field Separator) defaults to space, tab, newline. Word
splitting uses it; changing it changes splitting behavior:

```bash
line="a:b:c"

IFS=: read -r x y z <<< "$line"
printf '%s|%s|%s\n' "$x" "$y" "$z"     # a|b|c
```

Scoping `IFS` to a single command (as above) is safe. Setting it globally
affects every later expansion and is a common source of action-at-a-distance
bugs. If you must, save and restore:

```bash
old_ifs="$IFS"
IFS=$'\n'
# ...
IFS="$old_ifs"
```

Setting `IFS=` (empty) in `while IFS= read -r` disables splitting entirely,
which is why that idiom preserves leading and trailing whitespace.

## Command substitution

`$(...)` strips **all trailing newlines**. This is usually what you want, but
it means you cannot capture trailing blank lines:

```bash
content="$(cat file.txt)"     # trailing newlines gone
```

To preserve them, append a sentinel and remove it:

```bash
content="$(cat file.txt; printf x)"
content="${content%x}"
```

Prefer `$(...)` over backticks: it nests without escaping, and it does not
treat backslashes specially.

```bash
outer="$(echo "$(date +%Y)")"   # clean
outer="`echo \`date +%Y\``"     # legal but unreadable
```

## Quoting in nested contexts

Double quotes do not nest, but command substitution resets the context — the
quotes inside `$(...)` are independent of those outside:

```bash
echo "Today is $(date +"%A, %d %B")"    # correct, inner quotes are fine
```

For `find -exec`, quote the shell fragment in single quotes so the *outer*
shell leaves `{}` and `$0` alone:

```bash
find . -name '*.log' -exec sh -c 'gzip -- "$1"' _ {} \;
```

For `ssh` and `sudo bash -c`, the remote side re-parses the string, so it
needs a second level of quoting. `${var@Q}` produces it correctly:

```bash
ssh host "ls ${dir@Q}"
```

## Arrays are the answer to dynamic commands

Any time you are tempted to build a command as a string, use an array. A
string loses quoting on re-expansion and there is no correct way to recover
it:

```bash
# WRONG — quotes become literal characters
cmd="rsync -a --exclude 'node_modules' $src $dst"
$cmd

# Correct
cmd=(rsync -a --exclude 'node_modules' "$src" "$dst")
"${cmd[@]}"
```

If you need to log what will run, use `${cmd[*]@Q}` — it produces a
copy-pasteable, correctly quoted line.

## Checklist

- Every `$var` and `$(cmd)` is inside double quotes, unless splitting is
  deliberate.
- `"$@"` (never `$*`) to forward arguments.
- `[[ ]]` instead of `[ ]`.
- Single quotes for regexes and `awk`/`sed` programs.
- `shopt -s nullglob` or an existence guard before every glob loop.
- Arrays for dynamic command lines.
- `shellcheck` clean — it detects nearly every violation above.
