---
name: harness-score-audit
description: "Use when auditing a repository's AI agent harness maturity or improving its score. The harness-score tool (MIT, npx harness-score) measures 6 dimensions across 36 checks (108 points, L0-L4 maturity). Steps: run baseline, interpret dimensions, fix by priority, re-run, gate CI."
---
# Harness Score Audit

## When to use

- Auditing a repo's readiness for AI-assisted development (agent harness maturity)
- Improving harness-score to reach a target maturity level (L0→L4)
- Setting up CI gates that enforce minimum harness quality
- Comparing repos across an organization for harness adoption
- Prioritizing which harness dimension to fix first for maximum point gain

## When NOT to use

- Evaluating agent output quality (use `agent-evals`)
- Designing MCP tools (use `mcp-tool-design-patterns`)
- Writing SKILL.md files (use `skill-authoring`)

---

## Quick start

```bash
# Get baseline score (requires Node.js 18+)
npx -y harness-score . --json

# Human-readable output
npx -y harness-score .

# Gate CI at minimum level
npx -y harness-score . --min-level 2
# Exit code 1 if below L2
```

---

## The 6 dimensions (36 checks, 108 max points)

| # | Dimension | What it measures | Max pts |
|---|-----------|------------------|---------|
| 1 | **Context & Guides** | AGENTS.md, CLAUDE.md, .cursorrules, project context | 18 |
| 2 | **Skills & Commands** | SKILL.md files, .claude/commands, reusable prompts | 18 |
| 3 | **Hooks & Guardrails** | PreToolUse, PostToolUse, stop hooks, safety gates | 18 |
| 4 | **Sensors** | Test runner, linter, type checker, formatters | 18 |
| 5 | **CI Feedback** | GitHub Actions, GitLab CI, PR comments, status checks | 18 |
| 6 | **Hygiene** | .gitignore for AI dirs, no secrets, LICENSE, .env.example | 18 |

Each dimension has 6 checks × 3 points each = 18 points max.

---

## Maturity ladder

| Level | Score range | Meaning |
|-------|-------------|---------|
| **L0** | 0–21 | No harness — agent flies blind |
| **L1** | 22–43 | Basic — some context, minimal guardrails |
| **L2** | 44–65 | Structured — guides + skills + some hooks |
| **L3** | 66–86 | Mature — full harness, CI feedback loop |
| **L4** | 87–108 | Exemplary — all dimensions strong, gated CI |

---

## Decision tree: What to fix first

```
Current score?
│
├── L0 (0–21): Start with Context & Guides
│   └── Create AGENTS.md (biggest single-file impact)
│
├── L1 (22–43): Add Sensors + Hygiene
│   └── Test runner + .gitignore for .claude/.kiro
│
├── L2 (44–65): Add Skills + Hooks
│   └── At least 1 SKILL.md + PreToolUse hook
│
├── L3 (66–86): Polish CI Feedback + remaining gaps
│   └── PR status checks + harness-score gate in CI
│
└── L4 (87–108): Maintain — audit on major changes
```

**Priority heuristic**: fix the dimension with the LOWEST score first (most room to gain).

---

## Procedure: Full audit cycle

### Step 1: Get baseline

```bash
npx -y harness-score . --json > harness-baseline.json
cat harness-baseline.json | jq '.score, .level, .dimensions'
```

### Step 2: Interpret each dimension

For each dimension scoring below 12/18 (66%), check the remediation recipe in `references/remediation-recipes.md`.

### Step 3: Fix by priority

Apply fixes from highest-point-gain to lowest:
1. Missing AGENTS.md → +6 to +9 points
2. Missing .gitignore entries → +3 to +6 points
3. No test runner configured → +3 to +6 points
4. No SKILL.md files → +3 to +6 points
5. No hooks → +3 to +6 points
6. No CI feedback → +3 to +6 points

### Step 4: Re-run and verify

```bash
npx -y harness-score . --json > harness-after.json
diff <(jq '.dimensions' harness-baseline.json) \
     <(jq '.dimensions' harness-after.json)
```

### Step 5: Gate CI

```yaml
# GitHub Actions
- name: Harness Score Gate
  run: npx -y harness-score . --min-level 2

# GitLab CI
harness-gate:
  stage: pre-build
  image: node:20-slim
  script:
    - npx -y harness-score . --min-level 2
  rules:
    - if: $CI_MERGE_REQUEST_IID
```

---

## Dimension details

### 1. Context & Guides

Checks for files that tell the agent WHO it is and HOW to behave in this repo.

