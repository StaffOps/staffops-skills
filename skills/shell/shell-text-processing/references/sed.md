# sed Reference

`sed` applies editing commands to a stream, one line at a time. It is ideal
for stateless substitutions and line selection; anything requiring memory
across lines is usually clearer in `awk`.

## Command anatomy

```
[address[,address]] command [arguments]
```

Without an address, the command applies to every line.

## Addresses

| Address | Selects |
| --- | --- |
| `5` | Line 5 |
| `$` | Last line |
| `/regex/` | Lines matching the regex |
| `5,10` | Lines 5 through 10 |
| `5,$` | Line 5 to the end |
| `/start/,/end/` | From the first `start` to the next `end` |
| `0~3` | Every 3rd line (GNU) |
| `5,+2` | Line 5 and the 2 after it (GNU) |
| `/regex/!` | Lines **not** matching (negation) |

```bash
sed -n '10,20p' file          # print lines 10-20
sed '1d' file                 # delete the header
sed '$d' file                 # delete the last line
sed '/^#/d' file              # delete comment lines
sed '/^$/d' file              # delete blank lines
sed '/^#/!s/a/b/' file        # substitute only on non-comment lines
```

`-n` suppresses the automatic printing of each line, which is why `-n` and `p`
are almost always used together.

## Substitution

```
s/regex/replacement/flags
```

| Flag | Effect |
| --- | --- |
| `g` | Replace all occurrences on the line, not just the first |
| `N` | Replace only the Nth occurrence |
| `Ng` | Replace the Nth and every one after |
| `i` | Case-insensitive (GNU and modern BSD) |
| `p` | Print the line if a substitution happened |
| `w file` | Write changed lines to `file` |
| `e` | Execute the result as a shell command (GNU; dangerous) |

```bash
sed 's/foo/bar/'          # first per line
sed 's/foo/bar/g'         # all
sed 's/foo/bar/2'         # only the second
sed -n 's/foo/bar/p'      # print only changed lines
```

Any character works as the delimiter — use one absent from the data instead of
escaping:

```bash
sed 's|/usr/local/bin|/opt/bin|g'
sed 's#http://#https://#'
```

### Replacement specials

| Token | Meaning |
| --- | --- |
| `&` | The entire match |
| `\1`..`\9` | Capture groups |
| `\n`, `\t` | Newline, tab (GNU) |
| `\U`, `\L` | Uppercase / lowercase the rest (GNU) |
| `\u`, `\l` | Uppercase / lowercase the next character (GNU) |

```bash
sed 's/[0-9]\+/[&]/g'                 # wrap numbers in brackets
sed -E 's/([a-z]+)@([a-z.]+)/\2:\1/'  # swap around the @
sed -E 's/\b(\w)/\u\1/g'              # capitalize each word (GNU)
```

## Basic vs extended regex

BRE (default) requires backslashes before `+`, `?`, `{`, `(`, `|`. ERE (`-E`)
does not. Prefer `-E` — it is supported by both GNU and BSD and is far more
readable.

```bash
sed 's/[0-9]\{3\}/N/'      # BRE
sed -E 's/[0-9]{3}/N/'     # ERE -- clearer
sed -E 's/(cat|dog)/pet/'  # alternation needs ERE (or \| in BRE)
```

`sed -r` is the GNU spelling of `-E`; use `-E` for portability.

## Multiple commands

```bash
sed -e 's/a/b/' -e 's/c/d/' file
sed 's/a/b/; s/c/d/' file
sed -f script.sed file

# Braces group commands under one address.
sed '/BEGIN/,/END/ { s/foo/bar/; s/baz/qux/ }' file
```

## Other commands

