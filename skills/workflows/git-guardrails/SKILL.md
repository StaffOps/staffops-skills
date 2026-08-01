---
name: git-guardrails
description: "Block destructive git commands before Claude runs them."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [git, hooks, pretooluse, safety, claude-code]
    category: workflows
    related_skills: [git-advanced]
---
# Git Guardrails

A Claude Code `PreToolUse` hook that inspects every `Bash` tool call before it
runs and blocks destructive git operations at the shell level, instead of
relying on the model remembering not to run them. This is mechanical
enforcement, not policy prose: `git-conventions` (steering) states the rule
("never force-push without approval"); this skill is the hook that makes the
rule impossible to forget mid-session.

## When to Use

Use when a repository needs a hard backstop against an agent (or a human
pasting a command an agent suggested) running `push --force`, `reset --hard`,
`clean -f`, a branch or tag deletion, or an `rm -rf` that lands on `.git` -
before the command executes, not after. Also reach for this when an existing
deny-list hook is too blunt (all-or-nothing) and the team needs per-repo
tuning: some of these commands are legitimate in a supervised recovery, and
the hook needs a way to say so without being edited by hand every time.

## The failure mode this prevents

Two concrete scenarios motivate every rule below:

1. **An agent force-pushes over a colleague's unpushed commits.** The agent
   rebases its branch, the rebase looks clean, and it force-pushes to
   "finish the job." If a teammate pushed to that same branch in the
   meantime, `--force` silently overwrites their commits on the remote - no
   confirmation, no diff shown, no error unless someone happens to notice
   the branch's commit count went down.
2. **An agent resets away uncommitted work it did not create.** A working
   tree already has uncommitted changes - a human's WIP, or output from a
   step earlier in the same session - when the agent decides the tree is in
   a bad state and runs `git reset --hard` to "get back to a clean slate."
   `reset --hard` does not ask which changes are safe to discard; it
   discards all of them, and `git clean -f` does the same for untracked
   files. Neither operation leaves a reflog entry for what was thrown away,
   because the reflog tracks commits and refs, not working-tree content.

A model can be told "don't do this" in its system prompt and still do it,
because the instruction competes with whatever local reasoning made the
destructive command look correct in the moment. A `PreToolUse` hook runs
outside the model's context entirely: it sees the literal command string
Claude Code is about to execute and can refuse before the shell ever forks.

## What gets blocked

Each rule fires on an individual statement, not the whole raw command line -
a command is split on `&&`, `||`, `;`, and `|` before evaluation, so
`git rebase main && git push --force` is caught even though `git rebase main`
on its own is harmless. Before any rule runs, the statement is tokenized with
a small quote-aware word-splitter (single and double quotes are stripped, not
treated as text), so `git push "--force" origin main` is evaluated exactly
like the unquoted form - wrapping a flag in quotes does not change how it
matches.

| Rule id | Blocks | Exempt / safer alternative |
| --- | --- | --- |
| `force-push` | `git push --force` / `-f`, or a `+refspec` (`git push origin +main`, `+feature:main`) | `--force-with-lease`, `--force-if-includes` |
| `reset-hard` | `git reset --hard` | `git reset --soft` / `--mixed` |
| `branch-force-delete` | `git branch -D`, `--delete --force` | `git branch -d` (refuses if unmerged) |
| `clean-force` | `git clean -f`, `-fd`, `-fdx`, any short-flag cluster containing `f` | `git clean -n` (dry run first) |
| `checkout-discard` | `git checkout -- <path>`, `git checkout .` | `git stash` first if unsure |
| `restore-discard` | `git restore <path>` (working tree) | `git restore --staged <path>` (index only) |
| `skip-hooks` | `--no-verify`, `--no-gpg-sign`, `gpgsign=false` | run the skipped hook manually to see why it fails |
| `rewrite-pushed-history` | `commit --amend` or `rebase` when the target repo's `HEAD` equals its upstream tracking ref exactly | `git revert` for already-pushed commits |
| `tag-delete-local` | `git tag -d` / `--delete` | confirm with `git ls-remote --tags origin <tag>` first |
| `remote-ref-delete` | `git push --delete`, `git push origin :refs/tags/...` | coordinate with anyone who may have already fetched the ref |
| `rm-rf-git` | `rm` with a recursive flag (`-r`, `-R`, `--recursive`) AND a force flag (`-f`, `-F`, `--force`) anywhere among its arguments, targeting `.git`, the repo root, or `/` | scope the path explicitly (`rm -rf ./build`) |
| `command-substitution` | any statement containing `$(...)` or `` `...` `` | run the substitution yourself first, then paste the literal result |

