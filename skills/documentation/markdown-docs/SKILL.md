---
name: markdown-docs
description: "Write structured, reviewable Markdown docs."
version: 2.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [markdown, docs, documentation]
    category: documentation
    related_skills: [api-docs-patterns, local-reference-docs, mkdocs-conventions]
---
# Markdown Docs — Quick Rules

## When to Use

- Writing or reviewing any `.md` file (README, HOW-TO, runbook, spec)
- Reviewing PRs that touch documentation
- Deciding how to structure a new doc

## When NOT to Use

- Wiki/Notion (different conventions apply)
- Code comments (see `code-quality` steering)

---

## The 10 Rules

### 1. ONE H1 per doc — it's the title

```markdown
# My Service            ← only one of these
## Configuration        ← sections
### Database            ← subsections (max H4)
```

### 2. Don't skip heading levels

❌ `## Section` → `#### Deep` (skipped H3)
✅ `## Section` → `### Subsection` → `#### Detail`

### 3. Sentence case headings

❌ `## Getting Started With The API`
✅ `## Getting started with the API`

### 4. Always tag code blocks with language

```markdown
```yaml
key: value
```⁣

```bash
kubectl get pods
```⁣
```

Hint: `bash` not `sh`, `yaml` not `yml`.

### 5. Tables for structured data, not prose

✅ Good table:
```markdown
| Env | Cluster | Namespace |
|-----|---------|-----------|
| PRD | prd-nv  | payments  |
```

❌ Bad: table cells with 3 paragraphs of text. Use a list instead.

### 6. Links must be descriptive

❌ `[click here](url)`
✅ `[OTel Collector configuration](./docs/collector.md)`

### 7. Keep paragraphs SHORT (3-4 sentences max)

Wall of text = nobody reads it. Break with:
- Bullet lists
- Code examples
- Tables
- Headings

### 8. Callouts / admonitions

For GitHub:
```markdown
> [!NOTE]
> Informational.

> [!WARNING]
> Careful here.
```

For non-GitHub renderers:
```markdown
**Note**: Informational.

**Warning**: Careful here.
```

### 9. Relative links for internal refs

```markdown
<!-- ✅ Relative -->
See [architecture](./docs/architecture.md)

<!-- ❌ Absolute (breaks on forks/mirrors) -->
See [architecture](https://gitlab.example.com/team/repo/-/blob/main/docs/architecture.md)
```

### 10. README is an index, not an encyclopedia

Long explanation? → Move to `docs/<topic>.md`, link from README.

---

## Doc Structure Template

```markdown
# Service Name

Brief: what this does, who it's for (2 sentences max).

## Quick Start

Fastest path to "it works" (< 5 steps).

## Configuration

Env vars, config files, secrets.

## Architecture

Diagram + 1 paragraph.

## Development

How to build/test/run locally.

## Deployment

How it gets to production.

## Troubleshooting

Common errors → fixes.
```

---

## Checklist Before Committing Docs

- [ ] ONE H1, headings don't skip levels
- [ ] Code blocks have language tags
- [ ] No broken links (`grep -oE '\[.*\]\(.*\)' file.md`)
- [ ] Paragraphs ≤ 4 sentences
- [ ] No "click here" links
- [ ] Ran spellcheck (optional but nice)

---

## Related Skills

- `mkdocs-conventions` — MkDocs Material config
- `api-docs-patterns` — OpenAPI/proto docs
- `diagram-patterns` — Mermaid / ASCII / drawio
- `adr-template` — Architecture Decision Records
