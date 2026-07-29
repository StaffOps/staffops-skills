---
name: linux-command-line
description: "Navigate the shell with pipes, globs and job control."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [linux, cli, pipes, redirection, globbing, jobs, find, xargs]
    category: linux
    related_skills: [bash-scripting, shell-text-processing, linux-filesystem]
---
# Linux Command Line

The mechanics the shell gives you before any script is written: redirection,
pipes, globbing, `find`/`xargs`, job control, and history. Getting these right
is what separates a one-liner that works from one that quietly mangles
filenames.

## When to Use

Use when composing commands interactively, wiring `find` into another tool,
redirecting output correctly, backgrounding long jobs, or explaining why a
pipeline behaves unexpectedly.

## Redirection

Every process starts with three file descriptors: 0 (stdin), 1 (stdout),
2 (stderr).

| Form | Effect |
| --- | --- |
| `> file` | stdout to `file`, truncating |
| `>> file` | stdout to `file`, appending |
| `2> file` | stderr to `file` |
| `&> file` | both stdout and stderr (Bash) |
| `> file 2>&1` | both, POSIX-portable |
| `2>&1 > file` | **stderr to the terminal**, stdout to the file |
| `< file` | read stdin from `file` |
| `<<< "text"` | here-string |
| `2>/dev/null` | discard stderr |
| `>/dev/null 2>&1` | discard everything |

Order matters, and this is the classic trap:

```bash
cmd > file 2>&1     # stdout -> file, then stderr -> wherever stdout points (file)
cmd 2>&1 > file     # stderr -> terminal (stdout's CURRENT target), then stdout -> file
```

`2>&1` means "make fd 2 a copy of fd 1 **as it is right now**", not "follow fd
1 forever".

Here-documents feed multi-line input:

```bash
cat <<EOF          # expands $variables
Path is $PATH
EOF

cat <<'EOF'        # quoted delimiter: no expansion at all
Literal $PATH
EOF

cat <<-EOF         # strips leading TABS (not spaces), for indented scripts
	indented
	EOF
```

## Pipes

```bash
cmd1 | cmd2               # stdout of cmd1 -> stdin of cmd2
cmd1 |& cmd2              # stdout AND stderr (Bash 4+)
cmd1 2>&1 | cmd2          # same, portable
cmd | tee file            # write to file AND pass through
cmd | tee -a file         # append
cmd | tee /dev/stderr | c # inspect mid-pipeline
```

Only stdout flows through a pipe. To filter stderr instead, swap the
descriptors:

```bash
cmd 2>&1 >/dev/null | grep error     # only stderr reaches grep
```

Every stage runs in a **subshell**, so variables set inside a `while read`
loop on the right side of a pipe are lost. Use process substitution:

```bash
count=0
find . -type f | while read -r f; do (( count++ )); done
echo "$count"                 # 0 -- the loop ran in a subshell

while read -r f; do (( count++ )); done < <(find . -type f)
echo "$count"                 # correct
```

Pipes also run stages **concurrently**, which is why `head` can terminate a
long-running producer early (via SIGPIPE, exit 141).

## Globbing

Expanded by the shell, not by the command — the command only ever sees the
resulting filenames.

| Pattern | Matches |
| --- | --- |
| `*` | Any characters except `/` and a leading `.` |
| `?` | Exactly one character |
| `[abc]` / `[a-z]` | One character from the set or range |
| `[!abc]` | One character not in the set |
| `{a,b}` | Brace expansion — `a` and `b`, even if no file exists |
| `**` | Recursive, with `shopt -s globstar` |

```bash
shopt -s globstar nullglob dotglob
ls **/*.log            # recursive
cp file{,.bak}         # expands to: cp file file.bak
mkdir -p proj/{src,test,docs}
```

Brace expansion is **not** globbing: it happens first, is purely textual, and
does not check the filesystem.

Critical shell options:

| Option | Without it |
| --- | --- |
| `nullglob` | A non-matching glob stays as the literal pattern string |
| `failglob` | Same, but you usually want an error instead |
| `dotglob` | `*` skips dotfiles |
| `globstar` | `**` behaves like `*` |
| `nocaseglob` | Matching is case-sensitive |

```bash
# Without nullglob this loop runs once with f="*.log" literally.
shopt -s nullglob
for f in *.log; do process "$f"; done
```

## find

```bash
find . -name '*.log'                  # by name (quote it: the shell must not expand)
find . -iname '*.LOG'                 # case-insensitive
find . -type f -o -type l             # files or symlinks
find . -mtime -7                      # modified in the last 7 days
find . -mmin -30                      # last 30 minutes
find . -size +100M                    # larger than 100 MiB
find . -user www-data -perm -o+w      # owned by a user AND world-writable
find . -maxdepth 2 -mindepth 1        # depth control
find . -newer reference.txt           # newer than a reference file
find . -empty                         # empty files and directories
find . -path '*/node_modules' -prune -o -type f -print   # skip a subtree
```

Acting on results:

```bash
find . -name '*.tmp' -delete                    # built in, safest
find . -name '*.log' -exec gzip {} \;           # one process per file
find . -name '*.log' -exec gzip {} +            # batched -- much faster
find . -name '*.log' -print0 | xargs -0 gzip    # equivalent, parallelizable
```

