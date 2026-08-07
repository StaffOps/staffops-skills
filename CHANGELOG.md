# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-08-07

Initial public release of the StaffOps Skills catalog.

### Added

- **229 skills** across 17 categories: ai (17), apm-metrics (50),
  aws (21), containers (5), development (21), documentation (9),
  finops (3), infrastructure (14), linux (6), networking (5),
  observability (28), projects (1), security (11), shell (5),
  sre (15), troubleshooting (5), workflows (13).
- Consistent skill format: YAML frontmatter with `name`, `description`,
  `version`, `author`, `license`, `platforms`, and `metadata.hermes`
  fields. Body follows When to Use / When NOT to Use / Steps /
  Anti-patterns / Related Skills structure.
- **93+ reference files** (templates, cheat sheets, diagnostic tables)
  under `references/` in applicable skills.
- **4 executable Python scripts** in SRE skills: capacity-projection,
  deploy-correlation-checker, metric-correlation-analysis, and
  slo-burn-rate-calculator.
- **Tooling** (`tools/`):
  - `validate_skills.py` — enforces layout, frontmatter, description
    length, category consistency, and English-only prose.
  - `generate_catalog.py` — regenerates the README catalog table from
    the skill tree.
  - `verify_metrics.sh` — validates metric names referenced in
    apm-metrics skills against a live VictoriaMetrics instance.
  - `install.sh` — installs/uninstalls skills into Claude Code, Kiro
    CLI, or Hermes Agent with `--dry-run` support.
- **Cross-reference graph** (`docs/skill-graph.md`) mapping
  `related_skills` links between all 229 skills.
- All apm-metrics skills verified against live VictoriaMetrics inventory
  — metric names are real, not assumed.
- Shell skills (`shell/`, `linux/`) tested against Ubuntu 24.04
  containers including a real systemd-as-PID-1 environment.
- Zero Portuguese content — all prose, comments, and examples in English.
- Zero organization-specific content — all internal names replaced with
  `<org>`, `<org-domain>`, `<ACCOUNT_ID>`, `<workspace>` placeholders.
- `CONTRIBUTING.md` with skill authoring checklist and PR process.
- MIT license.

### Notes

- 270 non-blocking validation warnings remain (bulk-imported skills
  missing optional `version`/`author`/`license`/`platforms` fields).
  These do not affect skill loading or agent behavior.
- Description limit enforced at 60 characters to preserve agent context
  budget when all 229 frontmatter entries are loaded simultaneously.

[1.0.0]: https://github.com/staffops/staffops-skills/releases/tag/v1.0.0
