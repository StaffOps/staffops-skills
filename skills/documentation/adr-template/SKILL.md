---
name: adr-template
description: "Write MADR architecture decision records."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [adr, template, documentation]
    category: documentation
    related_skills: [pipeline-template-apps]
---
# ADR Template

Architecture Decision Records (ADRs) capture **why** a decision was made, not just what was decided. They are the institutional memory for cross-cutting technical choices.

## When to Use

Use when writing Architecture Decision Records (ADRs) for projects. Covers MADR format, numbering, lifecycle, storage conventions, decision drivers, and copy-paste template.

## What is an ADR

An ADR documents a single architectural decision:
- **Context**: what forces are at play
- **Decision**: what was chosen
- **Consequences**: what trade-offs result

ADRs are **immutable once accepted** — if a decision changes, a new ADR supersedes the old one (never edit/delete).

## When to write an ADR

### Write an ADR when:

| Trigger | Example |
|---------|---------|
| Cross-cutting technology choice | "Use VictoriaMetrics over Prometheus" |
| Breaking change to shared infra | "Rename PRD-BATCH to BTC" |
| Deviation from corporate standard | "Use raw Deployment instead of Rollout for X" |
| New tool adoption | "Use apko over Dockerfile for base images" |
| Architecture pattern decision | "Istio Ambient over sidecar mode" |
| Security model change | "IRSA over node-level IAM roles" |
| Data format / protocol choice | "gRPC over HTTP for inter-service" |

### Do NOT write an ADR for:

- Trivial config changes (bump a version, change a port)
- Individual code refactors (rename a variable)
- Bug fixes
- Routine dependency updates

## Copy-Paste Template

Use `references/adr-template.md` — a streamlined, ready-to-fill ADR skeleton with:
- Status, date, context, decision drivers
- Considered options with pros/cons
- Consequences and risks
- "When this decision would be wrong" section (signals to re-evaluate)

```bash
cp references/adr-template.md docs/adr/NNNN-my-decision.md
# Replace NNNN with next sequential number
```
- Decisions already covered by existing ADRs

## MADR format

Use **Markdown Any Decision Records (MADR)** — a structured format with explicit sections.

### Required sections

| Section | Purpose |
|---------|---------|
| Title (H1) | Short decision statement |
| Status | Lifecycle state |
| Context and problem statement | What forces exist |
| Decision drivers | What criteria matter most |
| Considered options | What alternatives were evaluated |
| Decision outcome | What was chosen and why |
| Consequences | Good, bad, neutral outcomes |

### Optional sections

| Section | Purpose |
|---------|---------|
| Pros and cons of each option | Detailed comparison |
| Links | Related ADRs, issues, docs |
| More information | Implementation notes, timeline |

## Numbering and naming

Format: `NNNN-kebab-case-title.md`

```
docs/adrs/
├── 0001-use-bottlerocket-for-eks-nodes.md
├── 0002-apko-over-dockerfile-for-base-images.md
├── 0003-rename-prd-batch-to-btc.md
├── 0004-victoriametrics-over-prometheus.md
└── 0005-istio-ambient-over-sidecar.md
```

- Sequential numbering (never reuse numbers)
- Kebab-case title (lowercase, hyphens)
- Start from `0001`

## Storage

| Scope | Location |
|-------|----------|
| Project-specific | `<repo>/docs/adrs/` |
| Cross-cutting (org-wide) | `<workspace>/<central-docs-portal>/docs/adrs/` |

Cross-cutting decisions (affect multiple teams/repos) go in the corporate devops-docs MkDocs site. Project-specific decisions stay in the project repo.

## Lifecycle

```
proposed → accepted → [deprecated | superseded by NNNN]
```

| Status | Meaning |
|--------|---------|
| `proposed` | Under discussion, not yet decided |
| `accepted` | Decision made, in effect |
| `deprecated` | No longer relevant (context changed) |
| `superseded by ADR-NNNN` | Replaced by a newer decision |

- Never delete ADRs — mark as deprecated/superseded
- Link superseding ADR in the old one
- Link superseded ADR in the new one

## Conventions

- Language: **pt-BR** for corporate devops-docs ADRs, English for library/OSS repos
- Date format: `YYYY-MM-DD`
- Author: name + team/sigla (e.g., "DevOps/INFRA")
- Review: ADRs for `accepted` status require at least 1 reviewer from affected team
- MkDocs integration: ADRs in devops-docs are navigable via `nav:` in `mkdocs.yml`

## Full template (copy-paste ready)

