---
name: jira-conventions
description: "Write Jira issues with consistent conventions."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [jira, conventions, workflows]
    category: workflows
    related_skills: [mkdocs-conventions]
---
# Jira Conventions (<org>)

Standards for writing and managing Jira tickets at <org>.

## When to Use

Jira ticket conventions and templates for <org>. Use when creating issues, writing user stories, formatting acceptance criteria, or planning sprints. Will be expanded with <org>-specific project keys and workflows after MCP Atlassian integration. Covers issue types, JQL patterns, ticket templates, descriptions, links.

## Issue types

| Type | When to use |
|------|-------------|
| **Story** | User-facing feature with business value |
| **Task** | Work item without direct user value (refactor, infra, docs) |
| **Bug** | Defect in existing functionality |
| **Epic** | Large initiative spanning multiple stories |
| **Spike** | Time-boxed investigation / research |
| **Sub-task** | Breakdown of a Story/Task |

## Title format

### Story
```
As a <role>, I want <capability> so that <benefit>
```

Or shortened:
```
[Domain] Capability description
```

Examples:
- `As a developer, I want auto-instrumentation so that I don't write boilerplate`
- `[Telemetry] Add Kafka instrumentation to <org> OTel Helper`

### Task
```
[Domain] Action verb + object
```

Examples:
- `[Infra] Migrate Fluent Bit to OTel filelog receiver`
- `[Docs] Add MkDocs site for <org> OTel Helper`
- `[CI] Add cosign signing to all Harbor image pipelines`

### Bug
```
[Domain] What's broken when X
```

Examples:
- `[Telemetry] Traces missing `service.namespace` label after k8sattributes update`
- `[Helm] vmalert values not rendered when external_alert_source has nested Go template`

## Description templates

### Story template

```markdown
## Background
Context — why this matters.

## User story
As a <role>, I want <capability> so that <benefit>.

## Acceptance criteria
- [ ] Given X, when Y, then Z
- [ ] Given A, when B, then C

## Out of scope
What this story does NOT cover.

## Technical notes
Implementation hints (not prescriptive).

## Definition of done
- [ ] Code merged to main
- [ ] Tests passing (unit + integration)
- [ ] Docs updated (README, API docs)
- [ ] Demo'd in standup
```

### Task template

```markdown
## Description
What needs to be done.

## Why
Justification.

## Steps
1. Step 1
2. Step 2

## Validation
How we'll know it's done.

## Links
- [Related doc](link)
- [Related Jira](link)
```

### Bug template

```markdown
## Summary
1-2 sentences.

## Steps to reproduce
1. ...
2. ...

## Expected behavior
What should happen.

## Actual behavior
What happens instead.

## Environment
- Cluster: dev / prd
- Service: <name>
- Version: <commit-sha>

## Logs / screenshots
```
<paste relevant excerpt>
```

## Severity
- **S1**: production down, no workaround
- **S2**: production degraded
- **S3**: minor issue, workaround exists
- **S4**: cosmetic / nice-to-have

## Trace / metric / log links
- [Tempo trace](link)
- [Grafana dashboard](link)
```

### Spike template

```markdown
## Question to answer
What we need to learn.

## Time-box
Max effort: <X days>

## Approach
What we'll investigate.

## Outcome
What we'll deliver:
- [ ] Decision document
- [ ] POC code (throwaway)
- [ ] Recommendation
```

## Acceptance criteria

### Use Given-When-Then

```
Given a user with role admin
When they request /admin/users
Then they receive 200 OK with the user list
```

### Or checkboxes for simpler cases

```markdown
- [ ] Endpoint /v1/orders/{id} returns 200 for valid IDs
- [ ] Returns 404 for non-existent IDs
- [ ] Returns 401 for unauthenticated requests
- [ ] Response schema matches OpenAPI spec
- [ ] Latency P95 < 200ms under normal load
```

## Estimation

