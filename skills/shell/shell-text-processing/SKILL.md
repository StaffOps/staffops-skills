---
name: shell-text-processing
description: "Transform text with awk, sed, grep, sort and jq."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [awk, sed, grep, jq, text, parsing, logs]
    category: shell
    related_skills: [bash-scripting, shell-cli-design]
---
# Shell Text Processing

Choosing and composing the classic text tools: `grep` to select, `sed` to
edit, `awk` to compute, `sort`/`uniq` to aggregate, `jq` for JSON. Emphasis on
picking the right one and on the GNU/BSD differences that break scripts when
they move between Linux and macOS.

## When to Use

Use when parsing logs, reshaping CSV or TSV, extracting fields from command
output, writing one-liners that will end up in a script, or replacing a slow
per-line Bash loop with a single-pass tool.

## Choosing the tool

| Need | Tool | Why not the others |
| --- | --- | --- |
| Select matching lines | `grep` | Fastest; `awk`/`sed` are overkill |
| Substitute text | `sed` | Purpose-built for `s///` |
| Field-aware logic, arithmetic, grouping | `awk` | The only one with variables and arrays |
| Count and aggregate | `sort` + `uniq -c` | Simple; `awk` for anything conditional |
| JSON | `jq` | Never regex-parse JSON |
| YAML | `yq` | Same reason |
| Fixed-width columns | `cut -c` | `awk` splits on whitespace, not columns |
| Column alignment for humans | `column -t` | Display only |

Rule of thumb: if the task needs to *remember* anything between lines, it is
an `awk` job. If it is a stateless per-line edit, `sed`. If it is only
selection, `grep`.

## grep

```bash
grep -F 'literal'         # fixed string; fastest, no regex surprises
grep -E 'a|b'             # extended regex (no backslash-escaped groups)
grep -P '\d+(?=ms)'       # Perl regex: lookahead, \d, \b  (GNU only)
grep -o 'pattern'         # print only the match, one per line
grep -c pattern           # count matching LINES (not matches)
grep -v pattern           # invert
grep -i pattern           # case-insensitive
grep -w word              # whole word
grep -r --include='*.log' # recursive, filtered by glob
grep -A3 -B2 pattern      # 3 lines after, 2 before
grep -q pattern           # quiet; exit status only -- ideal for `if`
grep -m1 pattern          # stop at the first match
```

Use `-F` whenever the pattern is a literal, especially when it comes from a
variable — otherwise a `.` or `*` in the data is interpreted as a regex:

```bash
grep -F -- "$user_input" file     # `--` also guards against a leading dash
```

`grep -c` counts *lines*, not occurrences. For occurrences: `grep -o pat | wc -l`.

## sed

```bash
sed 's/old/new/'          # first occurrence per line
sed 's/old/new/g'         # all occurrences
sed 's/old/new/2'         # only the 2nd occurrence
sed -E 's/([0-9]+)/<\1>/g'  # extended regex + capture group
sed -n '5p'               # print line 5 only (-n suppresses default output)
sed -n '10,20p'           # lines 10-20
sed '/pattern/d'          # delete matching lines
sed '1d;$d'               # delete first and last line
sed 's/#.*//' file        # strip comments
sed -i.bak 's/a/b/' file  # edit in place, keeping file.bak
```

Any character can be the delimiter, which avoids escaping paths:

```bash
sed 's|/usr/local|/opt|g'      # much clearer than escaping every slash
```

**In-place editing is the main portability trap.** GNU `sed -i` takes an
optional suffix; BSD/macOS `sed -i` *requires* one:

```bash
sed -i 's/a/b/' f        # GNU: fine.  BSD: consumes 's/a/b/' as the suffix
sed -i '' 's/a/b/' f     # BSD: fine.  GNU: treats '' as the script
sed -i.bak 's/a/b/' f    # works on BOTH -- always use this form
```

For scripts that must run on both without leaving `.bak` files, write to a
temp file and `mv`, or use `perl -i -pe`.

## awk

`awk` is a small programming language. The structure is `pattern { action }`,
applied to every line.

```bash
awk '{ print $2 }'                   # second whitespace-separated field
awk -F: '{ print $1 }' /etc/passwd   # colon-delimited
awk -F'\t' -v OFS='\t' '{ ... }'     # tab in, tab out
awk 'NR > 1'                         # skip a header (no action = print)
awk 'NF'                             # drop blank lines
awk '$3 > 100'                       # numeric filter
awk '/error/ && !/ignore/'           # combined patterns
awk '{ sum += $1 } END { print sum }'
awk '{ print $NF }'                  # last field
awk 'END { print NR }'               # line count
```

Built-in variables worth knowing:

| Variable | Meaning |
| --- | --- |
| `$0` | The whole line |
| `$1`..`$NF` | Fields |
| `NF` | Number of fields on this line |
| `NR` | Record (line) number overall |
| `FNR` | Line number within the current file |
| `FS` / `OFS` | Input / output field separator |
| `RS` / `ORS` | Input / output record separator |

Grouping with associative arrays is where `awk` earns its place:

```bash
# Sum bytes per status code from an access log.
awk '{ bytes[$9] += $10 } END { for (s in bytes) printf "%s %d\n", s, bytes[s] }'

# Count distinct values, sorted by frequency.
awk '{ c[$1]++ } END { for (k in c) print c[k], k }' | sort -rn

# p95 of field 7.
awk '{ v[NR] = $7 } END { n = asort(v); print v[int(n * 0.95)] }'   # gawk only
```

Pass shell variables in with `-v`; never interpolate them into the program
text, which breaks on quotes and is an injection risk:

