# On-Call Handoff Note

## Metadata

| Field | Value |
|-------|-------|
| **Date** | YYYY-MM-DD |
| **Outgoing** | Name (shift end: HH:MM TZ) |
| **Incoming** | Name (shift start: HH:MM TZ) |
| **Rotation** | Primary / Secondary |

## Active Incidents

| Incident | Severity | Status | Owner | Notes |
|----------|----------|--------|-------|-------|
| [title] | SEV2 | Mitigated, monitoring | @name | Rollback applied; watching for recurrence |
| — | — | — | — | — |

> If none: "No active incidents."

## Recent Deploys (last 24h)

| Time (UTC) | Service | Change | Rollback? |
|------------|---------|--------|-----------|
| HH:MM | service-name | feat: description (MR !NNN) | Ready (tag v1.2.2) |
| HH:MM | service-name | fix: description | Ready |

> Watch for latent issues from these deploys during your shift.

## Error Budget Status

| Service | SLO Target | Budget Remaining (30d) | Trend |
|---------|-----------|------------------------|-------|
| api-gateway | 99.9% | 72% | Stable |
| payment-svc | 99.95% | 31% | ⚠️ Declining |

> Services below 50% budget: be conservative — avoid risky deploys.

## Silenced Alerts

| Alert | Reason | Expires |
|-------|--------|---------|
| `HighMemoryUsage` on batch-worker | Known spike during nightly job | YYYY-MM-DD HH:MM |
| `CertExpiringSoon` on internal-api | Renewal scheduled for tomorrow | YYYY-MM-DD HH:MM |

> Review before your shift ends — re-silence or resolve.

## Known Issues (non-incident, worth knowing)

- **service-x**: Intermittent 504s to downstream-y during peak. Tracked in JIRA-NNN. No action unless rate exceeds 1%.
- **cluster-z**: Node pool at 85% capacity. Karpenter should handle, but watch for Pending pods.

## Upcoming Changes (next 24h)

| Time (UTC) | Change | Risk | Contact |
|------------|--------|------|---------|
| HH:MM | DB maintenance window (read replicas) | Low | @dba-team |
| HH:MM | Feature flag rollout: new-checkout (10%) | Medium | @product-name |

## Handoff Checklist

- [ ] Incoming has access to war room / incident channel
- [ ] Incoming reviewed active alerts dashboard
- [ ] PagerDuty / OpsGenie rotation updated
- [ ] Any open threads in Slack handed over with context
- [ ] Verbal or sync walkthrough completed (for SEV1/2 carryover)
