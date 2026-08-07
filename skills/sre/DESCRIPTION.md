# sre

Reliability engineering: SLOs, incidents, and error budgets.

15 skills.

- **alerting-strategy** — Use when designing new alert rules, reducing alert fatigue, routing alerts to correct channels, evaluating alert quality (MTTA/MTTR/false-positive rate), or deciding between symptom-based vs cause-...
- **capacity-projection** — > _(references/)_
- **deploy-correlation-checker** — > _(references/)_
- **error-budget-framework** — Use when implementing error budget tracking, burn rate alerting, or defining budget exhaustion policies. Provides complete VMRule recording rules and alert rules (copy-paste ready), multi-window bu...
- **incident-response-runbook** — Run incident command, severity and comms.
- **incident-skip-criteria** — > _(references/)_
- **incident-triage** — >
- **investigation-cost-guardrail** — > _(references/)_
- **metric-correlation-analysis** — > _(references/)_
- **post-mortem-templates** — Use when writing a blameless post-mortem after a production incident (SEV1-2 mandatory, SEV3 encouraged). Provides copy-paste templates by severity, 5-Whys and fishbone RCA techniques, action item ...
- **root-cause-analysis** — Use when investigating production incidents where the root cause is unknown. Provides structured techniques (5 Whys, fault tree, elimination), cross-signal correlation patterns, timeline constructi...
- **runbook-authoring** — Use when writing an operational runbook for a new or existing alert. Every production alert MUST have a linked runbook. Provides copy-paste template with diagnostics/mitigation/verification/escalat...
- **sla-slo-design** — Use when defining reliability targets (SLI/SLO/SLA) for a new or existing service, choosing service tier, writing recording rules for VictoriaMetrics, or setting up burn rate alerting. Covers avail...
- **slo-burn-rate-calculator** — > _(references/)_
- **symptom-router** — > _(references/)_
