---
name: ai-coding-agent-guardrails
description: "Scope file, shell, and review permissions for coding agents."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [ai, coding-agent, guardrails, permissions, secrets, review-gates, subagent]
    category: ai
    related_skills: [ai-agent-security, git-guardrails, mcp-server-security, agent-platform-design]
---
# AI Coding Agent Guardrails

Configuring the permission surface of an AI coding agent (Claude Code, Cursor,
Copilot, Codex, or an in-house equivalent) that reads and writes a codebase
and runs shell commands as part of a development workflow: which of its tools
carry which blast radius, how to keep broad filesystem read access from
becoming a secrets leak, and which of its outputs need a human to look at a
diff before it lands. This is `ai-agent-security`'s general framework applied
to one concrete, narrow tool set -- it does not re-derive that framework, the
git-command-blocking mechanism (`git-guardrails`, already shipped in this
catalog), or MCP transport/authorization (`mcp-server-security`); it cites all
three and covers only what is specific to a coding agent's permission surface.

## When to Use

- Configuring a new coding agent for a repo or team for the first time --
  deciding its default tool grants before the first session, not after
  something surprising happens
- Deciding whether a specific coding-agent action should apply automatically
  or wait for a human to review a diff
- An agent has, or is about to get, read access to a repo that also holds
  `.env` files, credential files, SSH keys, or a config file with an inline
  secret
- Wiring a supervisor/subagent coding workflow where a dispatched subagent
  should not inherit the supervisor's full read/write/shell/git tool set
- Reviewing an agent's permission configuration (`settings.json` or
  equivalent) before it runs unattended, in CI, or with elevated scope

## 1. The coding-agent tool surface, tiered by blast radius

A coding agent's tools are not one risk surface, they are at least five, and
`ai-agent-security`'s blast-radius table (None/Low/Medium/High/Irreversible)
lands differently on each:

| Tool | Where it lands on the blast-radius table | Why |
| --- | --- | --- |
| File read | None -- fully reversible on its own | Reading does not corrupt anything. The risk it carries is not corruption; it is what the agent later does with what it read (see §2). |
| File write / edit | Low to Medium | Corrupts working-tree state, but a committed history means most mistakes are recoverable. Uncommitted work has no such safety net -- this is why an agent should never be the one deciding to discard uncommitted changes without a gate. |
| Shell execution | Spans the entire table | `ls`, `grep`, running the test suite are near-zero. A `curl` to an unknown host is network-adjacent (see below). `rm -rf`, a raw `dd`, or a package install that runs a postinstall script can be High or Irreversible. `ai-agent-security` already makes the general point that a general "run shell command" tool "is not one tool, it is every command that shell can run -- treat it as the union" -- a coding agent's shell access is the concrete instance of exactly that. |
| Git operations | Low (`status`, `diff`, `add`) through Irreversible (`push --force`, `reset --hard`, `branch -D`) | `git-guardrails` is this catalog's own shipped instance of mechanical enforcement for exactly the Irreversible row of this one category: a `PreToolUse` hook that inspects the literal shell command before it runs and blocks a named list of destructive git operations. It is a **strict deny-by-default binary gate, not a tiered confirmation system** -- a matched command is blocked outright, and the only way past a block is an explicit, out-of-band override configured ahead of time (a narrow per-repo `allow_patterns`/`disable_rules` entry, or a human setting `GIT_GUARDRAILS_DISABLE=1` for a supervised session), never a re-click in the moment. |
| Network / MCP tool calls | A separate risk surface, not an extension of the shell row | Transport security, tool authorization in front of dispatch, and audit logging for MCP-exposed tools are `mcp-server-security`'s domain in full -- do not improvise a redundant policy layer here. If the coding agent's tool set includes MCP servers (a linter-as-a-service, an internal ticket lookup, a deploy tool), scope and gate those per that skill, not by analogy to the file/shell rows above. |