`rewrite-pushed-history` is the one rule that does not decide from the
command text alone. It runs `git rev-parse @{u}` and `git rev-parse HEAD` at
hook time: if they match, every local commit is already mirrored on the
remote, and an amend or rebase right now would rewrite something a clone may
already have. If there is no upstream (a local-only branch), the check
cannot fire, because there is nothing "already pushed" to protect.

This live check runs against the repository the intercepted command actually
targets, not necessarily the hook process's own working directory: if the
command includes `-C <path>`, `--git-dir=<path>`, or `--work-tree=<path>`,
the check runs with the same flag against the same path. If that path can't
be resolved to an existing directory, or the live check fails for any reason
other than "no upstream configured", the rule fails CLOSED (blocks) instead
of silently falling back to checking the wrong repository and returning a
false "safe".

`rm-rf-git` similarly does not require a single combined token: `rm -r -f
.git`, `rm -Rf .git`, and `rm -rf .git` are all detected the same way, by
scanning every argument for a recursive flag and a force flag independently
rather than pattern-matching one glued-together short-flag cluster.

### Command wrapping (`bash -c`, `sh -c`, `eval`)

One level of `bash -c "..."`, `sh -c "..."`, or `eval "..."` indirection is
unwrapped automatically: the hook extracts the literal inner command string
and re-runs every rule above against it before allowing the outer statement
through. `bash -c "git push --force origin main"` and
`eval "git push --force origin main"` are both blocked by `force-push`, the
same as the unwrapped form. This unwrapping is **one level only** - a second
layer of wrapping (`bash -c "bash -c '...'"`) is not followed; see "Known
limitations".

## Wiring it into Claude Code

### 1. Copy the hook script

The script is at
[scripts/block-dangerous-git.sh](scripts/block-dangerous-git.sh). It is
POSIX-leaning bash that avoids bash 4+ features (no `mapfile`, no
associative arrays) so it runs unmodified on macOS's stock bash 3.2 as well
as Linux and WSL.

```bash
# Project scope
cp scripts/block-dangerous-git.sh .claude/hooks/block-dangerous-git.sh
chmod +x .claude/hooks/block-dangerous-git.sh

# Global scope (applies to every project)
cp scripts/block-dangerous-git.sh ~/.claude/hooks/block-dangerous-git.sh
chmod +x ~/.claude/hooks/block-dangerous-git.sh
```

### 2. Register the PreToolUse hook

Add to `.claude/settings.json` (project) or `~/.claude/settings.json`
(global) - merge into an existing `hooks.PreToolUse` array, do not overwrite
other settings:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/block-dangerous-git.sh"
          }
        ]
      }
    ]
  }
}
```

The `matcher` field scopes the hook to the `Bash` tool only - it does not
run for `Read`, `Edit`, or other tool calls. Exit code `2` from the hook
blocks the tool call and returns the hook's stderr to Claude as the reason;
exit code `0` allows it through unchanged.

### 3. Verify

```bash
echo '{"tool_input":{"command":"git push --force origin main"}}' \
  | .claude/hooks/block-dangerous-git.sh
echo "exit: $?"   # expect 2, and a BLOCKED message on stderr

echo '{"tool_input":{"command":"git push --force-with-lease origin main"}}' \
  | .claude/hooks/block-dangerous-git.sh
