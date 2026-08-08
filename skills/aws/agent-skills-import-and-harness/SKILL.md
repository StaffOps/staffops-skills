---
name: agent-skills-import-and-harness
description: Use when importing assets to the agentspace or running the behaviour harness. Carries every API constraint that cost a failed attempt — sourceUrl being GitHub-only, base64 inline blobs, the extension allowlist, agent_type singular vs plural, the userType enum, the event-stream shape — plus how typed executions are created and what the harness cannot reach.
---

# Importing and validating

Every constraint here cost a failed attempt. Recorded so it costs nobody another one.

## `sourceUrl` cannot import this repo

GitHub-only, for two independent reasons:

1. The parser needs exactly `owner/repo` before `/tree/`. This project is nested four levels (`<org>/<nested-path>/aws-devops-agent-skills`), so it can never parse — `Invalid GitHub URL format`
2. Even with a two-segment path, the host needs a GitHub association — `No GitHub access is configured for the repository's host`

GitLab's `/-/tree/` separator also breaks the parse. **Use `zip`.**

Cost of that: no **Sync** button and no *Last synced* in the Operator Web App. Re-run the import script after a merge.

## Import constraints

| Constraint | Detail |
|-----------|--------|
| Blob encoding | Base64 **inline** in the JSON. `fileb://` is rejected for document-typed parameters. Write the payload to a file to stay clear of `ARG_MAX` |
| Zip layout | `SKILL.md` at the **zip root** — zip the directory contents, not the directory |
| Extension allowlist | `.md .txt .json .yaml .yml .xml .csv .tsv .html .htm` + images + `.pdf`. An extensionless `references/.gitkeep` failed 7 skills; exclude `*.gitkeep` at any depth |
| `GENERIC` is exclusive | Cannot be combined with other agent types — it already means all of them |
| Metadata key differs by asset type | `skills` use the `agent_types` **array**; `agents_md` uses `agent_type` **singular string**. Using the array on `agents_md` fails with `agent_type is required for AgentsMd knowledge items` |
| Limits | 6 MB and 100 files per skill; 200 skills per agentspace |
| After import | `name` and `description` become read-only in the UI — they are owned by `SKILL.md` |
| `create-asset` does not upsert | Look up the `assetId` by name first, then `update-asset` |
| `update-association` replaces the **entire** configuration | Capture the original, rebuild minus what you are removing, diff, then send. A partial payload breaks tool access for the whole association |

## The agent_types enum is not the UI labels

| API | Web App label |
|-----|---------------|
| `GENERIC` | Generic |
| `CHAT` | **On-demand** |
| `INCIDENT_TRIAGE` | Incident Triage |
| `INCIDENT_RCA` | Incident RCA |
| `INCIDENT_MITIGATION` | Incident Mitigation |
| `PREVENTION` | **Evaluation** |

`ON_DEMAND` and `EVALUATION` are rejected. Also valid, unused here: `CHANGE_REVIEW`, `CHANGE_RELEASE`, `QUALITY_ASSURANCE_TESTING`, `RELEASE_SHEPHERD`, `RELEASE_READINESS_REVIEW`, `RELEASE_TESTING`, `SYSTEM_LEARNING`, `INCIDENT_UI`, `GRADER`.

**Technique worth reusing:** extract an undocumented enum by submitting an invalid value and reading the constraint error. Faster and more reliable than searching docs. Use a reversible operation on a disposable resource — `update-asset` on a test asset, never `create-*`.

## Driving the agent

`SendMessage` returns an event stream, which is why it is **absent from the AWS CLI** and present in boto3.

```
CreateChat(agentSpaceId, userId, userType)   -> executionId
SendMessage(agentSpaceId, executionId, content, context, userId, assetIds)
```

- `userType` enum is `[GAIA, MIDWAY, STATIC, IAM, IDC, IDP]`. `HUMAN` is rejected; `IAM` is right for an STS caller
- `assetIds` pins specific assets to a message, which removes the ambiguity of whether a skill loaded or the answer came from general knowledge
- `context` carries only `currentPage`, `lastMessage`, `userActionResponse` — it does **not** select an agent type

### Event-stream shape

`contentBlockStop` carries an **empty** `text`. The payload only exists in deltas, nested one level: `textDelta.text` and `jsonDelta.partialJson`.

Block types: `text`, `final_response`, `tool_summary`, `context_usage`, `chat_title`, `load_skill`, `run_subagent`, `user_prompt`.