The table is a starting map, not a substitute for the exercise:
`ai-agent-security`'s deployment checklist ("enumerate every tool the agent
can call... name the blast-radius tier... confirm the friction matches the
tier") should be walked once, concretely, against the specific tool grants a
given coding agent configuration actually has -- a general "shell access"
grant and a general "file write access" grant are each the union of many
possible actions, not one.

## 2. Secrets protection when filesystem read access is broad by design

A general web-facing agent's data-exposure problem is usually solved by
scoping *what it can read* narrowly -- `ai-agent-security` recommends
allow-lists over deny-lists for exactly this reason: a deny-list must
anticipate every sensitive path in advance and will always miss one. A coding
agent breaks that recommendation's usual justification, because its entire
value is reading whatever source file is relevant to the task at hand --
enumerating every legitimate file it might need to open in advance would
cripple it. This is the one place in this catalog where a **deny-list is the
correct, deliberate exception**, and it needs to be paired with a second
mitigation for what the deny-list cannot catch:

**a. Pattern-based exclusion for files that are entirely secret.** Configure
the agent's read scope (or the harness's own ignore mechanism) to deny read
outright on file patterns that are never legitimately part of a code-review
or editing task: `.env`, `.env.*`, `*.pem`, `*.key`, `.aws/credentials`,
`id_rsa`/`id_ed25519`, `kubeconfig`, `.npmrc`/`.pypirc` with embedded tokens.
This is a narrow, well-known set -- unlike the general case, a coding agent's
"never legitimately needed" file list is short and stable enough that a
deny-list does not have the usual failure mode of missing an unknown-unknown
sensitive path.

**b. Redaction/awareness for secrets embedded inside a file the agent
legitimately needs to read.** The pattern-based exclusion above does nothing
for a Terraform `.tfvars` file, a `docker-compose.yaml` with an inline
credential, or a config file that mixes ordinary settings with one secret
value -- excluding the whole file breaks the task, since the agent needs the
rest of that file's content. The mitigation here is not exclusion, it is
controlling what the agent is allowed to *echo back*:
`ai-agent-security` §2 already names commit messages, PR descriptions, and
error output surfaced to a user as the easiest-to-miss exfiltration vectors --
apply that specifically here: an agent explaining a config change should
describe the change ("added a database connection string"), never quote the
literal value back into a commit message, chat response, or log line, even
when the value came from a file it was legitimately allowed to open.

The two mitigations are complementary, not redundant: (a) stops the agent
from ever seeing a handful of known secret-only files at all; (b) bounds the
damage for the much larger set of ordinary files that happen to contain one
secret value mixed in with content the agent needs.

## 3. Review gates on a coding agent's own output

The sharpest version of `ai-agent-security` §3's blast-radius/friction
principle, applied to a coding agent specifically, is the gap between an
agent that **proposes a diff for a human to approve before it is applied**
(safest, slowest) and one that **auto-commits and auto-pushes** (fastest,
riskiest). Map concrete coding-agent actions onto that same table:

| Action | Tier | Gate |
| --- | --- | --- |
| Run a linter, formatter, or the existing test suite | None/Low | Auto-apply; log the result |
| Write to a scratch file or a throwaway branch | Low | Auto-apply; visible in the diff, cheap to discard |
| Commit to a local, non-shared branch | Low-Medium | Auto-apply is reasonable once the repo's own review culture expects commits to be squashed/reviewed before merge |
| Open a draft PR / merge request | Low-Medium | Auto-apply -- opening a PR is not merging one; a human still reviews before it lands |
| Merge or push to a shared/protected branch | High | Requires a human review gate naming the exact change -- this is the point where "agent proposes, human approves" should be a hard requirement, not a preference |
| Force-push, `reset --hard`, branch/tag deletion | Irreversible | Already covered mechanically by `git-guardrails` -- do not additionally rely on a review-gate convention here, since the point of that hook is that it does not depend on the agent choosing to ask |

