# Builtins That Replace External Commands

Every external command in a loop costs a `fork` + `exec`. In a loop over
10,000 lines that is 10,000 processes. Bash builtins run in-process and are
typically 50-100x faster.

## The substitution table

| External | Builtin equivalent | Notes |
| --- | --- | --- |
| `basename "$p"` | `"${p##*/}"` | No trailing-slash handling |
| `dirname "$p"` | `"${p%/*}"` | Returns `$p` if there is no `/` |
| `echo "$s" \| tr a-z A-Z` | `"${s^^}"` | Bash 4+ |
| `echo "$s" \| sed 's/a/b/'` | `"${s/a/b}"` | Literal, not regex |
| `echo "$s" \| cut -c1-3` | `"${s:0:3}"` | |
| `expr length "$s"` | `"${#s}"` | |
| `expr $a + $b` | `$(( a + b ))` | Integers only |
| `cat file` | `"$(< file)"` | No subshell in Bash |
| `seq 1 10` | `{1..10}` | Brace expansion, literal only |
| `test -f "$f"` | `[[ -f "$f" ]]` | |
| `pwd` | `"$PWD"` | |
| `date +%s` | `"$EPOCHSECONDS"` | Bash 5+ |
| `sleep 0.5` | `read -t 0.5 -u X` | Rarely worth it; `sleep` is fine |

`basename` and `dirname` differ from the expansions at the edges — for
`/a/b/`, `basename` gives `b` while `${p##*/}` gives an empty string. Strip
trailing slashes first (`p="${p%/}"`) if that matters.

## Reading a file without `cat`

```bash
content="$(< /etc/hostname)"      # builtin redirection, no subshell for cat

# Line by line, no external process at all.
while IFS= read -r line; do
    printf '%s\n' "$line"
done < /etc/passwd
```

`$(< file)` is a Bash optimization: it reads the file directly instead of
running `cat` in a subshell.

## String tests without `grep`

```bash
# Substring.
[[ "$haystack" == *"$needle"* ]]

# Prefix / suffix.
[[ "$path" == /var/* ]]
[[ "$file" == *.log ]]

# Regex with captures.
if [[ "$version" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
    major="${BASH_REMATCH[1]}"
    minor="${BASH_REMATCH[2]}"
    patch="${BASH_REMATCH[3]}"
fi
```

The regex in `=~` must be **unquoted** to be treated as a pattern. Quoting it
makes it a literal string — a very common bug:

```bash
[[ "$s" =~ ^[0-9]+$ ]]      # regex
[[ "$s" =~ "^[0-9]+$" ]]    # literal string match — almost never intended
```

Store complex patterns in a variable to avoid escaping issues:

```bash
re='^([0-9]{4})-([0-9]{2})-([0-9]{2})$'
[[ "$date" =~ $re ]]        # unquoted variable, still a regex
```

## Arithmetic

```bash
(( count++ ))
(( total += n ))
(( max = a > b ? a : b ))

if (( count > 10 )); then ...
```

Inside `(( ))` variables do not need `$`, and comparison uses `<` `>` `==`
rather than `-lt` `-gt` `-eq`. Integer only — Bash has no floating point:

```bash
# For floats, use awk.
pct="$(awk -v a="$hits" -v b="$total" 'BEGIN { printf "%.2f", a/b*100 }')"
```

Note that `(( expr ))` returns exit status 1 when the expression evaluates to
zero. Under `set -e` this terminates the script:

```bash
count=0
(( count++ ))      # returns 1 because the *old* value was 0 → script exits

(( count++ )) || true      # safe
count=$(( count + 1 ))     # safer: assignment always succeeds
```

## printf instead of echo

`echo` behavior varies across shells and implementations for `-n`, `-e`, and
leading dashes. `printf` is specified and predictable:

```bash
printf '%s\n' "$var"            # always literal, always one trailing newline
printf '%s\n' "${array[@]}"     # format reused for each element — one per line
printf '%-20s %6.2f\n' "$name" "$value"
printf -v padded '%05d' "$n"    # assign to a variable, no subshell
```

`printf -v` is the fastest way to format into a variable — it avoids the
subshell that `var=$(printf ...)` would create.

## Loop performance

The difference is measurable:

```bash
# ~10,000 forks
for i in {1..10000}; do
    name=$(basename "/path/to/file$i.txt")
done

# zero forks
for i in {1..10000}; do
    name="/path/to/file$i.txt"; name="${name##*/}"
done
```

The rule of thumb: **no external command inside a hot loop**. If the work
genuinely needs `awk` or `sed`, restructure so the external tool processes the
whole stream once instead of being called per line:

```bash
# Slow: one sed per line
while read -r line; do
    echo "$line" | sed 's/foo/bar/'
done < input

# Fast: one sed total
sed 's/foo/bar/' < input
```

## Useful builtins that are easy to forget

| Builtin | Use |
| --- | --- |
| `mapfile -t arr < file` | Read a file into an array (Bash 4+) |
| `read -a arr <<< "$line"` | Split a line into an array on `IFS` |
| `printf -v var` | Format into a variable without a subshell |
| `local -n ref=name` | Nameref — pass an array to a function by reference |
| `caller` | Call stack, for error traps |
| `type -t cmd` | Is it a builtin, function, alias, or file? |
| `command -v cmd` | Portable "is this installed" check |
| `wait -n` | Wait for the next background job to finish |
| `shopt -s inherit_errexit` | Make `set -e` apply inside `$(...)` |

```bash
# Read a file into an array, one line per element.
mapfile -t lines < /etc/hosts
printf 'read %d lines\n' "${#lines[@]}"

# Check a dependency exists before using it.
command -v jq >/dev/null 2>&1 || { printf 'jq is required\n' >&2; exit 1; }

# Pass an array to a function by reference (Bash 4.3+).
process() {
    local -n arr="$1"
    printf '%s\n' "${arr[@]}"
}
process myarray
```
