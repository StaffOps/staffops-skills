---
name: conventional-commits
description: "Write Conventional Commits and changelogs."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [conventional, commits, workflows]
    category: workflows
    related_skills: []
---
# Conventional Commits

Specification: https://www.conventionalcommits.org/en/v1.0.0/

## When to Use

Conventional Commits 1.0 specification reference. Use when writing commit messages, configuring commitlint, or generating CHANGELOG. Covers types, scopes, breaking changes, footers, and <org>-specific conventions.

## Format

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

## Types (<org> standard)

| Type | When to use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, whitespace (no code change) |
| `refactor` | Code change that neither adds feature nor fixes bug |
| `perf` | Performance improvement |
| `test` | Adding or fixing tests |
| `chore` | Maintenance, dependencies, tooling |
| `ci` | CI/CD pipeline changes |
| `build` | Build system, packaging changes |
| `revert` | Revert a previous commit |
| `security` | Security fix (alternative to fix when emphasizing security) |

## Scopes (<org> standard)

Scope is the area of code affected. At <org>, common scopes:

### Per repo

For <org> OTel Helper monorepo:
- `dotnet` — .NET lib changes
- `python` — Python lib changes
- `dashboards` — Grafana dashboards
- `ci` — pipeline changes
- `docs` — documentation
- `examples` — sample apps

For monitoring Helm:
- `vm` — VictoriaMetrics
- `otel` — OTel Collector
- `loki` — Loki
- `tempo` — Tempo
- `pyroscope` — Pyroscope
- `alerts` — vmrules / alertmanager

### When to omit scope
For repo-wide changes that don't fit one area, omit:
```
chore: update all dependencies
```

## Description rules

- Imperative mood (`add`, `fix`, `update` — NOT `added`, `fixed`, `updated`)
- Lowercase first letter
- No period at the end
- Max 72 chars (line length on most tools)
- Be specific (`fix: handle null user`, not `fix: bug`)

## Examples

### Simple commits

```
feat(otel): add gRPC instrumentation
fix(vm): correct cardinality calc when stddev=0
docs(staffops): update setup-agents.sh usage in README
chore(deps): bump opentelemetry from 1.42.0 to 1.42.1
ci(dotnet): switch demo stage to dual-arch build
```

### With body

```
feat(otel): add tail sampling for prd environment

Add probabilistic sampling policies for production traces:
- 10% baseline
- 100% errors and high-latency
- 100% debug-forced via tracestate

This balances cost (90% reduction in trace storage) with
debuggability (errors and slow paths always retained).

DEVOPS-1234
```

### With breaking change

```
feat(api)!: rename /v1/orders to /v2/orders

BREAKING CHANGE: clients must update endpoint URL.
The /v1 endpoint is removed. Migration guide:
- Replace `/v1/orders` with `/v2/orders` in client code
- Response schema is unchanged
```

Note the `!` after type/scope. The `BREAKING CHANGE:` footer is mandatory.

### Revert

```
revert: feat(otel): add tail sampling for prd environment

This reverts commit a1b2c3d4.

Sampling caused unexpected metric drops. Investigation
in DEVOPS-5678.
```

## Footers

Footers provide additional metadata. Format: `<token>: <value>`.

### Common footers

| Footer | Purpose |
|--------|---------|
| `BREAKING CHANGE:` | Mark breaking change (alternative to `!`) |
| `Refs: DEVOPS-1234` | Reference Jira ticket |
| `Closes: #42` | Close GitLab/GitHub issue |
| `Reviewed-by: <name>` | Code review credit |
| `Co-authored-by: Name <email>` | Pair programming credit |
| `Signed-off-by: Name <email>` | DCO sign-off |

### Multiple footers

```
feat(otel): add Kafka instrumentation

Adds OpenTelemetry.Instrumentation.Kafka 1.15.1.

Refs: DEVOPS-1234
Closes: #42
Co-authored-by: Maria <maria@<org-domain>>
Signed-off-by: Karli <karli@<org-domain>>
```

## CHANGELOG generation

### Tools
- `git-cliff`
- `conventional-changelog`
- `semantic-release` (also handles versioning)

### Auto-generated changelog example

```markdown
# Changelog

## [1.2.0] - 2026-05-28

### Features
- **otel**: add gRPC instrumentation (#42)
- **dashboards**: add Collector health dashboard

### Bug Fixes
- **vm**: correct cardinality calc when stddev=0
- **dotnet**: handle null Activity.Current in worker

### Breaking Changes
- **api**: rename /v1/orders to /v2/orders
```

## Commitlint config

Validates commits via git hooks or CI:

