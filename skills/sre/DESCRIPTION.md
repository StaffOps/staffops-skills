# sre

Reliability engineering: SLOs, incidents, and error budgets.

17 skills.

- **alerting-strategy** — Use when designing new alert rules, reducing alert fatigue, routing alerts to correct channels, evaluating alert quality (MTTA/MTTR/false-positive rate), or deciding between symptom-based vs cause-... _(references/)_
- **capacity-projection** — Use when assessing whether storage, ingestion rate, or resource usage will exhaust capacity before the next review cycle. Runs a bundled Python script that fits linear regression on time-series dat... _(references/)_
- **chaos-engineering-patterns** — Use when designing chaos experiments or running game days. Covers steady state hypothesis, experiment design (pod kill, network partition, CPU stress, disk fill), Litmus/Chaos Mesh CRDs, blast radi... _(references/)_
- **deploy-correlation-checker** — Use when an anomaly is detected and you need to determine if a recent deploy caused it. Cross-references deploy timestamps (from ArgoCD) with metric anomaly start times. Identifies the most likely ... _(references/)_
- **error-budget-framework** — Use when implementing error budget tracking, burn rate alerting, or defining budget exhaustion policies. Provides complete VMRule recording rules and alert rules (copy-paste ready), multi-window bu... _(references/)_
- **incident-response-runbook** — Run incident command, severity and comms. _(references/)_
- **incident-skip-criteria** — Incident Triage agent ONLY. Evaluate whether an alert should be SKIPPED (no paid investigation) or INVESTIGATED. Triggers: every incoming alert before the investigation budget is spent. Criteria: k... _(references/)_
- **incident-triage** — Use when an alert fires (SLOBurnRateP1/P2, PodCrashLooping, HighErrorRate), a user reports service degradation, or pods are in CrashLoopBackOff/OOMKilled. Provides severity classification, evidence...
- **investigation-cost-guardrail** — Applies to EVERY investigation before the first query is executed. Triggered always — enforces time/cost budgets per incident severity, prevents unbounded queries (PromQL over 30d, TraceQL without ... _(references/)_
- **metric-correlation-analysis** — Use when multiple metrics anomaly at the same time and you need to determine if they share a common cause. Runs a bundled Python script that detects Z-score anomalies per metric and finds temporal ... _(references/)_
- **on-call-handoff-protocol** — Use when handing off an on-call shift or starting a new one. Structured checklist covering active incidents, recent deploys, error budget burn, silenced alerts, known issues, and status page state.... _(references/)_
- **post-mortem-templates** — Use when writing a blameless post-mortem after a production incident (SEV1-2 mandatory, SEV3 encouraged). Provides copy-paste templates by severity, 5-Whys and fishbone RCA techniques, action item ... _(references/)_
- **root-cause-analysis** — Use when investigating production incidents where the root cause is unknown. Provides structured techniques (5 Whys, fault tree, elimination), cross-signal correlation patterns, timeline constructi...
- **runbook-authoring** — Use when writing an operational runbook for a new or existing alert. Every production alert MUST have a linked runbook. Provides copy-paste template with diagnostics/mitigation/verification/escalat...
- **sla-slo-design** — Use when defining reliability targets (SLI/SLO/SLA) for a new or existing service, choosing service tier, writing recording rules for VictoriaMetrics, or setting up burn rate alerting. Covers avail...
- **slo-burn-rate-calculator** — Use when an SLO burn rate alert fires, when assessing budget health during an incident, or when determining how long until the error budget exhausts at the current rate. Runs a bundled Python scrip... _(references/)_
- **symptom-router** — ENTRY POINT — load FIRST when any symptom is reported: \"API is slow\", \"high latency\", \"logs missing\", \"traces missing\", \"metrics missing\", \"gaps in dashboard\", \"pods Pending\", \"OOMKi... _(references/)_