Prefer `-exec ... +` or `-print0 | xargs -0`. Never pipe bare `find` output
into `xargs` without `-print0` — filenames with spaces or newlines break it.

`-prune` must come before the action and needs the `-o ... -print` form to
work as expected; that idiom above is worth memorizing.

## xargs

```bash
xargs -0                 # NUL-delimited input (pairs with find -print0)
xargs -n1                # one argument per invocation
xargs -I{} cmd {} arg    # placeholder substitution (implies -n1)
xargs -P8                # 8 parallel processes
xargs -r                 # do nothing if input is empty (GNU)
xargs -t                 # echo each command before running it
```

```bash
# Parallel compression, NUL-safe.
find . -name '*.log' -print0 | xargs -0 -P8 -n1 gzip

# Placeholder form -- note it disables batching.
find . -name '*.conf' -print0 | xargs -0 -I{} cp {} /backup/
```

Without `-r`, GNU `xargs` still runs the command once with no arguments on
empty input, which surprises people (`rm` with no args is harmless; other
commands are not).

## Job control

```bash
cmd &                # start in the background
jobs                 # list jobs of this shell
fg %1                # bring job 1 to the foreground
bg %1                # resume job 1 in the background
Ctrl-Z               # suspend the foreground job (SIGTSTP)
Ctrl-C               # interrupt it (SIGINT)
kill %1              # signal by job number
wait                 # wait for all background jobs
wait $!              # wait for the most recent one, and get its exit status
disown -h %1         # keep the job running after the shell exits
```

Jobs are a property of the **shell**, so they die when the terminal closes
unless detached:

```bash
nohup long-task > out.log 2>&1 &     # immune to SIGHUP
setsid long-task > out.log 2>&1 &    # new session, fully detached
systemd-run --user --scope long-task # managed by systemd
```

For anything that must survive a disconnect, use `tmux` or `screen` rather
than `nohup` — you keep the ability to reattach and see the output.

Collect exit statuses from parallel work:

```bash
pids=()
for host in "${hosts[@]}"; do
    check "$host" & pids+=($!)
done
rc=0
for pid in "${pids[@]}"; do
    wait "$pid" || rc=1
done
exit "$rc"
```

## Command history and line editing

```bash
!!            # previous command
!$            # last argument of the previous command
!^            # first argument
!*            # all arguments
!abc          # most recent command starting with abc
^old^new      # rerun the previous command with one substitution
Ctrl-R        # reverse incremental search
Alt-.         # insert the last argument of the previous command
```

```bash
sudo !!                  # rerun the last command with sudo
mkdir /tmp/x && cd !$    # cd into the directory just created
```

Keep secrets out of history:

```bash
export HISTCONTROL=ignoreboth   # ignore duplicates and lines starting with a space
 secret-command --token=abc     # leading space -> not recorded
```

Useful editing keys: `Ctrl-A`/`Ctrl-E` (start/end), `Ctrl-W` (delete word
back), `Ctrl-U`/`Ctrl-K` (cut to start/end), `Ctrl-Y` (paste), `Alt-B`/`Alt-F`
(word movement).

## Getting information

```bash
type -a cmd          # builtin, function, alias, or which file(s)
command -v cmd       # portable "does this exist"
which -a cmd         # all matches in PATH (external, less reliable)
file /bin/ls         # what kind of file it is
ldd /bin/ls          # shared library dependencies
man 5 crontab        # section 5 = file formats
apropos compress     # search man page descriptions
help while           # help for a shell BUILTIN (man will not have it)
```

`type` beats `which` because it knows about builtins, functions, and aliases —
`which` only searches `PATH` and will confidently point at the wrong thing.

## Pitfalls

- **`2>&1` placed before `>`** — stderr goes to the terminal, not the file.
- **Unquoted globs passed to `find -name`** — the shell expands them first.
- **`for f in $(ls)`** — breaks on spaces. Use a glob or `find -print0`.
- **`xargs` without `-0`** — breaks on filenames with spaces or newlines.
- **Variables assigned inside a piped `while` loop** — lost to the subshell.
- **A glob that matches nothing** — stays literal without `nullglob`.
- **`rm -rf $dir/`** with an empty `$dir` — use `"${dir:?}"`.
- **`cmd &` in a script that then exits** — the child may be killed. `wait`.
- **`sudo cmd > /root/f`** — the redirect runs as *you*. Use `| sudo tee`.

## Verification

```bash
echo "$?"                       # exit status of the last command
set -x                          # trace expansion, then set +x
printf '%q\n' "$var"            # show the value with quoting made visible
cmd | od -c | head              # reveal invisible characters
ls -la; stat file               # confirm what actually changed
```

`scripts/explain-pipeline.sh` traces a pipeline stage by stage, showing line
counts and exit statuses per stage.

## Reference

- `references/redirection.md` — file descriptors, exec, advanced redirection
- `references/find-recipes.md` — practical `find` and `xargs` combinations
- `scripts/explain-pipeline.sh` — per-stage diagnostics for a pipeline
- `examples/bulk-rename.sh` — safe batch rename with dry-run and NUL handling
