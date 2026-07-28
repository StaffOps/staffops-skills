# awk Reference

`awk` reads input record by record (by default, line by line), splits each
record into fields, and runs `pattern { action }` blocks against it.

## Program structure

```awk
BEGIN { ... }        # once, before any input
pattern { action }   # per record
/regex/ { action }   # per record matching the regex
END { ... }          # once, after all input
```

Omitting the pattern runs the action on every record. Omitting the action
defaults to `print $0`.

```bash
awk 'NR > 1'                    # print every line except the header
awk '{ print $1 }'              # print field 1 of every line
awk '/error/'                   # print lines containing "error"
awk 'BEGIN { FS=":" } { print $1 }'
```

## Built-in variables

| Variable | Meaning | Default |
| --- | --- | --- |
| `$0` | Whole record | |
| `$1`..`$NF` | Fields | |
| `NF` | Field count in this record | |
| `NR` | Record number across all input | |
| `FNR` | Record number within the current file | |
| `FILENAME` | Current input file | |
| `FS` | Input field separator | whitespace |
| `OFS` | Output field separator | space |
| `RS` | Input record separator | newline |
| `ORS` | Output record separator | newline |
| `SUBSEP` | Multi-dimensional array key separator | `\034` |

Setting `FS` on the command line is usually clearer than in `BEGIN`:

```bash
awk -F: '{ print $1 }' /etc/passwd
awk -F'\t' -v OFS='\t' '{ $3 = "x"; print }' data.tsv
awk -F' *\\| *' '{ print $2 }'        # regex FS: pipe with optional spaces
```

Assigning to any field rebuilds `$0` using `OFS` — this is how you convert
delimiters:

```bash
awk -F, -v OFS='\t' '{ $1 = $1; print }' in.csv     # CSV -> TSV
```

The `$1 = $1` looks redundant but is what triggers the rebuild.

## Patterns

```bash
awk '$3 > 100'                      # numeric comparison
awk '$1 == "GET"'                   # string equality
awk '/error/ && !/timeout/'         # regex combination
awk '$0 ~ /^2026-/'                 # explicit match
awk '$2 !~ /^(GET|HEAD)$/'          # negated match
awk 'NR >= 10 && NR <= 20'          # line range by number
awk '/START/,/END/'                 # range pattern: from match to match
```

Comparison is numeric when both sides look numeric, string otherwise. Force
one explicitly when it matters:

```bash
awk '$1 + 0 > 100'         # force numeric
awk '$1 "" == "007"'       # force string
```

## Arrays

All arrays are associative; indices are strings.

```bash
# Frequency count.
awk '{ count[$1]++ } END { for (k in count) print count[k], k }'

# Sum grouped by key.
awk '{ total[$1] += $2 } END { for (k in total) printf "%s %.2f\n", k, total[k] }'

# Deduplicate, preserving first-seen order.
awk '!seen[$0]++'

# Two-key grouping via SUBSEP.
awk '{ m[$1,$2]++ } END { for (k in m) { split(k, p, SUBSEP); print p[1], p[2], m[k] } }'

# Membership test without creating the element.
awk '"key" in arr { ... }'
```

`!seen[$0]++` is the canonical dedupe idiom: the first time a line is seen the
value is 0 (falsy → `!0` is true → print), and the post-increment makes every
later occurrence truthy.

## String functions

| Function | Purpose |
| --- | --- |
| `length(s)` | Length of `s` (or `$0` if omitted) |
| `substr(s, i [, n])` | Substring from position `i` (1-based) |
| `index(s, t)` | Position of `t` in `s`, or 0 |
| `split(s, arr [, fs])` | Split into `arr`, returns element count |
| `sub(re, rep [, target])` | Replace first match; returns 1 or 0 |
| `gsub(re, rep [, target])` | Replace all; returns count |
| `match(s, re)` | Sets `RSTART` and `RLENGTH`; returns position |
| `sprintf(fmt, ...)` | Format into a string |
| `tolower(s)` / `toupper(s)` | Case conversion |

```bash
# Extract with match/RSTART/RLENGTH.
awk '{ if (match($0, /[0-9]+ms/)) print substr($0, RSTART, RLENGTH) }'

# Split a path.
awk '{ n = split($1, parts, "/"); print parts[n] }'

# Strip surrounding quotes.
awk '{ gsub(/^"|"$/, "", $1); print $1 }'
```

