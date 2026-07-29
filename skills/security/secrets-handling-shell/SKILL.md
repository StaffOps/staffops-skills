---
name: secrets-handling-shell
description: "Avoid leaking secrets through shell history, env and logs."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [secrets, shell-history, env-vars, credentials, leakage]
    category: security
    related_skills: [bash-scripting, ssh-hardening]
---
# Secrets Handling in Shell

The specific, concrete ways secrets leak through ordinary shell usage —
command history, process listings, environment variables, and logs — and
the habits that avoid each one. Most of these leaks require no special
attacker sophistication; they're readable by anyone with ordinary access to
the same host.

## When to Use

Use when writing a script that handles a credential or token, running a
command with a secret as an argument, deciding where to store an API key
locally, or reviewing a script/pipeline for secret-handling mistakes before
it ships.

## The core leak paths, and why each matters

| Path | Who can see it | How long it persists |
| --- | --- | --- |
| Shell history file | Anyone with read access to `~/.bash_history` (or equivalent) | Until manually cleared — often years |
| Process list (`ps aux`) | Any user on the host, in most default configurations | Only while the process runs, but that's often long enough |
| Environment variables | The process itself, and anyone who can read `/proc/<pid>/environ` | For the process's lifetime |
| Application/CI logs | Everyone with log access — frequently a much larger audience than intended | Indefinitely, per log retention |
| Shell scripts committed to version control | Everyone with repo access, forever, even after later removal | Permanently, in git history |

Each of these is a **different** exposure with a different fix — treating
"don't leak secrets" as one problem misses that command-line arguments and
environment variables, for instance, need entirely different mitigations.

## Command-line arguments are visible to every user

```bash
curl -H "Authorization: Bearer sk-abc123..." https://api.example.com   # BAD: visible in `ps`
```

```bash
ps aux | grep curl
# shows the FULL command line, including the token, to any user on the host
```

Any process's command-line arguments are visible via `ps` (or reading
`/proc/<pid>/cmdline`) to **every user on the system**, not just root, on
most default Linux configurations. A secret passed as a CLI argument is
exposed for as long as that process runs — which for a long-running command
can be a significant window.

**Correct approaches:**

```bash
# Read from an environment variable instead (see the next section for its own caveats).
curl -H "Authorization: Bearer ${API_TOKEN}" https://api.example.com

# Or from a file, via a flag the tool supports for exactly this.
curl -H "Authorization: Bearer $(cat token.txt)" https://api.example.com

# Many tools have a purpose-built flag that avoids the CLI-argument exposure entirely.
curl --netrc https://api.example.com
docker login --password-stdin < password.txt
```

`--password-stdin`-style flags exist specifically because tool authors
recognize the CLI-argument exposure — prefer them whenever a tool offers
one, over constructing the credential into the command line directly.

## Environment variables: better, but not perfect

```bash
export API_TOKEN="sk-abc123..."
curl -H "Authorization: Bearer ${API_TOKEN}" https://api.example.com
```

This avoids the `ps`-visible exposure — an environment variable is not part
of the command line arguments. But it is **not fully hidden**: it is
readable via `/proc/<pid>/environ` by root or the process's own user, and it
is inherited by every child process the shell spawns, which broadens the
exposure surface if any of those children are less trusted (a build script
that calls out to third-party tooling, for instance).

```bash
cat /proc/$$/environ | tr '\0' '\n'   # anyone with access to a process can read its full environment
```

For anything more sensitive than a short-lived personal token, a
purpose-built secrets mechanism (see below) is preferable to a bare
environment variable — but env vars remain a reasonable, low-friction choice
for many ordinary cases, and are strictly better than a CLI argument.

## Shell history

```bash
curl -H "Authorization: Bearer sk-abc123..." https://api.example.com
history | grep Bearer          # it's right there, potentially for years
```

Every command typed interactively is recorded in `~/.bash_history` (or the
equivalent for other shells) by default, and that file is rarely cleaned up
— a secret typed directly into a command is effectively permanent local
storage of it, readable by anyone who later gains access to that home
directory or a backup of it.

**Mitigations:**

```bash
export HISTCONTROL=ignoreboth      # ignore duplicate lines AND lines starting with a space

 curl -H "Authorization: Bearer sk-abc123..." https://api.example.com
# ^ the leading space means this specific command is NOT recorded, with
# HISTCONTROL=ignoreboth in effect
```

`HISTCONTROL=ignoreboth` combined with a deliberate leading space on any
command containing a secret is the standard, low-friction habit — but it
requires remembering to add the space every time, which is exactly the kind
of manual discipline that fails under time pressure. Preferring the file-
or environment-variable-based approaches above avoids needing to remember
this at all, since the secret then never appears as literal text in a
command line in the first place.

