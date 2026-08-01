# Handoff Template

Copy this skeleton when writing a handoff document (Mode B) or when composing
the summary string passed to `claude --bg` (Mode A). Delete any section that
does not apply — a migration handoff will not have a "Severity" line, an
incident handoff will not have a "Rollback plan" line.

```markdown
# Handoff: <incident name or migration name>

Written: <YYYY-MM-DD HH:MM UTC-offset>
Type: [Incident | Migration]
Severity: [SEV1 | SEV2 | SEV3 | SEV4 | n/a for migration]
IC / Owner: <name or "unassigned">
Elapsed: <time since detection / since migration start>

## Status

<Current working hypothesis, even if tentative. Current phase of the
migration. What is true right now, not a narrative of everything tried.>

Suspected cause category: [Code | Config | Infra | Deploy | Capacity |
Dependency | n/a — not yet narrowed]

## Ruled Out (do not repeat this investigation)

- <Dead end 1> - checked via <command / query / dashboard>, result: <negative
  finding>
- <Dead end 2> - checked via <command / query / dashboard>, result: <negative
  finding>

## Still Running

- <Background remediation, canary, migration step, or long-running job> -
  expected completion: <time or condition>. Check status via: <command or
  link>.

## Links

- Incident channel / thread: <url>
- Ticket: <url or ID>
- Runbook in use: <path or skill name>
- Relevant dashboard(s): <url>
- Relevant query/queries: <PromQL / LogQL / TraceQL, or a link to a saved
  query>

## Next Steps

1. <Concrete next action, highest priority first>
2. <...>
3. <...>

## Rollback Plan (migrations only)

<How to revert if the next step fails. Omit for incidents already past
mitigation.>

## Suggested Skills

- <skill-name> - <why the next session should invoke it>
- <skill-name> - <why the next session should invoke it>
```

## Filled example (incident)

```markdown
# Handoff: payment-api 5xx spike (INC-2381)

Written: 2026-07-31 22:40 UTC-03
Type: Incident
Severity: SEV2
IC: unassigned for next shift - please claim in #incidents-active
Elapsed: 55 minutes since detection

## Status

Error rate on payment-api is holding steady at ~6% (down from a 40% spike at
detection). Current hypothesis: a connection pool leak introduced by the
1.4.2 deploy at 21:50, not yet confirmed. Rollback has NOT been executed —
holding to gather more evidence first, per IC decision at 22:10.

Suspected cause category: Deploy (pending confirmation against the 21:50
release)

## Ruled Out (do not repeat this investigation)

- Not a downstream RDS issue - checked RDS CPU/connections in Grafana,
  both nominal for the whole window.
- Not a cert expiry - `cert-manager` events show no recent renewal or
  failure for payment-api's certificate.
- Not a Karpenter node churn issue - no node replacements in the affected
  namespace in the last 2 hours (`kubectl get events -n payments`).

## Still Running

- Connection pool metrics dashboard left open, refreshing every 30s -
  watching for the leak to reproduce. Link: <grafana dashboard url>.

## Links

- Incident channel: #incidents-active, thread starting 21:55
- Ticket: INC-2381
- Runbook in use: incident-response-runbook (Mitigate phase)
- Dashboard: <grafana dashboard url>
- Query used: `sum(rate(http_server_request_duration_seconds_count{service="payment-api",http_status_code=~"5.."}[5m]))`

## Next Steps

1. Confirm the connection pool leak hypothesis by correlating pool
   exhaustion metrics with the 21:50 deploy timestamp.
2. If confirmed, roll back to the pre-1.4.2 image via ArgoCD.
3. If not confirmed within 30 minutes, escalate severity and page the
   payments team lead.

## Suggested Skills

- incident-response-runbook - for severity/escalation rules and the
  Mitigate-vs-Investigate decision.
- post-mortem-templates - once resolved, for the 5 Whys and action item
  format (this doc's "Status" hypothesis maps to the eventual Root Cause
  section).
```