In `sub`/`gsub` replacements, `&` means "the whole match". Escape it as `\\&`
to insert a literal ampersand.

## Numeric formatting

```bash
awk '{ printf "%-20s %8.2f %5d%%\n", $1, $2, $3 }'
awk '{ printf "%s\n", $1 / 1024 / 1024 }'          # bytes -> MiB
awk 'BEGIN { printf "%.3f\n", 22/7 }'
```

`awk` is often the simplest way to do floating-point arithmetic from a shell
script, since Bash has integers only:

```bash
pct="$(awk -v a="$part" -v b="$total" 'BEGIN { printf "%.1f", a/b*100 }')"
```

## Passing values in

```bash
awk -v threshold="$t" -v name="$n" '$3 > threshold && $1 == name' file
```

`-v` values are set before `BEGIN` runs. To read a value only for a specific
input file, place `var=value` between filenames.

Never build the program text by interpolating shell variables — quoting breaks
and it is an injection vector:

```bash
awk -v p="$pattern" '$0 ~ p'      # correct
awk "\$0 ~ /$pattern/"            # fragile
```

## Multiple files

```bash
# FNR == NR is true only while reading the FIRST file.
awk 'FNR == NR { keys[$1]; next } $1 in keys' ids.txt data.txt

# Print each file's line count.
awk 'END { print FILENAME, FNR }' a.txt b.txt      # only the last file
awk 'FNR == 1 && NR > 1 { print prev, c; c = 0 } { c++; prev = FILENAME }' *.txt
```

The `FNR == NR { ...; next }` idiom is the standard way to load a lookup table
from the first file and then process the second.

## Control flow

```awk
{
    if ($3 > 100) high++
    else if ($3 > 50) mid++
    else low++

    for (i = 1; i <= NF; i++) sum += $i
    for (key in arr) print key, arr[key]

    while ((getline line < "other.txt") > 0) n++

    if ($1 == "skip") next          # go to the next record
    if ($1 == "stop") exit 1        # stop; END still runs
}
```

## User-defined functions

```awk
function human(bytes,   units, i) {      # locals go after the real params
    split("B KB MB GB TB", units, " ")
    for (i = 1; bytes >= 1024 && i < 5; i++) bytes /= 1024
    return sprintf("%.1f%s", bytes, units[i])
}
{ print human($1) }
```

The extra-spaces convention marks parameters used as local variables — `awk`
has no other way to declare them, and undeclared names are global.

## Portability

macOS ships the original BWK `awk`; Linux typically `gawk`; Alpine `mawk` or
BusyBox. Stick to POSIX unless you require `gawk`:

| Feature | Availability |
| --- | --- |
| `gensub()`, `asort()`, `asorti()` | gawk only |
| `strftime()`, `systime()`, `mktime()` | gawk, mawk |
| `length(array)` | gawk |
| `RS` as a regular expression | gawk |
| `IGNORECASE` | gawk |
| `sub`, `gsub`, `match`, `split`, `substr` | Everywhere |

```bash
command -v gawk >/dev/null || die "gawk required"
```

## Recipes

```bash
# Sum a column.
awk '{ s += $1 } END { print s }'

# Average, guarding against no input.
awk '{ s += $1; n++ } END { print (n ? s/n : 0) }'

# Max with the line that produced it.
awk '$1 > max { max = $1; line = $0 } END { print max, line }'

# Median (requires sorted numeric input).
sort -n | awk '{ v[NR] = $1 } END { print (NR % 2) ? v[(NR+1)/2] : (v[NR/2] + v[NR/2+1]) / 2 }'

# Percentile.
sort -n | awk '{ v[NR] = $1 } END { print v[int(NR * 0.95)] }'

# Column totals for every numeric column.
awk '{ for (i = 1; i <= NF; i++) s[i] += $i } END { for (i = 1; i <= NF; i++) printf "%s%s", s[i], (i < NF ? OFS : ORS) }'

# Transpose.
awk '{ for (i = 1; i <= NF; i++) a[i, NR] = $i } END { for (i = 1; i <= NF; i++) { for (j = 1; j <= NR; j++) printf "%s%s", a[i, j], (j < NR ? OFS : ORS) } }'

# Print the line before and after a match.
awk '/pattern/ { print prev; print; getline; print } { prev = $0 }'

# Records separated by blank lines (paragraph mode).
awk 'BEGIN { RS = "" } { print NR ": " $1 }'
```