```bash
history -c              # clear the CURRENT session's history (does not touch the file yet)
history -d <line_number>  # delete a specific line
```

## Logs and CI output

```bash
set -x                    # BASH TRACE MODE: every command, WITH its expanded arguments, is printed
curl -H "Authorization: Bearer ${API_TOKEN}" https://api.example.com
set +x
```

`set -x` (or `bash -x script.sh`) prints every command *after variable
expansion* — meaning a secret stored in a variable is printed in full to
whatever is capturing that output, which in CI is frequently a persistently
stored, widely-readable build log. This is one of the most common real-world
secret leak mechanisms precisely because `-x` is genuinely useful for
debugging and easy to leave enabled, or to enable temporarily and forget
running with a secret already in scope.

```bash
set +x                     # explicitly disable before anything sensitive
curl -H "Authorization: Bearer ${API_TOKEN}" https://api.example.com
set -x                      # re-enable after, if still needed for the rest of the script
```

Most CI systems (GitHub Actions, GitLab CI) also provide native secret
masking that redacts a registered secret value from log output wherever it
appears — register secrets through that mechanism rather than relying
solely on avoiding `-x`, since masking is a backstop for cases the discipline
above misses.

## Storing secrets locally

```bash
# Weak: a plaintext file, readable by the file's permission bits alone.
echo "sk-abc123..." > ~/.api_token
chmod 600 ~/.api_token

# Better: an OS-native credential store, when available.
security add-generic-password -a "$USER" -s "api_token" -w "sk-abc123..."   # macOS Keychain

# Better still, for anything beyond personal/local use: a real secrets
# manager (Vault, AWS Secrets Manager, etc.) fetched at runtime rather
# than stored on disk at all.
```

A `chmod 600` plaintext file is an acceptable minimum for personal,
low-sensitivity local development tokens — it is not sufficient for
anything a production system depends on, where a proper secrets manager
with access logging, rotation, and centralized revocation is the correct
tool. `secrets-management-dotnet` and the `external-secrets-aws-sm` skill
cover the runtime-fetch pattern for applications specifically.

## .env files and version control

```
# .gitignore
.env
.env.*
!.env.example
```

An `.env` file with real secrets must never be committed — the `.gitignore`
entry above is table stakes, but it only prevents *future* commits; a
secret already committed even once remains in git history permanently,
retrievable by anyone with repo access regardless of later deletion.

```bash
git log --all --full-history -- .env         # confirm it was never committed, or find when it was
git log -p --all -S "sk-abc123" -- .          # search history for a specific leaked value
```

If a secret is found to have been committed, **the only real fix is
rotating the secret itself** — rewriting git history (`git filter-repo`,
BFG) removes it from the *current* clone but cannot guarantee every fork,
local clone, or CI cache that already pulled it is also cleaned; treat any
committed secret as compromised and rotate it, rather than treating history
rewriting as sufficient remediation on its own.

## A quick self-check before running a command with a secret

```
[ ] Is the secret a CLI argument? -> move it to an env var, stdin, or a file the tool reads
[ ] Is `set -x` active anywhere in scope? -> disable it before this line
[ ] Will this command's output go to a shared/persistent log? -> check for masking
[ ] Am I about to type it directly at an interactive prompt? -> lead with a space (HISTCONTROL=ignoreboth)
[ ] Does this need to be saved locally at all, or fetched fresh each time?
```

## Pitfalls

- **Passing a secret as a CLI argument** — visible to every user on the
  host via `ps`, for the process's entire runtime.
- **`set -x` left enabled around a secret-handling line** — one of the most
  common real leak mechanisms in CI logs specifically.
- **Assuming an environment variable is fully hidden** — it's not visible
  in `ps`, but is readable via `/proc/<pid>/environ` and inherited by child
  processes.
- **Committing a `.env` file even once** — deleting it later does not
  remove it from git history; rotate the secret instead of relying on
  history rewriting.
- **Relying solely on remembering the leading-space history trick** — a
  manual habit that fails under time pressure; prefer approaches that don't
  require remembering it.
- **Treating CI's secret-masking as sufficient without also avoiding
  `set -x`** — masking typically only redacts registered, exact-match
  values, not arbitrary derived or partially-transformed forms of them.

## Reference

- `bash-scripting` — the shell fundamentals these habits build on
- `ssh-hardening` — key-based auth as an alternative to password/token secrets for SSH specifically