```bash
threshold=100
awk -v t="$threshold" '$3 > t' file      # correct
awk "\$3 > $threshold" file              # fragile
```

`references/awk.md` covers functions, multi-file processing, `getline`, and
the gawk-only extensions.

## sort, uniq, and friends

```bash
sort                      # lexical
sort -n                   # numeric
sort -h                   # human sizes (2K, 3M)  -- GNU only
sort -k2,2 -k1,1r         # by field 2, then field 1 descending
sort -t: -k3 -n           # custom delimiter
sort -u                   # unique (no separate uniq needed)
sort -V                   # version sort (1.10 after 1.9)  -- GNU only
uniq -c                   # count consecutive duplicates -- REQUIRES sort first
uniq -d                   # only duplicated lines
paste -d, a.txt b.txt     # join files side by side
join -t, -1 1 -2 1 a b    # relational join on a sorted key
comm -13 a b              # lines only in b (both must be sorted)
tr -d '\r'                # strip carriage returns
tr -s ' '                 # squeeze repeated spaces
```

`uniq` only collapses **adjacent** duplicates. `sort | uniq -c | sort -rn` is
the canonical frequency count.

## jq

```bash
jq '.field'                       # extract
jq -r '.field'                    # raw output (no surrounding quotes)
jq '.items[]'                     # iterate an array
jq '.items[] | select(.age > 30)' # filter
jq -r '.items[] | [.id, .name] | @tsv'   # to TSV for downstream tools
jq 'map(.value) | add'            # sum
jq -s 'group_by(.host) | map({host: .[0].host, n: length})'
jq --arg v "$shell_var" '.f = $v' # safe interpolation
jq -e '.ok'                       # exit non-zero if false/null -- for `if`
```

`-r` matters constantly: without it every string is quoted, which breaks
comparisons and downstream parsing. `--arg` is the only correct way to pass a
shell value in.

For newline-delimited JSON, `jq` reads a stream naturally:

```bash
kubectl get pods -o json | jq -r '.items[] | "\(.metadata.name) \(.status.phase)"'
```

## Composing a pipeline

Build left to right, checking the output at each stage before adding the next.
A worked example — top 10 client IPs returning 5xx:

```bash
awk '$9 ~ /^5/ { print $1 }' access.log \
  | sort \
  | uniq -c \
  | sort -rn \
  | head -10
```

The same logic in one `awk` pass is faster on large files because it avoids
sorting the full set:

```bash
awk '$9 ~ /^5/ { c[$1]++ } END { for (ip in c) print c[ip], ip }' access.log \
  | sort -rn | head -10
```

## Pitfalls

- **Parsing `ls`** — filenames may contain spaces and newlines. Use `find
  -print0` with `xargs -0`, or a glob.
- **`grep` on a variable without `-F`** — regex metacharacters in the data
  change the meaning.
- **`uniq` without `sort`** — silently misses non-adjacent duplicates.
- **`sed -i` without a suffix** — breaks on BSD/macOS. Always `-i.bak`.
- **Interpolating shell variables into `awk`/`jq` programs** — use `-v` and
  `--arg`.
- **`grep -P` in portable scripts** — GNU-only. Use `-E` or `awk`.
- **Locale-dependent sorting** — `sort` order changes with `LC_ALL`. Pin
  `LC_ALL=C` for byte order and reproducible results.
- **Windows line endings** — a trailing `\r` breaks comparisons invisibly.
  `tr -d '\r'` or `dos2unix` first.

## Verification

```bash
LC_ALL=C sort ...             # reproducible ordering
echo "$input" | cmd | head    # inspect each stage while building
cmd | od -c | head            # reveal invisible characters (\r, \t, NUL)
```

## Reference

- `references/awk.md` — language reference, arrays, functions, gawk extensions
- `references/sed.md` — addressing, hold space, multi-line editing
- `references/gnu-vs-bsd.md` — portability differences across all these tools
- `examples/log-report.sh` — multi-stage report from a raw access log

## When NOT to use

- **Structured data** (JSON, YAML, XML) with nested objects — use jq/yq/xmlstarlet, not regex.
- **Binary file manipulation** — use dedicated tools (xxd, file, binutils).
- **Complex data pipelines** where Python/pandas is clearer and more maintainable.


## Decision tree

```
What operation do you need?
├── Filter lines (keep/remove matching)?
│   ├── Fixed string → grep -F "pattern"
│   ├── Regex → grep -E "pattern"
│   └── Inverted (exclude) → grep -v "pattern"
├── Transform text (substitute/reformat)?
│   ├── Simple substitution → sed 's/old/new/g'
│   ├── Field extraction → awk '{print $N}' or cut -d: -f2
│   └── Multi-line / complex → awk with BEGIN/END blocks
├── Aggregate (count/sum/unique)?
│   ├── Count occurrences → sort | uniq -c | sort -rn
│   ├── Sum a column → awk '{s+=$1} END{print s}'
│   └── Top-N → sort | uniq -c | sort -rn | head -N
├── Join / correlate two files?
│   ├── Same key field → join (requires sorted input)
│   └── Side-by-side → paste file1 file2
└── Structured data (JSON/YAML/CSV)?
    ├── JSON → jq '.field'
    ├── YAML → yq '.field'
    └── CSV → awk -F, or csvkit
```

## Related skills

- [linux-command-line](../linux/linux-command-line/SKILL.md) — pipes, redirection, find/xargs.
- [bash-scripting](../shell/bash-scripting/SKILL.md) — integrating text processing into scripts.
- [log-analysis](../troubleshooting/log-analysis/SKILL.md) — applying text tools to log files.
- [shell-testing-linting](../shell/shell-testing-linting/SKILL.md) — validating text pipelines.
