# aws

AWS service design and troubleshooting patterns.

21 skills.

- **agent-instruction-authoring** — Use when writing or editing an agents_md or a SKILL.md for the AWS DevOps Agent. Carries the rule that an instruction must prescribe substance rather than labels, because the platform overrides the...
- **agent-skills-adversarial-review** — Refute a document with independent reviewers before commit.
- **agent-skills-cost-modelling** — Estimate agent cost from observed duration, not guesses.
- **agent-skills-debugging** — Troubleshooting guide for when a skill doesn't load, loads but produces empty results, or loads but the agent ignores its procedure.
- **agent-skills-harness-guide** — How to run the behaviour harness, interpret results, add new cases, understand costs, and recover from common failures.
- **agent-skills-import-and-harness** — Use when importing assets to the agentspace or running the behaviour harness. Carries every API constraint that cost a failed attempt — sourceUrl being GitHub-only, base64 inline blobs, the extensi...
- **agent-skills-metric-verification** — Use before writing, editing or reviewing any metric name or PromQL query in this repo. Carries the verified environment traps — the inconsistent `_total` suffix, Summary-vs-Histogram, Tempo v3 with...
- **agent-skills-new-skill-checklist** — Step-by-step procedure for adding a new skill to the AWS DevOps Agent catalog — from scaffolding through import and validation.
- **agent-skills-readonly-invariant** — Use when touching the read-only prohibition, the agents_md, the tool associations, or anything about what the agent may execute. Carries the invariant, why the approval-gated model was wrong, the c...
- **agent-skills-sandbox-development** — How to build skills with executable code for the AWS DevOps Agent sandbox — bundling Python/bash scripts, filesystem layout, pre-installed packages, and testing patterns.
- **agent-skills-specs-authoring** — Where planning artefacts go, and what makes one valid.
- **aws-devops-agent-skills** — Use when authoring, importing, validating, or troubleshooting skills for the AWS DevOps Agent (aidevops) — writing SKILL.md, choosing agent_types, importing via zip or sourceUrl, debugging Validati...
- **cloudfront-patterns** — Configure CloudFront origins, caching and WAF.
- **cost-explorer** — Analyze AWS spend via Cost Explorer and CUR Athena.
- **eks-management** — Manage EKS nodes, Karpenter, IRSA and upgrades.
- **eks-node-troubleshooting** — Use when pods are Pending with scheduling failures, nodes show NotReady, Karpenter isn't provisioning, spot interruptions caused rescheduling, or nodes show resource pressure (MemoryPressure, DiskP...
- **iam-patterns** — Design least-privilege IAM roles and policies.
- **lambda-patterns** — Design Lambda cold start, VPC and observability.
- **rds-patterns** — Design RDS sizing, failover and backup strategy.
- **route53-patterns** — Design Route 53 zones, records and health checks.
- **security-hub-patterns** — Configure Security Hub standards and aggregation.
