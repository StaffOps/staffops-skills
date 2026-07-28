# Frequent shellcheck Codes

Each entry shows the flagged pattern, why it is wrong, and the fix.

## SC2086 — Unquoted variable

The most common finding by a wide margin.

```bash
rm $file                    # flagged
cp $src $dst
```

An unquoted expansion is word-split on `IFS` and then glob-expanded. `file="a
b.txt"` becomes two arguments; `file="*"` expands to every file in the
directory.

```bash
rm -- "$file"
cp -- "$src" "$dst"
```

Deliberate splitting is the rare exception — and an array expresses it better:

```bash
# shellcheck disable=SC2086  # $FLAGS intentionally splits into separate args
run $FLAGS

# Better: no suppression needed
flags=(--verbose --color)
run "${flags[@]}"
```

## SC2046 — Unquoted command substitution

```bash
rm $(find . -name '*.tmp')       # flagged; breaks on spaces in names
```

```bash
find . -name '*.tmp' -delete                     # best: no shell involved
find . -name '*.tmp' -print0 | xargs -0 rm --    # if a command is required
```

## SC2155 — Declaration masks the exit status

```bash
local ver=$(get_version)         # flagged
export TOKEN=$(fetch_token)
```

`local`, `export`, `declare`, and `readonly` are commands that return 0, so a
failure inside `$(...)` is invisible — including under `set -e`.

```bash
local ver
ver="$(get_version)" || return 1

export TOKEN
TOKEN="$(fetch_token)" || die "token fetch failed"
```

## SC2164 — `cd` without a guard

```bash
cd /some/dir                     # flagged
rm -rf ./*                       # runs in the WRONG directory if cd failed
```

```bash
cd /some/dir || exit 1
# or, for a scoped change:
( cd /some/dir && rm -rf ./* )
```

## SC2181 — Checking `$?` indirectly

```bash
grep -q pattern file             # flagged pattern below
if [ $? -ne 0 ]; then ...
```

`$?` is fragile — any intervening command overwrites it.

```bash
if ! grep -q pattern file; then ...
```

## SC2115 — Dangerous `rm` with a possibly empty variable

```bash
rm -rf "$dir/$sub"               # flagged; becomes `rm -rf /` if both are empty
```

```bash
rm -rf -- "${dir:?dir is unset}/${sub:?sub is unset}"
```

The `:?` form aborts with a message instead of deleting the filesystem root.
Any destructive command built from variables deserves this treatment.

## SC2068 — Unquoted array or `$@`

```bash
process $@                       # flagged
copy ${files[@]}
```

```bash
process "$@"
copy "${files[@]}"
```

`"$@"` preserves argument boundaries; `$@` re-splits them.

## SC2012 — Parsing `ls`

```bash
count=$(ls | wc -l)              # flagged
for f in $(ls *.txt); do ...
```

`ls` output is for humans; filenames may contain spaces and newlines.

```bash
count=$(find . -maxdepth 1 -type f | wc -l)
for f in *.txt; do [[ -e "$f" ]] || continue; ...; done
```

## SC2059 — Variable in a printf format

```bash
printf "$msg\n"                  # flagged
```

If `$msg` contains `%s` or `%d`, `printf` consumes arguments that are not
there — a format-string bug, and a security issue with untrusted input.

```bash
printf '%s\n' "$msg"
```

## SC1090 / SC1091 — Cannot follow a source

```bash
source "$CONFIG_DIR/lib.sh"      # SC1090: path is dynamic
source ./lib.sh                  # SC1091: file not found at analysis time
```

Tell shellcheck where to look:

```bash
# shellcheck source=lib/common.sh
source "$LIB_DIR/common.sh"

# shellcheck source-path=SCRIPTDIR/lib
```

Or set `source-path` and `external-sources=true` in `.shellcheckrc`. Pass `-x`
so it follows them.

## SC2103 / SC2038 / SC2044 — `cd` and `find` in loops

```bash
for d in */; do cd "$d"; make; cd ..; done       # SC2103
find . -name '*.sh' | xargs grep foo             # SC2038: breaks on spaces
for f in $(find . -name '*.sh'); do ...          # SC2044: same
```

```bash
for d in */; do ( cd "$d" && make ); done        # subshell scopes the cd
find . -name '*.sh' -print0 | xargs -0 grep foo
find . -name '*.sh' -exec grep foo {} +
while IFS= read -r -d '' f; do ...; done < <(find . -name '*.sh' -print0)
```

## SC2216 / SC2217 — Piping to a command that ignores stdin

```bash
echo "data" | rm file            # SC2216
```

Usually a misunderstanding of what the command reads. Use a file argument, or
`xargs` to convert stdin into arguments.

## SC2094 — Reading and writing the same file

```bash
sort file > file                 # truncates before sort reads it
```

```bash
tmp="$(mktemp)"
sort file > "$tmp" && mv -- "$tmp" file
sort -o file file                # sort supports this specifically
```

## SC2178 / SC2128 — Array used as a scalar

```bash
files=(a b c)
echo $files                      # SC2128: yields only "a"
```

```bash
echo "${files[@]}"               # all elements
echo "${files[0]}"               # explicitly the first
```

## SC2317 — Unreachable command

Commonly a false positive with trap handlers, which are invoked indirectly:

```bash
# shellcheck disable=SC2317  # invoked via `trap`
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT
```

## SC2312 — Command substitution exit code ignored

Only active with `-o all`. Strict, and often noisy:

```bash
echo "Files: $(count_files)"     # a failure in count_files is invisible
```

```bash
files="$(count_files)" || die "count failed"
echo "Files: ${files}"
```

## SC2015 — `A && B || C` is not if-then-else

```bash
[[ -f "$f" ]] && process "$f" || echo "missing"
```

If `process` fails, `echo "missing"` also runs — the message is then wrong.

```bash
if [[ -f "$f" ]]; then
    process "$f"
else
    echo "missing"
fi
```

The idiom is only safe when `B` cannot fail.

## Checking a fix

Re-run shellcheck after every suppression. A directive placed above a comment,
a blank line, or the wrong construct is silently ignored, so an unverified
`disable` often means the warning is still live:

```bash
shellcheck -x -S style script.sh
```
