---
name: git-advanced
description: "Rebase, bisect and recover Git history safely."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [git, advanced, workflows]
    category: workflows
    related_skills: []
---
# Git Advanced Patterns

Operations beyond basic add/commit/push. ALWAYS get user approval before destructive operations (see `git-conventions` steering).

## When to Use

Advanced Git operations and patterns. Use for rebase, conflict resolution, bisect, hotfix flows, recovery scenarios, working with submodules, or rewriting history safely. Complements `git-conventions` (steering) which covers commit/push rules.

## Rebase patterns

### Interactive rebase (rewrite history of YOUR unpushed commits)

```bash
git rebase -i HEAD~5    # Edit last 5 commits
```

In the editor:
- `pick <hash>` — keep commit as-is
- `reword <hash>` — edit commit message
- `edit <hash>` — pause to amend the commit
- `squash <hash>` — combine with previous commit
- `fixup <hash>` — like squash but discard the message
- `drop <hash>` — remove the commit
- (reorder lines to reorder commits)

### Rebase against main

```bash
git fetch origin
git rebase origin/main
```

Resolves conflicts by replaying YOUR commits on top of latest main.

### When NOT to rebase
- Branches that are SHARED (others have pulled them)
- Already-pushed commits (rewriting forces force-push)

### Pull with rebase (cleaner history)

```bash
git pull --rebase origin main

# Set as default
git config --global pull.rebase true
```

## Conflict resolution

### Find conflicts
```bash
git status                         # Lists files with conflicts
git diff --name-only --diff-filter=U  # Unmerged files only
```

### Mark resolved
```bash
git add <resolved-file>
git rebase --continue   # If rebasing
git merge --continue    # If merging
```

### Abort if too messy
```bash
git rebase --abort      # Or
git merge --abort
```

### Use mergetool for complex conflicts
```bash
git mergetool
```

Or manually edit the file looking for `<<<<<<<`, `=======`, `>>>>>>>` markers.

## Bisect — find when a bug was introduced

```bash
# Start
git bisect start
git bisect bad                  # Current commit is broken
git bisect good <known-good-hash>  # Last known good commit

# Git checks out the midpoint, you test:
# (run tests, manual verification, etc.)

git bisect good   # if commit is OK
git bisect bad    # if commit has the bug

# Repeat until git identifies the culprit. Then:
git bisect reset
```

### Automated bisect

```bash
git bisect start HEAD <known-good>
git bisect run ./scripts/test-something.sh
# Script must exit 0 for "good", non-zero for "bad"
```

## Hotfix flow (production fix)

### Pattern 1: from main directly

```bash
# Start from main
git checkout main
git pull
git checkout -b hotfix/critical-bug

# Make changes
git add ...
git commit -m "fix: resolve critical issue X"

# Push and PR
git push -u origin hotfix/critical-bug
# Create PR, merge to main, deploy

# Optional: tag the release
git tag -a v1.2.1 -m "Hotfix: critical bug X"
git push origin v1.2.1
```

### Pattern 2: cherry-pick from feature branch

If the fix exists in a feature branch but you need it in main NOW:

```bash
# Find the commit
git log --oneline feature/long-running-thing | grep "fix:"

# Cherry-pick to main
git checkout main
git cherry-pick <commit-hash>
git push
```

## Recovery scenarios

### Undo last commit (keep changes)
```bash
git reset --soft HEAD~1
```

### Undo last commit (discard changes — DESTRUCTIVE)
```bash
git reset --hard HEAD~1   # Asks user approval per git-conventions steering!
```

### Recover deleted commit
```bash
git reflog                # Shows recent HEAD positions
git checkout <commit-hash>  # Or:
git reset --hard <commit-hash>
```

The reflog keeps history of HEAD changes for ~30 days. Most "lost" commits are recoverable.

### Recover deleted branch
```bash
git reflog | grep <branch-name>   # Find last commit
git branch <branch-name> <commit-hash>
```

### Undo a public commit (revert, not reset)
```bash
git revert <commit-hash>
```

`revert` creates a NEW commit that undoes the changes. Safe for shared history.

### Recover from bad rebase

```bash
git reflog                    # Find pre-rebase HEAD
git reset --hard HEAD@{5}     # Or specific hash from reflog
```

## Submodules

### Adding a submodule
```bash
git submodule add https://github.com/user/repo.git path/to/submodule
git commit -am "Add submodule"
```

### Cloning a repo with submodules
```bash
git clone --recurse-submodules <repo>
# Or after clone:
git submodule update --init --recursive
```

### Updating submodule to latest
```bash
git submodule update --remote
```

### Removing a submodule
```bash
git submodule deinit -f path/to/submodule
git rm -f path/to/submodule
rm -rf .git/modules/path/to/submodule
```

## Stash patterns

### Save uncommitted work temporarily
```bash
git stash push -m "WIP: refactoring"
# Switch branches, do other work...
git stash pop
```

### Stash including untracked files
```bash
git stash push -u
```

### Stash specific files
```bash
git stash push -m "auth changes" src/auth.go
```

### List/inspect/apply
```bash
git stash list                  # See all stashes
git stash show -p stash@{1}     # Show changes in a stash
git stash apply stash@{1}       # Apply without removing from list
git stash drop stash@{1}        # Remove a stash
```

## Worktrees (multiple checkouts)

When you need multiple branches checked out simultaneously:

```bash
# Create a worktree
git worktree add ../my-repo-feature feature/new-thing

# Now ../my-repo-feature has feature/new-thing checked out
# Original directory still on main

# Remove when done
git worktree remove ../my-repo-feature
```

