# Parameter Expansion Reference

Every form below is a Bash builtin — no subshell, no external process. For
anything these cover, they are faster and safer than `sed`, `cut`, `basename`,
or `dirname`.

Assume `path="/var/log/nginx/access.log.gz"` and `name="Report Draft"`.

## Defaults and assertions

| Form | Behavior |
| --- | --- |
| `${var:-default}` | Use `default` if `var` is unset **or empty** |
| `${var-default}` | Use `default` only if `var` is **unset** |
| `${var:=default}` | Same as `:-`, and assigns back to `var` |
| `${var:+alt}` | Use `alt` only if `var` is set and non-empty |
| `${var:?message}` | Print `message` to stderr and exit if unset or empty |

```bash
log_level="${LOG_LEVEL:-info}"        # tolerate unset
api_token="${API_TOKEN:?required}"    # fail fast with a message
flag="${verbose:+--verbose}"          # empty string when not verbose
```

`${var:?}` is the cleanest way to make a required environment variable
self-documenting: the error names the variable and the line.

## Removing prefixes and suffixes

`#` trims from the front, `%` from the back. Doubling the character makes the
match greedy.

| Form | Result |
| --- | --- |
| `${path#*/}` | `var/log/nginx/access.log.gz` (shortest leading match) |
| `${path##*/}` | `access.log.gz` — equivalent to `basename` |
| `${path%/*}` | `/var/log/nginx` — equivalent to `dirname` |
| `${path%%.*}` | `/var/log/nginx/access` |
| `${path%.gz}` | `/var/log/nginx/access.log` |

Mnemonic: on a US keyboard `#` is left of `$` and `%` is right of it, matching
the side each one trims.

```bash
file="${path##*/}"          # access.log.gz
dir="${path%/*}"            # /var/log/nginx
stem="${file%%.*}"          # access
ext="${file#*.}"            # log.gz
```

## Substitution

| Form | Result |
| --- | --- |
| `${path/log/LOG}` | Replaces the **first** `log` |
| `${path//log/LOG}` | Replaces **all** occurrences |
| `${path/#\/var/\/srv}` | Replaces only at the start (anchored) |
| `${path/%.gz/}` | Replaces only at the end (anchored) |
| `${path//\//_}` | `_var_log_nginx_access.log.gz` — `/` must be escaped |

```bash
slug="${name// /-}"          # Report-Draft
safe="${path//\//_}"         # flatten a path into a filename
```

## Substrings and length

| Form | Result |
| --- | --- |
| `${#path}` | `29` — length in characters |
| `${path:5}` | `log/nginx/access.log.gz` — from offset 5 |
| `${path:5:3}` | `log` — 3 characters from offset 5 |
| `${path: -2}` | `gz` — last 2 characters (**note the space**) |
| `${path:0:-3}` | `/var/log/nginx/access.log` — all but the last 3 |

The space in `${path: -2}` is required; `${path:-2}` is the default-value
operator and means something entirely different.

## Case conversion (Bash 4+)

| Form | Result for `name="Report Draft"` |
| --- | --- |
| `${name^}` | `Report Draft` (first char upper) |
| `${name^^}` | `REPORT DRAFT` |
| `${name,}` | `report Draft` (first char lower) |
| `${name,,}` | `report draft` |
| `${name~~}` | `rEPORT dRAFT` (swap case) |

```bash
# Case-insensitive comparison without `tr`.
if [[ "${answer,,}" == "yes" ]]; then ...
```

## Arrays

| Form | Meaning |
| --- | --- |
| `${arr[@]}` | All elements, one word each when quoted |
| `${arr[*]}` | All elements joined by the first char of `IFS` |
| `${#arr[@]}` | Number of elements |
| `${!arr[@]}` | All indices (or keys, for associative arrays) |
| `${arr[@]:1:2}` | Slice: 2 elements starting at index 1 |
| `${arr[@]/pat/rep}` | Substitution applied to every element |

```bash
files=(a.log b.log c.log)
printf '%s\n' "${files[@]%.log}"     # a b c — strip suffix from each
joined="$(IFS=,; echo "${files[*]}")" # a.log,b.log,c.log
```

## Indirection and quoting operators

| Form | Meaning |
| --- | --- |
| `${!var}` | Value of the variable *named* by `$var` |
| `${!prefix@}` | Names of all variables starting with `prefix` |
| `${var@Q}` | Value quoted so it can be reused as shell input |
| `${var@E}` | Value with backslash escapes expanded |
| `${var@A}` | An assignment statement that recreates `var` |

```bash
# Indirection: read a variable chosen at runtime.
env_name="PROD_URL"
url="${!env_name}"

# @Q makes logging safe and re-runnable.
printf 'running: %s\n' "${cmd[*]@Q}"
```

`${var@Q}` is the correct way to log a command line: the output can be pasted
back into a shell and will run identically, spaces and all.

## Common recipes

```bash
# Strip a trailing slash (idempotent).
dir="${dir%/}"

# Filename without any extension.
base="${file##*/}"; stem="${base%.*}"

# Trim leading and trailing whitespace (needs extglob).
shopt -s extglob
trimmed="${s##+([[:space:]])}"
trimmed="${trimmed%%+([[:space:]])}"

# Uppercase an environment variable name from a key.
var="CONFIG_${key^^}"
value="${!var:-}"

# Comma-separated list from an array.
csv="$(IFS=,; printf '%s' "${items[*]}")"
```

## What parameter expansion cannot do

Fall back to a real tool when you need:

- Regular expressions with capture groups — use `[[ $s =~ re ]]` and
  `BASH_REMATCH`, or `sed`/`awk`.
- Arithmetic on non-integers — Bash has no floats; use `awk` or Python.
- Multi-line transformations — use `awk`.
- JSON or YAML — use `jq` or `yq`; never parse them with expansions.
