# GNU vs BSD Portability

Scripts written on Linux routinely break on macOS and Alpine. Linux uses GNU
coreutils; macOS uses BSD utilities; Alpine uses BusyBox, which implements a
reduced subset of the GNU behavior.

## The high-frequency breakages

### `sed -i`

The single most common portability bug.

```bash
sed -i 's/a/b/' f        # GNU: OK.    BSD: 's/a/b/' is read as the backup suffix
sed -i '' 's/a/b/' f     # BSD: OK.    GNU: '' is read as the script -> error
sed -i.bak 's/a/b/' f    # Both: OK
```

Always use `-i.bak`. To avoid leaving backups behind in a portable way, skip
`-i` entirely:

```bash
tmp="$(mktemp)"
sed 's/a/b/' f > "$tmp" && mv -- "$tmp" f
```

### `sed -E` vs `-r`

`-E` (extended regex) works on both modern GNU and BSD. `-r` is GNU-only. Use
`-E`.

### `date`

Completely different arithmetic syntax:

```bash
date -d '1 hour ago'              # GNU
date -v-1H                        # BSD
date -d '@1700000000'             # GNU: epoch -> human
date -r 1700000000                # BSD: same
date +%s                          # both
```

Portable approaches: use `date +%s` and do arithmetic in the shell, or invoke
Python for anything non-trivial.

```bash
one_hour_ago=$(( $(date +%s) - 3600 ))
```

### `readlink -f`

GNU resolves the full path; BSD `readlink` has no `-f`.

```bash
readlink -f "$path"          # GNU only
realpath "$path"             # GNU coreutils 8.15+, and BSD via `brew install coreutils`

# Portable:
abspath() { cd -- "$(dirname -- "$1")" && printf '%s/%s\n' "$PWD" "${1##*/}"; }
```

### `stat`

Format strings are entirely incompatible:

```bash
stat -c '%s' f           # GNU: size in bytes
stat -f '%z' f           # BSD: size in bytes
stat -c '%Y' f           # GNU: mtime epoch
stat -f '%m' f           # BSD: mtime epoch
```

Portable size: `wc -c < f`. Portable mtime comparison: `[[ a -nt b ]]`.

### `find`

```bash
find . -printf '%p\n'         # GNU only
find . -regextype posix-egrep # GNU only
find . -maxdepth 1            # both (but must precede other expressions on BSD)
find . -name '*.log' -delete  # both
find . -exec cmd {} +         # both -- prefer over \; for performance
```

`-print0` and `xargs -0` exist on both and are the correct way to handle
arbitrary filenames.

### `xargs`

```bash
xargs -r cmd        # GNU: skip if input is empty. BSD: no -r (it is the default)
xargs -0 cmd        # both
xargs -I{} cmd {}   # both
xargs -P4 cmd       # both (parallel)
```

Guard portably by testing for input rather than relying on `-r`.

### `grep`

```bash
grep -P 'perl-regex'     # GNU only (and not always compiled in)
grep -E 'ere'            # both -- prefer this
grep -o                  # both
grep --include=          # both (GNU and modern BSD)
```

BusyBox `grep` lacks `-P` and some long options entirely.

### `sort`

```bash
sort -h        # GNU only (human-readable sizes)
sort -V        # GNU only (version sort)
sort -n        # both
sort -k2,2     # both
```

### `awk`

macOS ships the original `awk` (BWK), Linux usually `gawk`, Alpine `mawk` or
BusyBox `awk`. Only POSIX features are safe:

| Feature | Portable? |
| --- | --- |
| `gensub()` | No — gawk only |
| `asort()` / `asorti()` | No — gawk only |
| `strftime()` / `systime()` | No — gawk and mawk |
| `length(array)` | No — gawk |
| `RS` as a regex | No — gawk |
| `sub()` / `gsub()` / `match()` | Yes |
| `split()` / `substr()` / `index()` | Yes |
| Associative arrays | Yes |
| `printf` | Yes |

If a script needs gawk features, require it explicitly:

```bash
command -v gawk >/dev/null || die "gawk is required"
```

### Other differences

| Task | GNU | BSD | Portable |
| --- | --- | --- | --- |
| Base64 decode | `base64 -d` | `base64 -D` | `openssl base64 -d` |
| `echo -e` | Interprets escapes | Varies | `printf` |
| `mktemp` template | `mktemp -d` works bare | Needs a template on older BSD | `mktemp -d "${TMPDIR:-/tmp}/x.XXXXXX"` |
| `cp` preserve | `cp -a` | `cp -pR` | `cp -pR` |
| `mv` replace symlink | `mv -T` | not supported | unlink then `mv` |
| `timeout` | coreutils | `brew install coreutils` (`gtimeout`) | — |
| `sed` word boundary | `\b`, `\<` | `[[:<:]]` | `awk` |
| MD5 | `md5sum` | `md5 -q` | `openssl md5` |

## Detection strategies

**Prefer feature detection over OS detection:**

```bash
if sed --version >/dev/null 2>&1; then
    SED_INPLACE=(-i)          # GNU
else
    SED_INPLACE=(-i '')       # BSD
fi
sed "${SED_INPLACE[@]}" 's/a/b/' file
```

**Or normalize by requiring GNU tools**, which is what most CI images do:

```bash
# macOS: brew install coreutils gnu-sed findutils gawk
export PATH="/opt/homebrew/opt/coreutils/libexec/gnubin:$PATH"
export PATH="/opt/homebrew/opt/gnu-sed/libexec/gnubin:$PATH"
```

**Or sidestep the whole issue**: anything needing `date` arithmetic, path
resolution, or structured parsing is usually better written in Python, which
behaves identically everywhere.

## BusyBox specifics

Alpine-based containers use BusyBox, where most utilities are minimal
implementations:

- No `-P` in `grep`, no `-h`/`-V` in `sort`
- `awk` lacks most gawk functions
- `find` lacks `-printf`
- No `column`, no `pv`, often no `bash` at all (`/bin/sh` is `ash`)

For scripts that must run in Alpine, either target POSIX `sh` strictly, or
install what you need:

```dockerfile
RUN apk add --no-cache bash coreutils gawk sed grep findutils
```

Testing in the actual target image is the only reliable verification —
`shellcheck --shell=sh` catches bashisms but not missing utility flags.