echo "exit: $?"   # expect 0, no output
```

## Per-repo tuning (the override mechanism)

The original inspiration for this skill was a flat deny-list with no
override - blocked meant blocked, permanently, for every repo the hook was
installed in. That is too rigid: `git branch -D spike/throwaway` on a branch
nobody else has ever fetched is not actually dangerous, and a recovery
runbook may legitimately need `git clean -fdx` on a known build directory.

Drop a config file at `<repo>/.claude/git-guardrails.json` (see
[references/example-config.json](references/example-config.json)):

```json
{
  "disable_rules": ["tag-delete-local"],
  "allow_patterns": [
    "^git clean -fdx build/dist/?$",
    "^git branch -D spike/.*$"
  ]
}
```

- `disable_rules` - rule ids (from the table above) to turn off entirely for
  this repository.
- `allow_patterns` - extended regexes matched against the full, unsplit,
  pre-tokenization command text. Any match exempts that entire command from
  every rule, so keep these narrow (anchor with `^...$`, name the exact
  branch/path pattern) - a loose pattern here reopens the hole the hook
  exists to close.

If `jq` is not installed, config overrides still work through a minimal
fallback parser (a plain-text extractor for the flat `["a", "b"]` string
array shown above - not a real JSON parser), and the hook prints an explicit
warning to stderr the first time it loads a config file this way, so an
operator is never silently confused by unexplained blocks or unexplained
allows. See "Known limitations" for exactly what the fallback does and does
not handle.

For an emergency, supervised recovery session, set
`GIT_GUARDRAILS_DISABLE=1` in the environment before launching Claude Code to
bypass every rule for that session. This is meant for a human to set for
themselves, not something an agent should set on its own behalf - it prints
a visible notice to stderr every time it takes effect so the bypass is never
silent.

This mirrors the same philosophy as this organization's `git-conventions`
steering: destructive operations require explicit human confirmation, not a
silent, unappealable block forever baked into a script.

## Known limitations

- **Quote-aware tokenizing, but still not a real shell parser.** The hook's
  `tokenize` function strips single and double quotes and treats their
  contents as part of the same word, which is enough to normalize
  `git push "--force" origin main` to the same token stream as the unquoted
  form. It does NOT process backslash escapes, ANSI-C `$'...'` quoting,
  brace expansion, or variable expansion. A flag-like substring inside a
  quoted commit message (`git commit -m "add --force flag handling"`) can
  in principle still trip a rule, because the message text is scanned the
  same way command arguments are; the hook fails toward blocking in
  ambiguous cases rather than toward allowing, which is the safer failure
  mode here but can produce an occasional false positive on unusual commit
  messages.
- **Chain-operator splitting happens before quote parsing.** The hook splits
  a command on `&&`, `||`, `;`, and `|` using a plain regex over the raw
  text, before tokenizing. If one of those operators appears literally
  inside a quoted string passed to `bash -c`/`eval` (for example
  `bash -c "git checkout -- f && git push --force origin main"`), the split
  happens at that point too, and the two resulting halves are no longer a
  clean `bash -c "..."` wrapper - the unwrapping in the next bullet will not
  find and re-scan it correctly. A single, non-chained wrapped statement
  (`bash -c "git push --force origin main"`) is unaffected and is unwrapped
  correctly; this only bites when the wrapped string itself contains a
  chain operator.
- **`bash -c` / `sh -c` / `eval` unwrapping goes exactly one level deep.**
  `bash -c "git push --force origin main"` and
  `eval "git push --force origin main"` are unwrapped and re-scanned. A
  second layer of wrapping, such as `bash -c "bash -c 'git push --force
  origin main'"`, is not followed - the inner `bash -c` is treated as
  ordinary argument text on the second pass, not unwrapped again. This is a
  deliberate scope limit, not an oversight: unwrapping is meant to close the
  common "one indirection" bypass an agent might reach for, not to be a
  general-purpose shell interpreter.
- **`$(...)` and backtick command substitution are blocked outright, not
  evaluated.** This hook does not execute anything to see what a
  substitution would produce - doing so safely (without itself running
  arbitrary attacker-controlled code) is not something a shell script can
  do. The chosen tradeoff is to fail closed: any statement containing
  `$(...)` or a backtick is blocked under the `command-substitution` rule
  and requires human review, even when the substitution is actually benign
  (`git commit -m "Release $(date +%F)"` is blocked, not just
  `git $(echo push --force) origin main`). This trades a false positive on
  ordinary uses of command substitution for closing what would otherwise be
  an unconditional bypass of every other rule in this hook - text inside
  `$(...)` never gets tokenized or matched against anything, so leaving it
  unblocked would mean any rule here could be defeated by moving the
  dangerous flag into a substitution. Repos that rely on command
  substitution in git-adjacent commands can add `"command-substitution"` to
  `disable_rules`, or a narrow `allow_patterns` entry for the exact command.
