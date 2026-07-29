# find and xargs Recipes

## Expression order

`find` evaluates left to right and **short-circuits**, so ordering changes
both correctness and speed:

```bash
find . -name '*.log' -size +10M      # implicit AND
find . -name '*.log' -o -name '*.txt'  # OR
find . ! -name '*.log'                 # NOT
find . \( -name '*.a' -o -name '*.b' \) -size +1M   # grouping needs escaping
```

Put cheap tests first — `-name` is a string compare, `-size` and `-newer`
require a `stat` syscall per file:

```bash
find . -name '*.log' -mtime +30      # fast: filters by name before stat
find . -mtime +30 -name '*.log'      # slower: stats everything
```

`-maxdepth` and `-mindepth` must come **before** other expressions on BSD and
should anyway, since they prune the walk:

```bash
find . -maxdepth 1 -name '*.conf'
```

## Selection

```bash
# By type
find . -type f          # regular file
find . -type d          # directory
find . -type l          # symlink
find . -xtype l         # BROKEN symlink (GNU)

# By time (days for -*time, minutes for -*min)
find . -mtime -1        # modified in the last 24h
find . -mtime +30       # modified more than 30 days ago
find . -mmin -15        # last 15 minutes
find . -newer ref       # newer than a reference file
find . -newermt '2026-01-01'          # newer than a date (GNU)
find . -newermt '-2 hours'            # relative (GNU)

# By size (c=bytes, k, M, G; bare number = 512-byte blocks)
find . -size +100M
find . -size -1k
find . -empty

# By ownership and permission
find . -user deploy
find . -group www-data
find . -nouser                  # orphaned by UID
find . -perm 644                # exactly
find . -perm -o+w               # at least world-writable
find . -perm /u+s               # any of these bits (setuid)

# Cross-filesystem behavior
find / -xdev -name core         # do not descend into other mounts
```

`-mtime +30` means "more than 30 *whole* days", so `-mtime +0` excludes
anything from the last 24 hours. Use `-mmin` when the boundary matters.

## Pruning

The `-prune` idiom is unintuitive and worth memorizing verbatim:

```bash
find . -path '*/node_modules' -prune -o -type f -print
find . \( -name .git -o -name vendor \) -prune -o -name '*.go' -print
```

Read it as: "if the path matches, prune it (and the whole subtree), OR
otherwise apply the real test and print". The explicit `-print` is required —
without it the implicit print applies to the pruned entries too.

GNU alternative that reads better:

```bash
find . -name .git -prune -o -type f -print
find . -type f -not -path '*/.git/*'      # simpler, but walks .git anyway
```

`-prune` is much faster on large trees because it never descends.

## Acting on results

```bash
find . -name '*.tmp' -delete                       # built in; safest and fastest
find . -type d -empty -delete                      # removes empty dirs bottom-up

find . -name '*.log' -exec gzip {} \;              # one gzip PER FILE
find . -name '*.log' -exec gzip {} +               # batched: far fewer processes

find . -name '*.conf' -exec grep -l secret {} +    # batched grep
find . -type f -exec sh -c 'echo "$1"' _ {} \;     # shell per file, {} as $1

find . -name '*.log' -print0 | xargs -0 -P8 gzip   # parallel
```

Prefer `-delete` over `-exec rm` — it needs no fork and cannot be tricked by a
filename. Note `-delete` implies `-depth`, so it must come after the tests.

`-execdir` runs in the file's own directory, which avoids a class of race and
path-injection problems:

```bash
find . -name '*.tmp' -execdir rm -- {} +
```

## Safe pipelines

Filenames may contain spaces, newlines, and quotes. Only NUL is impossible.

```bash
# Correct
find . -name '*.log' -print0 | xargs -0 gzip
while IFS= read -r -d '' f; do process "$f"; done < <(find . -print0)

# Broken on any unusual filename
find . -name '*.log' | xargs gzip
for f in $(find . -name '*.log'); do process "$f"; done
```