```markdown
# ADR-NNNN: Title of decision

## Status

Proposed | Accepted | Deprecated | Superseded by [ADR-NNNN](NNNN-title.md)

- **Date**: YYYY-MM-DD
- **Author**: Name (Team/Sigla)
- **Reviewers**: Name1, Name2

## Context and problem statement

Describe the context and the problem or opportunity that motivates this decision.
What forces are at play? What constraints exist?

## Decision drivers

- **Driver 1**: description (e.g., "Must support multi-arch builds")
- **Driver 2**: description (e.g., "Minimize attack surface")
- **Driver 3**: description (e.g., "Team familiarity")

## Considered options

1. **Option A** — brief description
2. **Option B** — brief description
3. **Option C** — brief description

## Decision outcome

**Chosen option**: "Option B" because it satisfies drivers 1 and 2 with acceptable trade-offs on driver 3.

### Consequences

**Good**:
- Benefit 1
- Benefit 2

**Bad**:
- Trade-off 1
- Trade-off 2

**Neutral**:
- Side effect that is neither good nor bad

## Pros and cons of options

### Option A — brief name

- ✅ Pro 1
- ✅ Pro 2
- ❌ Con 1
- ❌ Con 2

### Option B — brief name (chosen)

- ✅ Pro 1
- ✅ Pro 2
- ❌ Con 1

### Option C — brief name

- ✅ Pro 1
- ❌ Con 1
- ❌ Con 2
- ❌ Con 3

## Links

- Supersedes: [ADR-NNNN](NNNN-title.md) (if applicable)
- Related: [ADR-NNNN](NNNN-title.md)
- Issue: GitLab issue URL
- Discussion: Slack thread / meeting notes URL
```

## Examples (illustrative)

### 0001-use-bottlerocket-for-eks-nodes.md

> **Context**: Need a container-optimized OS for EKS nodes. Options: Amazon Linux 2, Ubuntu, Bottlerocket.
>
> **Decision drivers**: minimal attack surface, automatic updates, immutable rootfs.
>
> **Chosen**: Bottlerocket — purpose-built for containers, immutable, auto-updates via orchestrator.

### 0002-apko-over-dockerfile-for-base-images.md

> **Context**: Base images built with Dockerfile have unnecessary packages, CVEs, and are hard to audit.
>
> **Decision drivers**: SBOM by default, minimal packages, multi-arch native, reproducible builds.
>
> **Chosen**: apko — declarative YAML, produces minimal images with built-in SBOM, multi-arch by default.

### 0003-rename-prd-batch-to-btc.md

> **Context**: `PRD-BATCH` / `PRD_BATCH` is inconsistent (hyphen vs underscore) and confusing with `PRD`.
>
> **Decision drivers**: clarity, consistency, shorter tag values, backward compatibility.
>
> **Chosen**: Rename to `BTC`. Aliases `PRD-BATCH` and `PRD_BATCH` accepted during migration.

## Anti-patterns

- ❌ **Empty ADR**: title + status only, no context or drivers (useless)
- ❌ **No decision drivers**: "we chose X" without explaining WHY X over Y
- ❌ **Post-hoc ADR**: written months after the decision just to fill a checkbox (loses the real reasoning)
- ❌ **ADR as spec**: 10-page document with implementation details (ADR captures the decision, not the implementation)
- ❌ **Single option ADR**: only one option listed — if there was no choice, there's no decision to record
- ❌ **Editing accepted ADRs**: changing the decision after acceptance (write a new superseding ADR instead)
- ❌ **ADR for trivial choices**: "use port 8080" or "name the variable X" (not architectural)
- ❌ **No consequences section**: every decision has trade-offs — if you can't name any, you haven't thought it through

## Reference

- MADR: https://adr.github.io/madr/
- ADR GitHub org: https://adr.github.io/
- Nygard original post: https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions
- Corporate docs: `<workspace>/<central-docs-portal>`
- Related: `markdown-docs`, `mkdocs-conventions`

## When NOT to use

- **Trivial decisions** (variable naming, minor config tweaks) — ADRs are for decisions with non-trivial trade-offs.
- **Feature specs** (requirements, design, tasks) — see [spec-writing](../workflows/spec-writing/SKILL.md).
- **Operational runbooks** — different purpose; see [runbook-authoring](../sre/runbook-authoring/SKILL.md).

## Related skills

- [spec-writing](../workflows/spec-writing/SKILL.md) — feature-level planning docs.
- [mkdocs-conventions](../documentation/mkdocs-conventions/SKILL.md) — publishing ADRs in corporate docs.
- [markdown-docs](../documentation/markdown-docs/SKILL.md) — formatting and structure.
- [conventional-commits](../workflows/conventional-commits/SKILL.md) — referencing ADR numbers in commits.
