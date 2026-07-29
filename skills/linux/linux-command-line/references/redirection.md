# Redirection and File Descriptors

## The model

A process inherits an open file table. The first three entries are
conventional:

| fd | Name | Default |
| --- | --- | --- |
| 0 | stdin | terminal input |
| 1 | stdout | terminal output |
| 2 | stderr | terminal output |

Redirection rewires an entry **before** the command runs. The command itself
never knows: it just writes to fd 1.

`n>&m` means "make fd `n` a duplicate of fd `m` **as it currently points**".
It is a snapshot, not a link — which is the entire explanation for the
ordering trap below.

## Order of operations

```bash
cmd > file 2>&1
#     ^ 1 -> file
#            ^ 2 -> copy of 1, which is now file
# Result: both in file.

cmd 2>&1 > file
#     ^ 2 -> copy of 1, which is still the terminal
#          ^ 1 -> file
# Result: stdout in file, stderr on the terminal.
```

The second form is occasionally what you want — for example to keep errors
visible while capturing data:

```bash
./job.sh 2>&1 > results.txt        # errors on screen, data to the file
```

To send only stderr down a pipe, discard stdout after the swap:

```bash
cmd 2>&1 >/dev/null | grep -i error
```

## Common forms

| Goal | Command |
| --- | --- |
| stdout to a file | `cmd > out` |
| Append stdout | `cmd >> out` |
| stderr to a file | `cmd 2> err` |
| Both to one file | `cmd > all 2>&1` or `cmd &> all` (Bash) |
| Both, appending | `cmd >> all 2>&1` or `cmd &>> all` |
| Separate files | `cmd > out 2> err` |
| Discard stdout, keep stderr | `cmd > /dev/null` |
| Discard everything | `cmd > /dev/null 2>&1` |
| stderr into a pipe | `cmd 2>&1 \| next` |
| Only stderr into a pipe | `cmd 2>&1 >/dev/null \| next` |
| Swap stdout and stderr | `cmd 3>&1 1>&2 2>&3 3>&-` |

The swap uses fd 3 as scratch space, then closes it with `3>&-`.

## Truncation happens first

The shell opens and truncates the redirect target **before** the command runs.
This is why reading and writing the same file destroys it:

```bash
sort file > file        # file is emptied before sort opens it
grep x file > file      # same
```

Correct forms:

```bash
sort file > tmp && mv tmp file
sort -o file file            # sort supports in-place explicitly
sponge < file               # from moreutils: buffers, then writes
```

`set -o noclobber` makes `>` refuse to overwrite an existing file; `>|`
overrides it for a single command.

## exec: redirect the shell itself

Without a command, `exec` changes the current shell's descriptors permanently:

```bash
exec > logfile 2>&1        # everything from here on goes to logfile
echo "this is logged"

exec 3< input.txt          # open fd 3 for reading
read -r line <&3
exec 3<&-                  # close it

exec 4> output.txt         # open fd 4 for writing
printf 'data\n' >&4
exec 4>&-
```

Keeping a descriptor open avoids reopening a file in a loop, and is how
`flock` holds a lock for the process lifetime:

```bash
exec 9> /var/lock/myjob.lock
flock -n 9 || exit 1
# lock is held until the process exits and fd 9 closes
```

A common script idiom — log everything while still showing it:

```bash
exec > >(tee -a "$LOGFILE") 2>&1
```

## Process substitution

`<(cmd)` and `>(cmd)` give a command a *filename* that is really a pipe. Use
it when a tool insists on a file path.

```bash
diff <(sort a.txt) <(sort b.txt)
comm -13 <(sort a) <(sort b)
join <(sort -k1 a) <(sort -k1 b)

# Feed one stream to two consumers.
cmd | tee >(gzip > out.gz) >(wc -l > count.txt) > /dev/null

# Keep a while-loop in the current shell (no subshell).
while read -r line; do total=$(( total + 1 )); done < <(cmd)
```

Under the hood the shell passes `/dev/fd/63` or similar. It is a Bash/Zsh
feature, not POSIX — `sh` scripts need a temp file instead.

## Here-documents and here-strings

```bash
cat <<EOF            # expands $var, $(cmd), backslashes
Value: $var
EOF

cat <<'EOF'          # quoted delimiter: entirely literal
Value: $var
EOF

cat <<-EOF           # strips leading TAB characters only
	indented in source
	EOF

grep pattern <<< "$string"      # here-string
```

A here-string appends a trailing newline, which matters when comparing:

```bash
wc -c <<< "abc"      # 4, not 3
printf 'abc' | wc -c # 3
```

Assigning a here-document to a variable:

```bash
read -r -d '' text <<'EOF' || true
line one
line two
EOF
```

The `|| true` is needed because `read` returns non-zero when it hits EOF
without the delimiter, which `set -e` would treat as failure.

## Redirecting a whole block

Redirection applies to compound commands too, which avoids repeating it:

```bash
{
    echo "header"
    generate_body
    echo "footer"
} > report.txt

while read -r line; do
    process "$line"
done < input.txt > output.txt 2> errors.txt
```

## /dev entries worth knowing

| Path | Purpose |
| --- | --- |
| `/dev/null` | Discards writes; reads return EOF |
| `/dev/zero` | Reads return infinite NUL bytes |
| `/dev/urandom` | Cryptographically suitable random bytes |
| `/dev/stdin`, `/dev/stdout`, `/dev/stderr` | The current process's fds as paths |
| `/dev/fd/N` | File descriptor N as a path |
| `/dev/tcp/host/port` | Bash-only: opens a TCP socket |

```bash
# Give a tool that requires a path the current stdin.
jq . /dev/stdin <<< "$json"

# Bash TCP -- handy when nc is unavailable.
exec 3<>/dev/tcp/example.com/80
printf 'GET / HTTP/1.0\r\n\r\n' >&3
cat <&3
exec 3<&-
```

## Checking what a process has open

```bash
ls -l /proc/$$/fd            # descriptors of the current shell
lsof -p "$pid"               # everything a process has open
lsof /var/log/app.log        # which processes hold this file
```

This is how you find the cause of "disk full but `du` shows nothing" — a
deleted file still held open by a process. `lsof | grep deleted` reveals it,
and the space returns only when the process closes it or restarts.