```js
// commitlint.config.js
module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'type-enum': [2, 'always', [
      'feat', 'fix', 'docs', 'style', 'refactor',
      'perf', 'test', 'chore', 'ci', 'build', 'revert', 'security'
    ]],
    'scope-enum': [2, 'always', [
      'dotnet', 'python', 'dashboards', 'ci', 'docs', 'examples',
      'vm', 'otel', 'loki', 'tempo', 'pyroscope', 'alerts'
    ]],
    'subject-case': [2, 'always', 'lower-case'],
    'subject-empty': [2, 'never'],
    'subject-full-stop': [2, 'never', '.'],
    'header-max-length': [2, 'always', 100],
  },
};
```

### Pre-commit hook

`.husky/commit-msg`:
```bash
#!/bin/sh
npx --no -- commitlint --edit "$1"
```

### CI validation

```yaml
# .gitlab-ci.yml
commitlint:
  image: node:20-slim
  stage: lint
  script:
    - npm install -g @commitlint/cli @commitlint/config-conventional
    - git fetch origin main
    - npx commitlint --from origin/main --to HEAD --verbose
  only:
    - merge_requests
```

## Semantic versioning correlation

Conventional Commits → SemVer:

| Commit type | Version bump |
|-------------|--------------|
| `feat` | MINOR (0.1.0 → 0.2.0) |
| `fix` | PATCH (0.1.0 → 0.1.1) |
| `BREAKING CHANGE:` | MAJOR (0.1.0 → 1.0.0) |
| Other types | No version change |

`semantic-release` automates this:
1. Analyzes commits since last release
2. Determines next version
3. Generates CHANGELOG
4. Creates Git tag
5. Publishes package

## Common mistakes

### Mistake: vague descriptions
```
❌ fix: bug
❌ chore: update
❌ feat: improvements
```
```
✅ fix: handle null user in middleware
✅ chore: bump dotnet SDK to 8.0.401
✅ feat: add cache eviction on schema change
```

### Mistake: not using imperative mood
```
❌ fix: fixed the null user bug
❌ feat: added retry logic
```
```
✅ fix: handle null user in middleware
✅ feat: add retry logic to gRPC client
```

### Mistake: combining multiple changes
```
❌ feat: add gRPC support and fix logging bug
```

Split into two commits:
```
✅ feat(otel): add gRPC instrumentation
✅ fix(otel): correct log level filtering
```

### Mistake: missing breaking change marker
```
❌ feat(api): change response schema
```
Should be:
```
✅ feat(api)!: change response schema

BREAKING CHANGE: Order.id is now string (was integer)
```

## Quick reference card

```
<type>(<scope>): <description>

types: feat | fix | docs | style | refactor | perf | test | chore | ci | build | revert | security
scopes: <repo-specific>
breaking: <type>(<scope>)!: ... + BREAKING CHANGE: footer
description: imperative, lowercase, no period, <72 chars
```

## Reference

- Spec: https://www.conventionalcommits.org/en/v1.0.0/
- Commitlint: https://commitlint.js.org/
- semantic-release: https://semantic-release.gitbook.io/
- git-cliff: https://git-cliff.org/
- Related: `git-conventions` (steering), `git-advanced`, `jira-conventions`

## When NOT to use

- **Internal WIP commits** during development — squash into a proper conventional commit before merge.
- **Non-git versioning systems** — the format is git-centric.
- **Changelog prose** — conventional commits generate changelogs; the writing itself is different.


## Decision tree

```
What did you change?
├── New feature (user-visible behavior) → feat(scope): description
├── Bug fix → fix(scope): description
├── Docs only (no code) → docs(scope): description
├── Refactor (no behavior change) → refactor(scope): description
├── Tests only → test(scope): description
├── CI/CD pipeline → ci(scope): description
├── Dependencies / tooling → chore(scope): description
├── Performance improvement → perf(scope): description
└── Formatting / style → style(scope): description
Is it a breaking change?
├── Yes → append ! after type: feat(api)!: rename endpoint
│         AND add BREAKING CHANGE: footer with migration notes
└── No → standard format, no special marker
Multiple changes in one commit?
└── Don't. Split into atomic commits (one type per commit).
```

## Related skills

- [git-advanced](../workflows/git-advanced/SKILL.md) — rebase, bisect, history rewriting.
- [git-guardrails](../workflows/git-guardrails/SKILL.md) — pre-commit hooks, push safety.
- [shell-cli-design](../shell/shell-cli-design/SKILL.md) — consistent naming conventions in automation.
- [spec-writing](../workflows/spec-writing/SKILL.md) — linking commits to spec tasks.
