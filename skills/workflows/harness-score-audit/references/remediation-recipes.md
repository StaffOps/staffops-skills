# Remediation Recipes — Harness Score Dimensions

Per-dimension fix recipes to improve harness-score. Each section shows the minimum viable fix to gain maximum points.

---

## Dimension 1: Context & Guides

### Create AGENTS.md (fastest +9 points)

```markdown
# <Project Name>

## Architecture

<Brief description of what this project does and how it's structured.>

```
src/           — Application source code
tests/         — Test suite
docs/          — Documentation
scripts/       — Build and automation scripts
```

## Build / Test / Run

```bash
# Build
<build command>

# Test
<test command>

# Run locally
<run command>
```

## Conventions

- Commit format: Conventional Commits (feat/fix/chore)
- Branch naming: feature/*, fix/*, chore/*
- Code style: <linter/formatter used>
- Test coverage: minimum 80%

## Gotchas

- <Non-obvious thing that trips up newcomers or agents>
- <Another common pitfall>
```

### Add tool-specific pointer (+3 points)

```bash
# CLAUDE.md (for Claude Code)
echo "# $(basename $(pwd))\n\nSee @AGENTS.md" > CLAUDE.md

# .cursorrules (for Cursor)
echo "See AGENTS.md for project context and conventions." > .cursorrules
```

---

## Dimension 2: Skills & Commands

### Create first SKILL.md (+3 points)

Create `.kiro/skills/<name>/SKILL.md` or `.claude/skills/<name>/SKILL.md`:

```markdown
---
name: <skill-name>
description: "Use when <trigger condition>. Covers <what it teaches>."
---
# <Skill Title>

## When to use
- <Condition 1>
- <Condition 2>

## Procedure
1. <Step 1>
2. <Step 2>
3. <Step 3>

## Anti-patterns
- ❌ <Common mistake>
```

### Add commands directory (+3 points)

```bash
mkdir -p .claude/commands
cat > .claude/commands/run-tests.md << 'EOF'
Run the project test suite and report results:
1. Execute: `<test command>`
2. If failures, show the failing test names and error messages
3. Suggest fixes for the top 3 failures
EOF
```

---

## Dimension 3: Hooks & Guardrails

### Add PreToolUse hook (+3 points)

In `.claude/settings.json` (Claude Code):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "write|shell",
        "command": "echo 'Tool use: $TOOL_NAME on $FILE_PATH'"
      }
    ]
  }
}
```

In `.kiro/agents/<name>.json` (Kiro):

```json
{
  "hooks": {
    "preToolUse": {
      "command": "validate-tool-use.sh",
      "description": "Validates destructive operations require confirmation"
    }
  }
}
```

### Document guardrails (+3 points)

Add to AGENTS.md:

```markdown
## Safety Guardrails

- Never modify files in `production/` without explicit approval
- Never run `rm -rf` or `git push --force`
- Always run tests before suggesting a commit
- Never expose secrets or credentials in output
```

---

## Dimension 4: Sensors

### Configure test runner (+3 points)

Ensure one of these is present and documented in AGENTS.md:

```bash
# Python
pytest.ini or pyproject.toml [tool.pytest]

# JavaScript/TypeScript
jest.config.js or vitest.config.ts

# Go
go test ./... (just needs test files)

# .NET
<project>.Tests.csproj
```

### Add linter config (+3 points)

```bash
# Python
cat > pyproject.toml << 'EOF'
[tool.ruff]
line-length = 120
select = ["E", "F", "I"]
EOF

# TypeScript
npx eslint --init

# Go (built-in)
# golangci-lint already available via `golangci-lint run`
```

### Add pre-commit hooks (+3 points)

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

---

## Dimension 5: CI Feedback

### Add CI config (+3 points)

**GitHub Actions:**

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: <test command>
      - name: Run linter
        run: <lint command>
```

**GitLab CI:**

```yaml
# .gitlab-ci.yml
stages: [test, lint]

test:
  stage: test
  script: <test command>

lint:
  stage: lint
  script: <lint command>
```

### Add harness-score gate (+3 points)

```yaml
# GitHub Actions addition
- name: Harness Score
  run: npx -y harness-score . --min-level 2

# GitLab CI addition
harness-gate:
  stage: test
  image: node:20-slim
  script: npx -y harness-score . --min-level 2
```

---

## Dimension 6: Hygiene

### Fix .gitignore (+3 points)

Append to `.gitignore`:

```gitignore
# AI tool local config (not versioned)
.claude/
.kiro/
.cursor/
.continue/
.aider*
```

### Add .env.example (+3 points)

```bash
# .env.example — copy to .env and fill in values
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
REDIS_URL=redis://localhost:6379
API_KEY=<your-api-key-here>
LOG_LEVEL=info
```

### Add LICENSE (+3 points)

```bash
# MIT (permissive)
curl -sL https://choosealicense.com/licenses/mit/ | sed "s/\[year\]/$(date +%Y)/" | sed "s/\[fullname\]/Your Name/" > LICENSE

# Or for internal/proprietary
echo "Copyright (c) $(date +%Y) <Company>. All rights reserved. Proprietary and confidential." > LICENSE
```

### Ensure no secrets in repo (+3 points)

```bash
# Scan for secrets
npx -y gitleaks detect --source .

# If found, remove from history:
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch <secret-file>' HEAD
# Then rotate the exposed credential immediately
```

---

## Priority matrix: Maximum points per effort

| Fix | Points gained | Effort | Do first? |
|-----|--------------|--------|-----------|
| Create AGENTS.md | +9 | 15 min | ✅ Always |
| Add .gitignore AI entries | +3 | 1 min | ✅ Always |
| Add LICENSE | +3 | 1 min | ✅ Always |
| Add .env.example | +3 | 5 min | ✅ If env vars exist |
| Tool pointer (CLAUDE.md) | +3 | 1 min | ✅ Always |
| Configure test runner | +3–6 | 10 min | ✅ If tests exist |
| Create 1 SKILL.md | +3 | 15 min | After AGENTS.md |
| Add CI config | +3–6 | 20 min | After sensors |
| Add hooks | +3–6 | 15 min | After L2 reached |
| Add pre-commit | +3 | 10 min | After linter |

**Fastest path L0→L2**: AGENTS.md + CLAUDE.md + .gitignore + LICENSE + .env.example + test runner = ~44 points in ~45 minutes.