- **`tag-delete-local` cannot check the remote.** Verifying whether a tag
  was already pushed requires `git ls-remote`, a network call this hook
  deliberately does not make (it runs on every `Bash` call; a network round
  trip there would add latency, and could hang, on every unrelated command
  too). It flags all local tag deletions for human review instead of
  guessing.
- **`remote-ref-delete` cannot always distinguish a tag from a branch** from
  the command text alone, so `git push --delete` is flagged regardless of
  which kind of ref it targets.
- **`rewrite-pushed-history`'s `-C`/`--git-dir`/`--work-tree` handling is a
  single-flag, last-one-wins parser.** It supports one target repository per
  statement; it does not replicate git's full "each `-C` is relative to the
  previous one" chaining behavior for multiple `-C` flags in the same
  command. If a target path is given and cannot be resolved to an existing
  directory, or the live upstream check fails for a reason other than "no
  upstream configured" (unrecognized error text, not a git repo, detached
  HEAD with no commits, etc), the rule fails closed and blocks rather than
  guessing - see "What gets blocked" above.
- **jq is the primary JSON parser** for both the hook payload
  (`tool_input.command`) and the per-repo config file
  (`.claude/git-guardrails.json`). If jq is missing:
  - Extracting `tool_input.command` falls back to a plain-text extraction
    and fails OPEN (allows the command) if that extraction comes back
    empty, rather than blocking unrelated `Bash` calls just because `jq`
    was not installed.
  - Loading the config file falls back to `extract_json_string_array`, a
    minimal, regex-based extractor that only understands the documented
    flat schema (`"disable_rules": ["a", "b"]` with plain, unescaped
    strings) - it is not a JSON parser and will not handle escaped quotes,
    nested structures, or comments. The hook prints
    `git-guardrails: jq not found, using a minimal fallback parser for
    <path> ...` to stderr every time this path is taken, so a missing `jq`
    is never a silent reason overrides stop applying.
- This hook is one layer of defense. It does not replace code review, branch
  protection on the remote, or the human-approval gates already required by
  `git-conventions` steering for commit/push - it exists to stop the
  specific case where a command runs before a human ever sees it proposed.

## Anti-patterns

- Installing the hook and assuming it is now safe to skip reviewing
  `git push` / `git reset` proposals from an agent - the hook covers the
  patterns in the table above, not every way to lose work.
- Writing an `allow_patterns` entry broad enough to match more than the one
  known-safe command it was added for (for example `.*--force.*` instead of
  a path- or branch-scoped pattern) - that is functionally the same as
  disabling `force-push` everywhere.
- Setting `GIT_GUARDRAILS_DISABLE=1` in a persistent shell profile so it is
  always on - the point of the escape hatch is that it is visible and
  temporary, not a permanent way to silence the hook.
- Relying on `tag-delete-local` alone to decide whether a tag deletion is
  safe - it cannot see the remote; check with `git ls-remote --tags origin
  <tag>` yourself before disabling the rule for that tag.
- Copying the script but skipping the verification step in "Wiring it into
  Claude Code" - a typo in the `hooks.json` matcher or command path means
  the hook silently never runs, and the repo is unprotected while looking
  configured.
- Assuming every layer of shell indirection is unwrapped - only one level of
  `bash -c` / `sh -c` / `eval` is followed, and `$(...)` / backtick content
  is never evaluated, only flagged. Nesting deeper than that is out of
  scope; see "Known limitations".
- Running Claude Code without `jq` installed and assuming
  `.claude/git-guardrails.json` overrides are silently working - watch for
  the `jq not found` warning on stderr, and prefer installing `jq` over
  relying on the fallback parser for anything beyond the simple documented
  schema.