The practical rule for a coding agent: the closer an action gets to something
another person could be affected by without reviewing it first (a shared
branch, a released package, a running deployment), the more it belongs in the
"propose a diff, wait for approval" mode rather than the "just do it" mode --
regardless of how mechanically safe the individual command looks in
isolation. A `git push` to a feature branch nobody else has touched and a
`git push` to `main` are the same shell tool call with entirely different
blast radii; the gate has to be keyed on the target, not the command name.

## 4. Multi-agent / subagent coding workflows

A supervisor coding agent that dispatches subagents for parallel or
specialized work -- a real pattern in this catalog's own tooling
(`agent-platform-design`'s Pattern 4 describes exactly this: "staffops
subagent model (already implemented -- fan-out/fan-in with `summary`
tool)") -- inherits
`ai-agent-security` §4's warning without modification: **a subagent's tool
grant should be derived from its specific subtask, not inherited from the
supervisor's full toolset.** A subagent spawned to "write tests for module
X" needs read access to that module and its test directory, and write access
to the test files it is producing -- it does not need the supervisor's shell
access to `push`, its access to unrelated modules, or its network/MCP tool
grants, and giving it those "in case it needs them" reproduces the exact
over-grant `ai-agent-security` names as the common mistake. Re-derive the
subagent's tool list per dispatch; do not select from a fixed, wide role
just because the same supervisor happens to spawn several kinds of
subagents.

## 5. What this does not cover

- **The general adversarial threat model for any tool-using agent** --
  exfiltration mechanics, the full blast-radius framework, the deployment
  checklist -- is `ai-agent-security` in full; this skill applies that
  framework to one tool set rather than restating it.
- **The mechanism that blocks destructive git commands** is `git-guardrails`
  -- this skill cites it as the concrete example of mechanical enforcement
  for one tool category and does not re-describe its rule table, tokenizer,
  or override syntax.
- **MCP transport security, tool authorization, and audit logging** are
  `mcp-server-security`'s domain in full, including for MCP-exposed tools a
  coding agent happens to call.
- **Detecting or defending against instructions smuggled into content the
  agent reads** (a manipulated file, a crafted commit message, a poisoned
  dependency's postinstall script) is the input side of the threat model
  `ai-agent-security` and `prompt-injection-defense` cover -- this skill is
  about the permission surface the agent has once it decides to act, not
  about why it decided to.

## Anti-patterns

- Granting a coding agent an unscoped "shell access" or "file write access"
  permission without tiering the specific commands/paths that grant actually
  allows -- a general shell tool is the union of every command it can run,
  not one risk.
- Treating a system-prompt instruction ("don't force-push," "never commit
  secrets") as sufficient control for an irreversible action instead of
  wiring the mechanical enforcement `git-guardrails` demonstrates for git and
  the equivalent for any other destructive tool category the agent has.
- Excluding an entire config or infrastructure file from the agent's read
  scope because it contains one secret value, when the rest of the file's
  content is legitimately needed for the task -- use redaction/awareness for
  embedded secrets instead of breaking the task.
- Assuming a deny-list of secret file patterns is sufficient on its own,
  with no mitigation for secrets embedded inside files the agent must
  legitimately read.
- Letting an agent auto-commit *and* auto-push to a shared or protected
  branch by default, with no diff-review step, on the reasoning that CI will
  catch anything wrong -- CI validates correctness, not whether the change
  should have shipped without a human looking at it first.
- Gating every coding-agent action identically (always auto-apply, or always
  require approval) instead of keying friction to the action's actual
  target -- a push to a private feature branch and a push to `main` are the
  same tool call with different blast radii.
- Handing a dispatched subagent the supervisor's full tool set "in case it
  needs it" instead of deriving its grant from the specific subtask it was
  spawned to perform.
- Assuming `git-guardrails` alone is a complete guardrail story for a coding
  agent -- it covers one tool category (git shell commands) mechanically; the
  file-read, file-write, and review-gate surfaces above still need their own
  configuration.
