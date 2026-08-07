---
name: how-this-agent-works
description: "Understand this agent's skills and steering."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [how, this, agent, works, workflows]
    category: workflows
    related_skills: [agent-platform-design]
---
# How This Agent Works

Meta-skill: how the staffops agent is structured, how it loads knowledge, and how to navigate or modify this repository.

---

## When to Use

Use when needing to understand the staffops agent's own architecture — how it loads steering/skills/context, how overlays work, how subagents are configured, and how to navigate or modify this repository.

## Arquitetura de Carregamento

```
Session Start
│
├── ALWAYS loaded (resources in the JSON):
│   ├── steering/**/*.md        ← rules (all of them, every session)
│   ├── context/*.md            ← project state
│   └── skills/**/SKILL.md      ← METADATA only (YAML frontmatter)
│       (full content loaded on demand when relevant)
│
├── Overlay (if configured):
│   ├── overlays/<org>/steering/*.md   ← org-specific rules
│   ├── overlays/<org>/context/*.md    ← org-specific state
│   └── overlays/<org>/skills/**/SKILL.md  ← org-specific skills
│
└── prompt.md                   ← system prompt (persona, response rules)
```

### What is loaded when

| Type | When | Context weight |
|------|--------|-----------------|
| `steering/` | **Always** — every session, every prompt | ~50KB (16 files) |
| `context/` | **Always** — project state | ~4KB (1 base file) |
| `skills/` metadata | **Always** — frontmatter with `name` + `description` | ~5KB (55 descriptions) |
| `skills/` full content | **On demand** — when the topic is relevant | 5-18KB per skill |
| `overlays/` | **Always** — if an overlay is configured | Varies by org |
| `learnings/` | **Not loaded automatically** — consulted manually | — |
| `archive/` | **Never** — preserved legacy material | — |

---

## Directory Hierarchy

```
staffops_agent_definition/
├── agents/
│   ├── mainagent/          ← primary agent (staffops)
│   │   ├── staffops.json   ← config: resources, tools, crew
│   │   ├── prompt.md       ← system prompt
│   │   └── meta.yml        ← name + description
│   ├── subagents/          ← 10 specialists
│   │   └── <name>/
│   │       ├── <name>.json
│   │       ├── prompt.md
│   │       └── meta.yml
│   └── templates/          ← .json.tmpl (SSOT for generating the JSONs)
├── steering/               ← rules ALWAYS active (generic)
├── skills/                 ← on-demand knowledge (9 categories)
│   └── <category>/<name>/SKILL.md
├── context/                ← project state (generic)
├── learnings/              ← captured knowledge (4 categories)
├── overlays/<org>/         ← per-organization customizations
│   ├── steering/
│   ├── skills/
│   ├── context/
│   └── learnings/
├── scripts/                ← sync-to-claude.sh
├── archive/                ← legacy material (inactive)
├── README.md
├── TODO.md
├── CHANGELOG.md
└── setup-agents.sh         ← installs via symlinks
```

---

## How the Agent Decides What to Do

### Decision flow by task type

```
Task received
│
├─ Is it cross-domain? (touches 2+ specialties)
│   └─ YES → fan out via the subagent tool (parallel-execution.md)
│
├─ Is it a single specialist's domain?
│   └─ YES → delegate to the subagent (inter-agent-collaboration.md)
│
├─ Is it trivial / already in the current conversation?
│   └─ YES → execute directly
│
└─ Does it need specific knowledge?
    └─ YES → the skill is loaded on demand by the LLM
```

### Available subagents