| Check | Points | What satisfies it |
|-------|--------|-------------------|
| AGENTS.md exists | 3 | File at repo root with project overview |
| Tool-specific pointer | 3 | CLAUDE.md or .cursorrules pointing to AGENTS.md |
| Architecture section | 3 | AGENTS.md has directory layout / component map |
| Build/test/run commands | 3 | AGENTS.md documents how to build and test |
| Conventions section | 3 | Coding style, naming, commit format documented |
| Gotchas/pitfalls | 3 | Non-obvious traps documented for the agent |

### 2. Skills & Commands

Checks for reusable knowledge the agent can invoke on-demand.

| Check | Points | What satisfies it |
|-------|--------|-------------------|
| ≥1 SKILL.md file | 3 | Any skill in .kiro/skills/ or .claude/skills/ |
| ≥3 SKILL.md files | 3 | Broader coverage |
| Skills have frontmatter | 3 | YAML name + description in each SKILL.md |
| Commands directory | 3 | .claude/commands/ or equivalent prompts |
| Skills cover key domains | 3 | Dev + ops + docs (not all one category) |
| Skills reference each other | 3 | "See also" / "Use X instead" cross-links |

### 3. Hooks & Guardrails

Checks for automated safety gates around agent actions.

| Check | Points | What satisfies it |
|-------|--------|-------------------|
| PreToolUse hook exists | 3 | Validates before destructive tool use |
| PostToolUse hook exists | 3 | Verifies after tool execution |
| Stop/SessionEnd hook | 3 | Cleanup or summary on session end |
| Deny-list patterns | 3 | Explicit "never do X" rules enforced |
| Approval gates defined | 3 | High-risk actions require human confirmation |
| Hook documentation | 3 | Hooks are documented (what they block/allow) |

### 4. Sensors

Checks for feedback loops the agent can use to validate its own work.

| Check | Points | What satisfies it |
|-------|--------|-------------------|
| Test runner configured | 3 | pytest/jest/go test/dotnet test runnable |
| Linter configured | 3 | eslint/ruff/golangci-lint present |
| Type checker | 3 | mypy/tsc/go vet configured |
| Formatter | 3 | prettier/black/gofmt configured |
| Coverage reporting | 3 | Coverage tool with threshold |
| Pre-commit hooks | 3 | .pre-commit-config.yaml or husky |

### 5. CI Feedback

Checks for automated pipeline feedback visible to the agent.

| Check | Points | What satisfies it |
|-------|--------|-------------------|
| CI config exists | 3 | .github/workflows/ or .gitlab-ci.yml |
| Tests run in CI | 3 | Test stage in pipeline |
| Lint runs in CI | 3 | Lint stage in pipeline |
| PR/MR status checks | 3 | Required checks before merge |
| CI failure feedback | 3 | Error messages parseable by agent |
| Harness-score gate | 3 | harness-score --min-level in CI |

### 6. Hygiene

Checks for clean repo setup that prevents agent-caused messes.

| Check | Points | What satisfies it |
|-------|--------|-------------------|
| .gitignore covers AI dirs | 3 | .claude/, .kiro/, .cursor/ excluded |
| No secrets in repo | 3 | No .env with real values, no keys |
| LICENSE file exists | 3 | Any OSS or proprietary license |
| .env.example exists | 3 | Template for required env vars |
| README.md exists | 3 | Basic project documentation |
| CHANGELOG or releases | 3 | Version history maintained |

---

## Anti-patterns

- ❌ Gaming the score (empty AGENTS.md with no real content)
- ❌ Adding hooks that don't actually validate anything
- ❌ Skills that are copy-pasted templates without project specifics
- ❌ CI gate at L4 on day one (start at L1, ratchet up over sprints)
- ❌ Auditing once and never re-running (harness degrades as code evolves)
- ❌ Treating harness-score as a replacement for actual agent evals

---

## Checklist: reaching L2 from L0

- [ ] Create `AGENTS.md` at repo root (architecture, build, conventions)
- [ ] Create `CLAUDE.md` with `See @AGENTS.md` (or tool-specific pointer)
- [ ] Add `.gitignore` entries for `.claude/`, `.kiro/`, `.cursor/`
- [ ] Ensure test runner is configured and documented in AGENTS.md
- [ ] Create at least 1 SKILL.md (project-specific knowledge)
- [ ] Add LICENSE file
- [ ] Add `.env.example` if env vars are used
- [ ] Run `npx -y harness-score . --min-level 2` — confirm pass