Useful for: hotfix while in middle of feature, comparing two branches side-by-side.

## Tag operations

### Create a tag
```bash
# Lightweight tag
git tag v1.2.0

# Annotated tag (preferred — has metadata)
git tag -a v1.2.0 -m "Release 1.2.0"
```

### Push tags
```bash
git push origin v1.2.0       # Single tag
git push origin --tags       # All tags
```

### Delete a tag
```bash
git tag -d v1.2.0            # Local
git push origin --delete v1.2.0  # Remote
```

### Find which tag contains a commit
```bash
git tag --contains <commit-hash>
```

## Inspecting history

### Pretty log
```bash
git log --oneline --graph --all --decorate
```

### Find commits by author
```bash
git log --author="<name>" --oneline
```

### Find commits that touched a file
```bash
git log --follow -- path/to/file
```

### Find commits with specific text in diff
```bash
git log -S "function_name"   # Pickaxe: when this string was added/removed
git log -G "regex"           # Like -S but regex
```

### Blame line range
```bash
git blame -L 10,20 path/to/file
```

### Show changes in a commit
```bash
git show <commit-hash>
git show <commit-hash> -- path/to/file
```

## Cleaning up

### Remove untracked files (CAREFUL)
```bash
git clean -n          # Dry run — shows what would be removed
git clean -fd         # Actually remove files and directories
git clean -fdx        # Also remove gitignored files
```

`-n` first, ALWAYS. Then `-fd` after confirming.

### Prune old branches that no longer exist on remote
```bash
git fetch --prune
git remote prune origin
```

### Garbage collect
```bash
git gc                 # Standard cleanup
git gc --aggressive    # More thorough (slower)
```

## Force push safely

`git push --force` is dangerous on shared branches. Always use:

```bash
git push --force-with-lease
```

This refuses to push if remote has commits you don't have locally. Catches accidental overwrites.

Even better, configure as default:
```bash
git config --global alias.fpush "push --force-with-lease"
# Now use: git fpush
```

## Useful aliases

Add to `~/.gitconfig`:

```
[alias]
  st = status -s
  co = checkout
  br = branch
  ci = commit
  unstage = reset HEAD --
  last = log -1 HEAD
  lg = log --oneline --graph --decorate --all
  amend = commit --amend --no-edit
  fpush = push --force-with-lease
  uncommit = reset --soft HEAD~1
```

## Common pitfalls

### Pitfall: pushing local main to wrong remote
Solution: `git remote -v` first; verify the URL.

### Pitfall: rebasing pushed commits
Solution: don't rebase pushed commits unless they're truly yours alone (not shared).

### Pitfall: accidentally committing secrets
Solution:
1. **Don't push** if you notice immediately
2. `git reset HEAD~1` (unstage)
3. Edit the file, remove secret
4. Re-commit

If pushed:
1. **Rotate the secret immediately** (assume compromised)
2. Use `git filter-repo` or BFG to remove from history
3. Force push (with team coordination)
4. Notify security team

### Pitfall: large files in history
Solution: use Git LFS for binary files. If already committed:
```bash
git filter-repo --invert-paths --path path/to/large-file
```

### Pitfall: stale forks / branches piling up
Solution: regularly `git fetch --prune` and `git branch -d <merged>`.

## Reference

- Pro Git book: https://git-scm.com/book
- Git docs: https://git-scm.com/docs
- BFG repo cleaner: https://rtyley.github.io/bfg-repo-cleaner/
- git-filter-repo: https://github.com/newren/git-filter-repo
- Related: `git-conventions` (steering — basic rules), `conventional-commits`, `jira-conventions`

## When NOT to use

- **Basic add/commit/push** — this skill is for complex operations (rebase, bisect, recovery).
- **Commit message formatting** — see [conventional-commits](../workflows/conventional-commits/SKILL.md).
- **CI/CD pipeline configuration** — see [pipeline-template-apps](../workflows/pipeline-template-apps/SKILL.md).


## Decision tree

```
Which operation do you need?
├── Rebase?
│   ├── Update branch with main → git rebase main (on feature branch)
│   ├── Squash messy history → git rebase -i HEAD~N (interactive)
│   ├── Conflict during rebase → fix, git add, git rebase --continue
│   └── Abort bad rebase → git rebase --abort
├── Find which commit broke it?
│   └── git bisect start → git bisect bad → git bisect good <ref> → test
├── Recover lost work?
│   ├── Dropped commit → git reflog → git cherry-pick <sha>
│   ├── Deleted branch → git reflog → git checkout -b branch <sha>
│   ├── Bad reset --hard → git reflog → git reset --hard <sha>
│   └── Amended wrongly → git reflog (previous HEAD is there)
├── Submodules?
│   ├── Clone with submodules → git clone --recurse-submodules
│   ├── Update → git submodule update --init --recursive
│   └── Add new → git submodule add URL path
└── Hotfix flow?
    └── Branch from production → fix → merge to production → cherry-pick to dev
```

## Related skills

- [conventional-commits](../workflows/conventional-commits/SKILL.md) — commit message format.
- [git-guardrails](../workflows/git-guardrails/SKILL.md) — safety hooks, destructive-op prevention.
- [bash-scripting](../shell/bash-scripting/SKILL.md) — automating git workflows in scripts.
- [session-handoff](../workflows/session-handoff/SKILL.md) — preserving context across sessions via commits.