| Subagent | Domain |
|----------|---------|
| `observability` | VictoriaMetrics, OTel, Tempo, Loki, Grafana, alerts |
| `gitops` | ArgoCD, Helmfile, ApplicationSets, Rollouts |
| `security` | Kyverno, cosign, SBOM, FTR, IAM audits |
| `sre` | SLI/SLO, error budgets, incidents, runbooks |
| `aws` | EKS, IAM, networking, RDS, S3, Lambda |
| `finops` | Cost Explorer, CUR, Savings Plans, rightsizing |
| `dev` | .NET / Python / Go — implementation + testing |
| `documentation` | MkDocs, ADRs, API docs |
| `anomaly-detection` | Detection rules, ML, alert tuning |
| `code-review` | Quality gate before commits |

---

## Steering vs Skills vs Context

| Concept | Purpose | Example |
|----------|-----------|---------|
| **Steering** | Rules the agent MUST always follow | "Read-only on K8s by default" |
| **Skill** | Deep knowledge about ONE topic | "How to configure VMAlert" |
| **Context** | Current project/environment state | "Existing clusters and endpoints" |
| **Learning** | Empirical discovery from past sessions | "Workaround for bug X in OTel" |

### When each one is consulted

- **Steering**: before ANY action (these are the guardrails)
- **Skill**: when the specific topic comes up in conversation
- **Context**: when environment/project data is needed
- **Learning**: when debugging or facing a recurring pattern

---

## Overlay System

Overlays add org-specific content WITHOUT modifying the base:

```
base (generic)          +  overlay/<org> (org-specific)
─────────────────────      ───────────────────────────
steering/k8s-safety.md     steering/aws-tag-policies.md
steering/git-conventions   steering/gitlab-branch-flow.md
skills/aws/eks-management  skills/infrastructure/helm-chart-app
context/STAFFOPS.md        context/INFRASTRUCTURE.md
```

**Rule**: anything company-specific (names, URLs, roles, tags) goes in the overlay. Anything valid for any organization goes in the base.

---

## How to Modify This Repository

### Adding a new steering doc

1. Create `steering/<name>.md` (if generic) or `overlays/<org>/steering/<name>.md` (if org-specific)
2. Format: markdown with `## CRITICAL:` for inviolable rules
3. It is picked up on the next session (glob `steering/**/*.md`)

### Adding a new skill

1. Create `skills/<category>/<name>/SKILL.md`
2. Required YAML frontmatter: `name` + `description` (starts with "Use when...")
3. Content: deep knowledge about the topic
4. It is detected via the glob `skills/**/SKILL.md`

### Adding a new subagent

```bash
mkdir agents/subagents/<name>
# Create meta.yml + prompt.md
./setup-agents.sh --generate  # generates the JSON
./setup-agents.sh             # installs the symlink
```

### Capturing a learning

At the end of troubleshooting or discovery, append to `learnings/<category>.md` following the format in `steering/knowledge-capture.md`.

### Promoting a learning

When a learning is referenced 3+ times → promote it to steering (if it became a rule) or a skill (if it became reusable knowledge).

---

## Cross-reference

- **How to delegate**: `steering/parallel-execution.md` + `steering/inter-agent-collaboration.md`
- **How to write specs**: `steering/spec-driven-workflow.md` + `skills/workflows/spec-writing`
- **How to capture knowledge**: `steering/knowledge-capture.md`
- **How to modify code**: `steering/dev-environment.md` (Docker-only) + `steering/code-quality.md`
- **How to commit**: `steering/git-conventions.md`
- **Full setup**: `README.md`, section "Automated Setup"

## When NOT to use

- **Using the agent** for normal tasks — you don't need to understand internals to ask questions.
- **Writing skills for a different agent platform** — this is specific to the staffops architecture.
- **Modifying steering rules** — read the relevant steering file directly instead.

## Related skills

- [skill-authoring](../workflows/skill-authoring/SKILL.md) — creating new skills for this agent.
- [skill-eval-harness](../workflows/skill-eval-harness/SKILL.md) — testing skill behavior.
- [session-handoff](../workflows/session-handoff/SKILL.md) — understanding context across sessions.
- [spec-writing](../workflows/spec-writing/SKILL.md) — writing specs that the agent follows.
