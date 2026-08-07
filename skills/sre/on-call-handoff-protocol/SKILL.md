---
name: on-call-handoff-protocol
description: Use when handing off an on-call shift or starting a new one. Structured checklist covering active incidents, recent deploys, error budget burn, silenced alerts, known issues, and status page state. Ensures no context is lost between shifts.
---

# On-Call Handoff Protocol

## When to use

- Starting a new on-call rotation shift
- Handing off to the next on-call engineer
- Returning from PTO and resuming on-call duties
- After an incident, ensuring next shift knows the state
- During extended incidents that span multiple shifts

## When NOT to use

- Routine standup updates (too heavy for daily meetings)
- Incident response in progress (use incident-response-runbook instead)
- Permanent team knowledge transfer (use documentation/runbooks)

---

## Incoming on-call checklist (starting your shift)

### 1. Active incidents

```bash
# Check current incidents / open alerts
# PagerDuty
curl -s -H "Authorization: Token token=<api-key>" \
  "https://api.pagerduty.com/incidents?statuses[]=triggered&statuses[]=acknowledged" | \
  jq '.incidents[] | {id, title, status, created_at}'

# Alertmanager — active alerts
curl -s http://alertmanager:9093/api/v2/alerts?active=true | \
  jq '.[] | {labels: .labels.alertname, status: .status.state, startsAt}'

# Grafana OnCall
# Check the on-call schedule UI for unresolved alert groups
```

- [ ] Any active incidents? Document their state.
- [ ] Any incidents resolved in last 4 hours that might recur?
- [ ] Outstanding action items from recent incidents?

### 2. Recent deployments (last 24h)

```bash
# ArgoCD — recent syncs
kubectl get applications -A -o custom-columns=\
  'NAME:.metadata.name,STATUS:.status.sync.status,HEALTH:.status.health.status,LAST_SYNC:.status.operationState.finishedAt' | \
  sort -k4 -r | head -20

# Check rollout status for canary/blue-green
kubectl get rollouts -A -o custom-columns=\
  'NAME:.metadata.name,STATUS:.status.phase,STEP:.status.currentStepIndex'

# Git log of recent merges to production branch
git log --oneline --since="24 hours ago" --merges origin/production
```

- [ ] Any deployments in progress (canary paused, blue-green pending)?
- [ ] Any recent rollbacks?
- [ ] Any known risky deploys expected during this shift?

### 3. Error budget burn

```bash
# Query error budget consumption (last 7d burn rate)
# Adjust PromQL to your SLO recording rules
curl -s "http://vmselect:8481/select/0/prometheus/api/v1/query?query=\
  1 - (sum(rate(http_server_request_duration_seconds_count{status!~\"5..\"}[7d])) / \
  sum(rate(http_server_request_duration_seconds_count[7d])))"

# Check if any service is burning budget faster than expected
# Multi-window burn rate alert should catch this, but verify manually
```

- [ ] Any services with error budget < 20% remaining?
- [ ] Any burn rate alerts currently suppressed?
- [ ] Is there a change freeze due to low budget?

### 4. Silenced/inhibited alerts

```bash
# Alertmanager — list active silences
curl -s http://alertmanager:9093/api/v2/silences?active=true | \
  jq '.[] | {id: .id, matchers: .matchers, createdBy: .createdBy, endsAt: .endsAt, comment: .comment}'
```

- [ ] Review each silence — is it still valid?
- [ ] Any silences expiring during this shift?
- [ ] Any silences without clear justification (remove them)?

### 5. Infrastructure state

```bash
# Node health
kubectl get nodes -o wide | grep -v " Ready"

# Pending pods (scheduling issues)
kubectl get pods -A --field-selector=status.phase=Pending

# Resource pressure
kubectl top nodes --sort-by=cpu | head -5
kubectl top nodes --sort-by=memory | head -5
```

- [ ] All nodes healthy?
- [ ] Any pods stuck in Pending/CrashLoopBackOff?
- [ ] Any nodes being drained or cordoned?

### 6. Known issues and workarounds

- [ ] Read the on-call handoff notes from outgoing engineer
- [ ] Check team channel for pinned messages about known issues
- [ ] Review any temporary workarounds in place (manual restarts, etc.)

### 7. Communication readiness

- [ ] Confirm you can receive alerts (phone, app, laptop)
- [ ] Test escalation path (know who your backup is)
- [ ] Know the status page URL and have edit access
- [ ] Know the incident communication channel

---

## Outgoing on-call checklist (ending your shift)

### Write handoff notes

```markdown
## On-Call Handoff: [DATE] [YOUR_NAME] → [NEXT_PERSON]

### Active issues
- [Issue 1]: [status, what's been done, what's pending]
- [Issue 2]: [status]

### Recent incidents (last 24-48h)
- [Incident]: [resolved/ongoing], RCA [done/pending], follow-ups [list]

### Deploys to watch
- [Service X] deployed at [time] — watch for [metric/behavior]

### Silences in place
- [Alert]: silenced until [time] because [reason]

### Known workarounds
- [Service Y]: restart pod if [symptom] appears (ticket: [link])

### Upcoming risks
- [Maintenance window at time]
- [Expected traffic spike from event]
- [Cert expiring in N days]
```

- [ ] Write handoff notes in team channel or handoff doc
- [ ] Verbally brief the incoming engineer on anything critical
- [ ] Transfer any active incident commander role
- [ ] Confirm incoming engineer acknowledges receipt

---

## Anti-patterns

- ❌ "Nothing happened, good luck" — always provide structured handoff
- ❌ Silencing alerts without documenting why and when to un-silence
- ❌ Not checking silences at shift start (inheriting stale silences)
- ❌ Skipping error budget check (might be in change freeze and not know)
- ❌ Not testing alert delivery at shift start (phone on DND, app logged out)
- ❌ Verbal-only handoff with no written notes (context lost if forgotten)
- ❌ Ignoring "resolved" incidents from last shift (may recur)

---

## Related skills

- `incident-response-runbook` — what to do when an alert fires
- `alerting-strategy` — understanding alert severity and routing
- `error-budget-framework` — interpreting burn rates and budget state
- `sla-slo-design` — understanding the SLOs you're protecting
- `post-mortem-templates` — documenting incidents that happened on your shift
