# StaffOps Skills

A catalog of 242 platform engineering skills for AI coding agents.

## Build & Test

```bash
python3 tools/validate_skills.py        # Validate all skills (frontmatter, structure, cross-refs)
python3 tools/generate_catalog.py       # Regenerate DESCRIPTION.md + README catalog
tools/verify_metrics.sh --all           # Verify metric names against live VM (needs VM_READ_ENDPOINT)
```

## Directory Layout

```
skills/<category>/<name>/SKILL.md       # The skill (procedure, decision trees)
skills/<category>/<name>/references/    # Supporting data (lookup tables, scripts, templates)
tools/                                  # Validation and generation scripts
docs/                                   # Research notes, skill graph
```

## Conventions

- Every SKILL.md has: `name` + `description` (100-1024 chars, starts with "Use when...")
- Standard sections: When to use, When NOT to use, Steps, Related skills
- `references/` for lookup data — NOT procedure (SKILL.md is procedure)
- English only, no org-specific content, no hardcoded paths
- Metric names must be verified against live backend before merge

## Do Not Touch

- `skills/apm-metrics/` metric names — verified against live VictoriaMetrics
- `tools/verify_metrics.sh` NOT_SCRAPED_ALLOWLIST — curated intentionally
- Frontmatter `name` field must match directory name exactly