`mapfile -d ''` reads a NUL stream into an array (Bash 4.4+):

```bash
mapfile -d '' files < <(find . -name '*.log' -print0)
printf 'found %d\n' "${#files[@]}"
```

## xargs

| Flag | Purpose |
| --- | --- |
| `-0` | Input is NUL-delimited |
| `-n N` | At most N arguments per command |
| `-I{}` | Replace `{}`; implies `-n1` and disables batching |
| `-P N` | Run N commands in parallel |
| `-r` | Skip entirely if input is empty (GNU) |
| `-t` | Print each command before running |
| `-a file` | Read from a file instead of stdin |

```bash
# Parallel, one file per process.
find . -name '*.jpg' -print0 | xargs -0 -P4 -n1 convert-image

# Placeholder form for a fixed destination.
find . -name '*.bak' -print0 | xargs -0 -I{} mv {} /archive/

# Dry run first -- -t echoes each command.
find . -name '*.tmp' -print0 | xargs -0 -t rm
```

`-I{}` and `-P` combine, but `-I{}` forces one argument per invocation, which
is slower. When the command accepts many arguments, prefer `-n50 -P8`.

## Practical recipes

```bash
# Total size of files matching a pattern.
find . -name '*.log' -printf '%s\n' | awk '{ s += $1 } END { print s/1024/1024 " MiB" }'

# 20 largest files under a tree.
find . -type f -printf '%s\t%p\n' | sort -rn | head -20

# Files modified since the last deploy.
find /srv/app -newer /var/run/last-deploy -type f

# Delete logs older than 30 days, but keep the directory structure.
find /var/log/app -type f -name '*.log' -mtime +30 -delete

# Rotate: compress yesterday's, delete last month's.
find /var/log -name '*.log' -mtime +1  ! -name '*.gz' -exec gzip {} +
find /var/log -name '*.log.gz' -mtime +30 -delete

# World-writable files (a common audit finding).
find / -xdev -type f -perm -o+w -not -path '/proc/*' 2>/dev/null

# setuid/setgid binaries.
find / -xdev -type f -perm /6000 -exec ls -l {} + 2>/dev/null

# Broken symlinks.
find . -xtype l

# Duplicate filenames across a tree.
find . -type f -printf '%f\n' | sort | uniq -d

# Files not accessed in a year (candidates for archiving).
find /data -type f -atime +365

# Count files per subdirectory.
find . -maxdepth 1 -type d -exec sh -c 'printf "%s\t%s\n" "$(find "$1" -type f | wc -l)" "$1"' _ {} \; | sort -rn

# Change permissions correctly -- dirs and files differ.
find . -type d -exec chmod 755 {} +
find . -type f -exec chmod 644 {} +
```

`-printf` is GNU-only. On BSD/macOS use `-exec stat -f ...` or install
`findutils`.

## Performance

- `-prune` beats `-not -path`: it skips the subtree instead of walking it.
- `-exec ... +` beats `-exec ... \;` by orders of magnitude on large sets.
- `-delete` beats `-exec rm {} +`.
- Put `-name` before `-size`/`-mtime` so cheap tests filter first.
- `-xdev` prevents wandering into `/proc`, `/sys`, and network mounts.
- For repeated searches over a static tree, `locate`/`mlocate` uses an index
  and is far faster — but the index may be stale.

## Alternatives

`fd` (`fd-find` on Debian) is a modern replacement with saner defaults —
respects `.gitignore`, parallel by default, and simpler syntax:

```bash
fd '\.log$'                 # regex by default
fd -e log                   # by extension
fd -H -I pattern            # include hidden and ignored files
fd -x gzip                  # exec, parallel by default
```

`ripgrep` (`rg`) replaces `find | xargs grep` for content search and is
substantially faster:

```bash
rg -l 'pattern' --glob '*.conf'
```

Both are worth installing on machines you use often; `find` remains the one
guaranteed to be present.
