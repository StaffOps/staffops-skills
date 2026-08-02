---
name: ai-agent-security
description: "Bound agent tool abuse, exfiltration, and overreach."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [ai, agent, security, tool-abuse, exfiltration, least-privilege, subagent]
    category: ai
    related_skills: [agent-platform-design, git-guardrails, iam-patterns]
---
# AI Agent Security

The adversarial side of running an agent that can call tools, read and write
files, and execute shell commands: what goes wrong when that access is misused,
and how to bound the damage. `agent-platform-design` covers execution patterns
and architecture (cron/webhook/Slack/multi-agent/CI triggers, state management,
observability) — this skill deliberately does not repeat that. It also does not
cover defending against manipulated instructions arriving inside the input
itself, or the systematic methodology for testing an agent adversarially —
those are separate, narrower concerns from this one, which is about what the
agent's tool and permission surface allows once it acts, regardless of why it
decided to act that way.

## When to Use

Use when designing, reviewing, or hardening any agent that has tool access
beyond pure text generation — shell execution, file read/write, network
calls, cloud credentials, or the ability to dispatch other agents. Reach for
this specifically when:

- Granting a new tool to an existing agent ("does this tool let it do more
  than the task needs?")
- Reviewing an agent's permission/approval configuration before it goes live
- Designing a multi-agent or supervisor/subagent system where each agent's
  tool scope needs to be decided independently
- An agent will read data of one sensitivity level and has any path — network,
  file, commit message — that leaves the trust boundary
- Something the agent did was surprising, even if it was not obviously
  malicious (this is the signal that scoping was too broad, not that the
  agent is broken)

## The threat model: it does not require a malicious user

The instinctive mental model is "an attacker crafts a prompt to trick the
agent." That is one path in, but it is not the interesting part of the threat
model for an agent that already has broad tool access. The interesting part
is this: **an agent with a capability will eventually use that capability**,
because some instruction — from a user who mistyped, from a file it was
asked to summarize, from a ticket description, from a config value it read —
will look enough like a legitimate reason to use it. The security question is
never "will someone try to trick it," it is "what is the worst thing this
agent can do with the tools it currently has, assuming the instruction it
acts on turns out to be wrong." Design for that worst case, not for the
absence of bad actors.

This reframes the job from "detect bad instructions" (a losing, adversarial
arms race handled elsewhere) to "bound what a wrong instruction can cost"
(a tractable, structural problem — this skill).

## 1. Tool-abuse: the shell/file/network agent as a worked example

An agent with shell access, file access, and network access is, structurally,
indistinguishable from a person with a terminal who does exactly what they
are told, instantly, without pausing to think "wait, why would I do that."
The danger is not exotic — it is the same command an engineer would type by
accident, except the agent will type it immediately and without hesitation
the moment an instruction (however it arrived) implies it should.

`git-guardrails` in this catalog is a concrete, already-shipped instance of
the correct defense pattern for exactly this problem: a `PreToolUse` hook
inspects every shell command *before* it runs and denies a specific list of
destructive git operations outright (`push --force`, `reset --hard`,
`clean -f`, forced branch deletion, tag deletion) unless an explicit,
out-of-band override is configured -- it is a deny-by-default gate, not a
tiered confirmation prompt. The generalizable lesson from that skill is not
about git specifically -- it is the shape of the fix: **enforcement at the
point of execution, mechanical and outside the model's own judgment, not an
instruction telling the agent "please be careful."** A system prompt that
says "never force-push" is a
preference the model holds in its context; a hook that inspects the actual
command string and blocks it is a control that holds regardless of what the
model currently believes it should do. Apply the same shape to every category
of destructive tool call the agent has access to — file deletion, resource
termination in a cloud console, DROP/TRUNCATE in a database tool — not just
the one git already solved.

The distinction that matters when scoping a new tool: is the action
**reversible** (a read, a `git status`, a dry-run) or does it have **lasting
effect** (a write, a delete, a push, a spend)? Only the first category should
ever execute without a gate.

## 2. Data exfiltration: read access plus an output path is a covert channel

An agent does not need to be compromised to leak data. It only needs two
things to be simultaneously true: it can **read** something sensitive, and
it has **any** path that leaves the trust boundary — a web request, a file
write into a folder that syncs elsewhere, a commit message, a support-ticket
comment, a Slack message to a public channel. Combine those two and the agent
is a covert channel even with zero malicious intent on anyone's part: an
instruction that looks entirely benign ("summarize this incident and post it
to #status") can carry a secret value straight out of the environment if that
secret was in whatever the agent read to write the summary.

This is worth naming explicitly because it does not look like an attack when
it happens — there is no injected payload to point at afterward, just a
credential that ended up somewhere it should not have because the agent had
both halves of the channel open at once.

**Concrete vectors to check for, in order of how easy they are to miss:**

| Vector | How it leaks | Why it is easy to miss |
| --- | --- | --- |
| Commit messages / PR descriptions | Agent quotes a config value, env var, or log line verbatim while explaining a change | Looks like normal, helpful commit hygiene |
| Outbound HTTP (webhook, API call, `curl`) | Agent includes file contents or command output as a request body/query param | The destination URL itself may be legitimate (a real Slack webhook, a real ticket API) |
| File writes to a synced or shared path | Agent writes scratch output into a directory that syncs to cloud storage, a shared drive, or another repo | The write itself is not to an "external" destination by any naming convention |
| Error messages / logs surfaced back to the user | Agent includes a stack trace or debug dump that happens to contain a connection string | Debug output is assumed safe because it is "just for troubleshooting" |
| Chained tool calls | Read a low-sensitivity file that references a path to a high-sensitivity one, then read that too, then act on it | Each individual step looks authorized; only the sequence is not |

**Primary mitigation: least-privilege tool scoping.** Do not rely on
output filtering as the first line of defense — filtering catches known
shapes of secrets (a key pattern, a PII regex) and misses everything else.
The control that actually closes the channel is denying the *combination*:
if a tool or task genuinely needs to read a sensitive data source, it should
not simultaneously hold a tool that can write to an unbounded destination
(arbitrary URL, arbitrary file path, arbitrary recipient). Split the task
across two scopes if it needs both — one that reads and produces a
structured, reviewed result, and a separate step (possibly a different
agent, see §4) that only handles the already-vetted output.

Practical scoping levers, cheapest to apply first:
- **Path allow-lists**, not deny-lists, for file read/write tools — a
  deny-list must anticipate every sensitive path in advance; an allow-list
  only needs to name what the task actually touches.
- **Egress allow-lists** for any tool that makes a network call — name the
  specific destinations the task needs, not "internet access."
- **Read/write separation** — a tool that reads a secret store should not be
  the same tool, or the same invocation, that can post externally.
- **Short-lived, scoped credentials** over long-lived broad ones (mirrors
  the IRSA/OIDC pattern for non-agent workloads — see `iam-patterns` for the
  underlying AWS mechanics when the agent's tools include cloud actions).

## 3. Approval gates: escalating friction by blast radius, not a single on/off switch

Not every tool call deserves the same amount of friction, and treating them
identically produces the worst of both outcomes: gate everything, and users
click "approve" reflexively without reading, which defeats the gate; gate
nothing, and there is no backstop at all. The general principle is to score
actions by **blast radius** — how hard is this to undo, and how far does its
effect reach — and let friction scale with that score:

| Blast radius | Example | Appropriate friction |
| --- | --- | --- |
| None / fully reversible | Read a file, run a query, `git status`, dry-run/plan | No gate — this is what makes an agent useful |
| Low, easily reverted | Write to a scratch path, create a draft, open (not merge) a PR | Proceed, but log it |
| Medium, reversible with effort | Merge to a non-protected branch, restart a service, scale a deployment | Confirmation prompt, one click |
| High, hard or slow to reverse | Push to a protected branch, delete a resource, modify IAM, spend above a threshold | Explicit confirmation naming the exact action, plus a stated rollback path |
| Irreversible | Force-push over remote history, drop a database, delete a backup | Deny outright by default; require an explicit, out-of-band override, not just a re-click |

`git-guardrails` is the concrete example already in this catalog of the
Irreversible row implemented mechanically for one domain (git): deny by
default, require an explicit, out-of-band override to proceed. It does not
implement the High row's "confirmation naming the exact action plus a
rollback path" -- that tier still needs a different mechanism (a
human-in-the-loop prompt, not a mechanical block) to be built per tool
category. The pattern generalizes: decide the blast-radius tier for every
tool an agent has
*before* deployment, not reactively after the first incident, and make the
tier — not the tool's name — the thing that determines whether it needs a
gate. A new tool that happens to be able to delete something inherits the
same "high" tier as every other deletion tool, even if nobody has thought
to add it to a list yet.

## 4. Multi-agent risk: a supervisor is only as scoped as its widest subagent

A supervisor agent that dispatches subagents for parallel or specialized
work introduces a failure mode that does not exist in a single-agent system:
**the subagent's tool access is a delegation, and delegation is easy to
over-grant.** The common mistake is giving every subagent the supervisor's
full tool set "to be safe" or "in case it needs it," reasoning that the
supervisor is trusted so its children must be fine too. That reasoning
breaks down for exactly the reason §1 and §2 exist — a subagent that receives
a manipulated or simply mistaken instruction (from the supervisor's own
imperfect task description, from data it reads mid-task, from a
misunderstanding of scope) now has the blast radius of the whole system, not
of the one task it was spawned to do.

Concretely, what goes wrong:
- A subagent spawned to "summarize the logs in this directory" is given
  filesystem write and network access because the supervisor's own
  permission set includes them — the summarization task needed neither.
- A subagent researching one service is handed credentials scoped to the
  entire account because provisioning per-subagent credentials felt like
  overhead — a mistake in that one subagent's reasoning now has account-wide
  reach.
- Results from an over-scoped subagent are trusted by the supervisor without
  the same scrutiny a top-level user instruction would get, because "it came
  from our own subagent" is treated as inherently safe.

**Mitigation: scope each subagent to only what its specific task needs,
every time, not to the union of what the system as a whole can do.** This
should feel like re-deriving the tool list per dispatch, not selecting from
a fixed subagent role — a "read-only research subagent" and a "deploy
subagent" are different enough in blast radius that they should never share
a permission set just because the same supervisor spawns both. Verify a
subagent's output the same way you would verify an external tool's output —
trust in the supervisor does not transitively make a wider-scoped delegate
safe.

## 5. Deployment review checklist

Before an agent with tool access goes live (or before adding a new tool to
one already running), walk this list. It is meant to be answered concretely
per tool, not agreed with in the abstract.

- [ ] **Enumerate every tool** the agent can call, including ones added
      incidentally (a general "run shell command" tool is not one tool, it
      is every command that shell can run — treat it as the union).
- [ ] **For each tool, name the blast-radius tier** (§3 table) and confirm
      the friction matches the tier — no high/irreversible-tier action
      executes without an explicit gate.
- [ ] **For each tool with write or network capability, name the exact
      destination scope** — path allow-list, egress allow-list, specific
      API endpoints — and confirm it is an allow-list, not a deny-list.
- [ ] **Cross-reference read access against write/network access**: does any
      single task, tool combination, or subagent hold both a sensitive read
      and an unbounded egress path at the same time (§2)? If yes, split it.
- [ ] **Check credential lifetime and scope** — no long-lived, broadly
      scoped credentials where a short-lived, narrowly scoped one would do
      (see `iam-patterns` for the AWS-specific mechanics).
- [ ] **For every subagent/delegate**, confirm its tool set was derived from
      *its* task, not inherited from the supervisor's full set (§4).
- [ ] **Confirm destructive-action enforcement is mechanical**, not
      prompt-based — a hook, a policy check, or a gate the model cannot
      talk itself past, following the `git-guardrails` pattern, for every
      category of destructive tool call the agent has, not only the one
      that already has a hook.
- [ ] **Confirm there is an audit trail** for every tool call that changes
      state — what ran, with what arguments, when, and what triggered it —
      independent of the agent's own conversational transcript.
- [ ] **Confirm a kill switch or equivalent circuit-breaker exists** and has
      been tested, not just documented, before the agent runs unattended.
- [ ] **Re-run this checklist whenever a tool is added**, not only at initial
      launch — the most common way scope creep happens is one "just this one
      extra tool" addition at a time, each individually reasonable.

## Anti-patterns

- Relying on the system prompt ("never delete production data") as the only
  control for an irreversible action — a preference the model holds is not
  an enforcement mechanism; see `git-guardrails` for what mechanical
  enforcement looks like.
- Gating every tool call identically regardless of blast radius — trains
  users to click through confirmations without reading them, which defeats
  the gate for the one action that actually needed it.
- Treating output filtering (secret/PII regex scanning) as sufficient
  defense against exfiltration instead of denying the read-plus-egress
  combination in the first place — filters only catch known shapes.
- Granting a subagent the supervisor's full tool set "in case it needs it"
  instead of deriving its scope from the specific task it was dispatched
  for.
- Trusting a subagent's output without the scrutiny a top-level instruction
  would get, on the reasoning that it "came from our own agent."
- A deny-list of dangerous file paths or commands instead of an allow-list —
  a deny-list must anticipate every sensitive path in advance and will
  always miss one; an allow-list only needs to name what the task actually
  touches.
- Long-lived, broadly scoped credentials handed to an agent for
  convenience, where a short-lived, narrowly scoped one would satisfy the
  same task.
- Adding tools to an agent one at a time without re-running the deployment
  checklist, so scope creep accumulates invisibly across many "reasonable"
  individual additions.
- No audit trail independent of the agent's own transcript — if the only
  record of what happened is the conversation the agent itself produced, a
  wrong or manipulated action leaves no way to reconstruct what actually
  ran.