| Command | Effect |
| --- | --- |
| `p` | Print the pattern space |
| `d` | Delete; start the next cycle |
| `a text` | Append `text` after the line |
| `i text` | Insert `text` before the line |
| `c text` | Replace the line with `text` |
| `y/abc/xyz/` | Transliterate characters (like `tr`) |
| `q` | Quit (with an optional exit code, GNU) |
| `r file` | Read and insert a file's contents |
| `=` | Print the line number |

```bash
sed '2i\
new line here' file              # portable insert (note the backslash-newline)

sed '/^\[main\]/a\
key = value' config.ini

sed '100q' bigfile               # stop after 100 lines -- faster than head on huge files
sed -n '/pattern/{=;p}' file     # print line numbers with matches
```

GNU accepts the shorter `sed '2i new line'`; BSD requires the backslash-newline
form above.

## Hold space

`sed` has two buffers: the pattern space (the current line) and the hold space
(persistent across lines). This is what enables multi-line work — though
`awk` is usually clearer for the same task.

| Command | Effect |
| --- | --- |
| `h` | Copy pattern space → hold space |
| `H` | Append pattern space → hold space |
| `g` | Copy hold space → pattern space |
| `G` | Append hold space → pattern space |
| `x` | Exchange the two |
| `n` | Read the next line into the pattern space |
| `N` | Append the next line to the pattern space |

```bash
sed '1!G;h;$!d' file          # reverse a file (the `tac` equivalent)
sed -e :a -e '$!N;s/\n/ /;ta' # join all lines with spaces
sed '$!N;s/\n/\t/'            # join line pairs with a tab
sed -n '/start/,/end/{H};${x;s/\n/ /g;p}'   # collect a range into one line
```

These are classic but hard to read. Reach for `awk` or Python once hold-space
logic appears.

## In-place editing

The main portability trap:

```bash
sed -i 's/a/b/' f        # GNU only
sed -i '' 's/a/b/' f     # BSD only
sed -i.bak 's/a/b/' f    # BOTH -- always use this
```

To edit in place without leaving backups, portably:

```bash
tmp="$(mktemp)"
sed 's/a/b/' file > "$tmp" && mv -- "$tmp" file
```

`sed -i` is not atomic on either platform — it writes a temp file and renames,
so a crash mid-edit can leave the original intact but the backup missing.

## Escaping a variable into a pattern

Shell variables interpolated into a `sed` script are interpreted as regex and
can also break the delimiter. Escape them:

```bash
escape_re() { printf '%s' "$1" | sed 's/[][\.*^$/]/\\&/g'; }
escape_rep() { printf '%s' "$1" | sed 's/[\/&]/\\&/g'; }

sed "s/$(escape_re "$find")/$(escape_rep "$replace")/g" file
```

For literal (non-regex) replacement, `awk` with `-v` and `index()`/`substr()`,
or a small Python script, avoids the escaping problem entirely.

## Common recipes

```bash
# Strip leading/trailing whitespace.
sed -E 's/^[[:space:]]+|[[:space:]]+$//g'

# Remove blank lines and comments.
sed -E '/^[[:space:]]*(#|$)/d'

# Strip ANSI color codes.
sed -E 's/\x1b\[[0-9;]*m//g'

# Windows -> Unix line endings.
sed 's/\r$//'

# Extract a value from key=value.
sed -n 's/^KEY=//p' file

# Print between two markers, exclusive.
sed -n '/BEGIN/,/END/{//!p}'

# Double-space a file.
sed G

# Number lines (like cat -n).
sed = file | sed 'N;s/\n/\t/'

# Delete the last N lines (GNU).
sed -n -e :a -e '1,3!{P;N;D};N;ba'

# Replace only on lines matching another pattern.
sed '/^prod/s/debug/info/'
```

## When to stop using sed

Move to `awk` or Python when you need:

- State across lines (counters, accumulators, lookups)
- Field-aware logic rather than character positions
- Arithmetic
- Structured formats — never regex-parse JSON, XML, YAML, or CSV with
  embedded delimiters
- Anything requiring hold-space gymnastics to express