### Story points (Fibonacci)
- 1 point: trivial (typo fix, simple config change)
- 2 points: small (1-2 hours)
- 3 points: medium (half day)
- 5 points: large (1-2 days)
- 8 points: very large — REVIEW: should be split
- 13 points: epic-sized — MUST be split

If a story is >8 points, break it down before working on it.

### Time estimates
Avoid hour estimates for stories — too brittle. Time estimates fit Tasks better.

## Linking issues

| Link type | When to use |
|-----------|-------------|
| **Blocks** | This issue blocks another from progressing |
| **Is blocked by** | Reverse of Blocks |
| **Relates to** | Soft relationship, FYI |
| **Duplicates** | Same as another issue |
| **Is duplicated by** | Reverse |
| **Caused by** | Bug X caused by change Y |

Always link related work — Jira's value is the graph, not isolated tickets.

## Labels

Use labels for:
- **Domain**: `telemetry`, `iam`, `networking`, `dba`
- **Type**: `tech-debt`, `security`, `compliance`
- **Quarter**: `q2-2026`, `q3-2026`
- **Status modifiers**: `blocked`, `at-risk`, `needs-design`

Don't use labels for:
- Things already in fields (priority, type, components)
- One-off tags only used once

## Components

Components map to logical product areas:
- `<org> OTel Helper / .NET`
- `<org> OTel Helper / Python`
- `Observability / Collector`
- `Observability / Grafana`
- `Anomaly Detection`
- `StaffOps Tools`

## JQL patterns

### My open issues
```jql
assignee = currentUser() AND statusCategory != Done
```

### Sprint backlog
```jql
project = OBS AND sprint in openSprints() ORDER BY priority DESC
```

### Stale tickets (no update in 30 days)
```jql
statusCategory != Done AND updated < -30d
```

### Bugs by severity
```jql
issuetype = Bug AND statusCategory != Done ORDER BY priority DESC, created ASC
```

### Linked to a release
```jql
fixVersion = "v1.2.0"
```

## Workflow states

Standard <org> workflow:

```
TO DO → IN PROGRESS → IN REVIEW → DONE
                          ↓
                       BLOCKED (any state)
```

### Transitions

- **TO DO → IN PROGRESS**: when you START work (not when you intend to)
- **IN PROGRESS → IN REVIEW**: PR submitted
- **IN REVIEW → DONE**: PR merged + AC validated
- **Any → BLOCKED**: external dependency stops you (link the blocker)

## Sprint hygiene

### At sprint start
- All planned issues have story points
- All issues have acceptance criteria
- Dependencies identified and linked

### During sprint
- Update status when YOU change it (not at standup)
- Add comments for blockers
- Keep tickets <8 points (split if needed)

### At sprint end
- Close completed tickets
- Move incomplete to backlog (don't auto-roll-over)
- Retro on what worked / didn't

## Ticket-to-PR linking

### In commit message
```
feat(otel): add gRPC instrumentation

DEVOPS-1234
```

### In PR description
```markdown
## Description
...

## Related
- DEVOPS-1234
- Closes DEVOPS-1235
```

GitLab/GitHub auto-link when project key + number appears.

## Future MCP integration

When MCP Atlassian server is added (see staffops `mcpServers` config), the agent will be able to:
- Create tickets from chat
- Update tickets with progress
- Search via JQL
- Link tickets to commits/PRs
- Generate sprint reports

Until then, use manual workflows.

## Roadmap for this skill

- [ ] Add <org>-specific project keys (after Fase 10 discovery)
- [ ] Add corporate workflow customizations (if any beyond standard)
- [ ] Add automation rules (e.g., auto-transition on PR merge)
- [ ] Add team-specific conventions (DEVOPS, OBS, INFRA project keys)

## Reference

- Atlassian best practices: https://www.atlassian.com/software/jira/guides/getting-started/best-practices
- JQL reference: https://confluence.atlassian.com/jirasoftwarecloud/advanced-searching-764478330.html
- Conventional Commits: https://www.conventionalcommits.org/
- Related: `git-conventions` (steering), `conventional-commits`, `git-advanced`
