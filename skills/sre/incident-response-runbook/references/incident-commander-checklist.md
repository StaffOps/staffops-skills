# Incident Commander Checklist

## Phase 1: Declare & Mobilize (first 5 minutes)

- [ ] **Confirm the incident** — verify alert is real, not false positive
- [ ] **Assess severity** using criteria:
  - SEV1: Complete outage / data loss / security breach
  - SEV2: Degraded service for >10% users / SLO breach
  - SEV3: Minor degradation / single-tenant / no SLO breach
- [ ] **Declare incident** in comms channel: `@here INCIDENT DECLARED — SEV[N]: [one-line summary]`
- [ ] **Open war room** (Slack channel / Zoom bridge / Meet)
- [ ] **Assign roles**:
  - IC (yourself) — coordinates, does NOT debug
  - Ops Lead — hands-on-keyboard, executes mitigations
  - Comms Lead — stakeholder updates, status page
  - Scribe — records timeline in real-time

## Phase 2: Investigate & Mitigate

- [ ] **Set investigation timer** — 15 min without progress = escalate
- [ ] **Gather signals**: metrics, logs, traces, recent deploys, recent config changes
- [ ] **Form hypothesis** → validate with data → act or discard
- [ ] **Prioritize mitigation over root cause** — restore service first:
  - Rollback last deploy?
  - Scale up / restart pods?
  - Feature flag off?
  - Failover to secondary?
- [ ] **Communicate every 15 min** (even if no progress):
  - What we know
  - What we're trying
  - ETA or "unknown"

## Phase 3: Escalation Triggers

Escalate immediately if ANY of these are true:

- [ ] No progress after 15 minutes
- [ ] Impact growing (more services / more users)
- [ ] Requires access you don't have (prod DB, IAM, vendor)
- [ ] Security involvement needed (data breach, unauthorized access)
- [ ] Customer-facing for >30 min without mitigation

## Phase 4: Resolution

- [ ] **Confirm mitigation** — error rates back to baseline
- [ ] **Monitor for 15 min** — watch for recurrence
- [ ] **Define "resolved" criteria**: error rate < X%, latency p99 < Y ms
- [ ] **Announce resolution**: `RESOLVED — [summary of fix]. Monitoring for stability.`
- [ ] **Update status page** (if external-facing)

## Phase 5: Close-Out (within 24h)

- [ ] **Create post-mortem doc** (use post-mortem template)
- [ ] **Assign post-mortem author** (ideally NOT the IC)
- [ ] **Schedule review meeting** (within 3 business days)
- [ ] **File action items** as tickets (Jira/Linear) with owners and due dates
- [ ] **Thank the team** — public recognition in channel

## Quick Reference: Status Update Template

```
🔴 INCIDENT UPDATE — SEV[N] — [HH:MM UTC]
Status: Investigating / Mitigating / Monitoring / Resolved
Impact: [who/what is affected]
Current action: [what we're doing right now]
Next update: [time]
```