Tool calls live in `tool_summary` as accumulated `partialJson`. The `name` field is the wrapper (`invoke_user_tool`, `search_user_tools`, `skill_read`); the MCP tool the operator cares about is `input.tool_name`. Skill loads carry `input.skill_id`.

Credentials: `harness/run.sh` resolves them on the host because boto3 inside a container cannot refresh an SSO session — mounting `~/.aws` is not enough.

## Typed executions

`create_chat` only opens a CHAT/GENERIC session. Typed work comes from **`create-backlog-task`**. The four `taskType` values are not equally reachable:

| `taskType` | How to reach it |
|-----------|-----------------|
| `INVESTIGATION` | A prose `description`. Works directly |
| `EVALUATION` | **Goal-driven.** Rejects prose: *"Evaluation task must have a json description containing valid goal_id"*. Use `list-goals`. The existing goal has `evaluationSchedule: rate(7 days)`, so `PREVENTION` is already exercised weekly — read that run instead of forcing one |
| `RELEASE_READINESS_REVIEW` | **MR-triggered.** A prose description fails in under a second with no execution. Real ones carry `{"agentInput": {"repository", "head_sha", "head_branch", "merge_request_iid", "source": "gitlab"}}` — so opening an MR on an associated project is how you exercise it |
| `RELEASE_TESTING` | Not attempted |

**The `agents_md` ARE applied.** The `utilization` record reports `{"agents_md": {"utilization": 2.4}}` on typed executions. The runtime `agentType: "ops1"` / `agentSubTask: "oncall"` is an internal label, not evidence of inertness — that misreading cost three attempts.

### Reading the journal

Two traps, both of which silently return nothing:

- **Paginate.** `--limit` caps at 100 and a deep investigation produced 124 records, with the conclusion on page 2. Follow `nextToken` or you will conclude the agent returned nothing.
- **The record schema varies by task type *and by depth*.** Parse for whichever is present:

  | Execution | Records |
  |-----------|---------|
  | Shallow `INVESTIGATION` | `utilization`, `investigation_result`, `message` |
  | Deep `INVESTIGATION` | `utilization`, `symptom`, `finding`, `investigation_gap`, `investigation_summary_md` |
  | `RELEASE_READINESS_REVIEW` | `usage_metrics`, `release_analysis_report`, `evidence_based_risk_analysis_report`, `aggregation_decision` |

`utilization` also names the loaded skill bundles, which is far more reliable than grepping the transcript. It does **not** reveal which `agents_md` loaded — their content is never echoed.

Creating a backlog task starts a **real, billed investigation** — a deep one ran 16 minutes. Get a deliberate go-ahead.

## Harness discipline

Assert on **observable behaviour** — tools invoked, skills loaded — never on prose. Text matching is language-brittle: the agent answers in the user's language, and one assertion failed for matching "approval" against a Portuguese reply while the gate had held perfectly.

Do not count `search_user_tools` and `invoke_user_tool` against a tool budget; they are latent-tool overhead, not investigative choices.

Costs ~$0.0083/agent-second. Sequential on purpose — the quota is 10 concurrent chats and a parallel run competes with real users. A 15-case pass is several dollars.

Keep removed tools listed in `MUTATING_TOOLS` so a reappearance fails a case instead of passing silently because the name stopped being watched.

## When NOT to use

- Debugging a skill that's already imported but not working — use `agent-skills-debugging`
- Running the harness after import (interpreting results) — use `agent-skills-harness-guide`
- Building sandbox code bundles — use `agent-skills-sandbox-development`

## Decision tree

```
├── Import failing?
│   ├── sourceUrl error → Use zip (GitLab/nested paths unsupported)
│   ├── ValidationException → Check: blob base64, extension allowlist, zip layout
│   └── agent_type error → Singular string for agents_md, array for skills
├── Updating an existing skill?
│   └── Re-run import script (no sync button — sourceUrl is GitHub-only)
└── Validating post-import?
    └── list-assets → confirm ACTIVE status → run harness case
```

## Related skills

- `agent-skills-debugging` — when the skill is imported but produces wrong output
- `agent-skills-harness-guide` — how to run and interpret the behaviour harness
- `agent-skills-sandbox-development` — filesystem layout and packaging for sandbox skills
- `agent-skills-new-skill-checklist` — full creation workflow that includes import as one step
