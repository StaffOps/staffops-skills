# Post-Mortem: [TITLE — e.g., "API Gateway 5xx Spike"]

## Metadata

| Field | Value |
|-------|-------|
| **Date** | YYYY-MM-DD |
| **Severity** | SEV1 / SEV2 / SEV3 |
| **Duration** | HH:MM (start → resolution) |
| **Author** | Name |
| **Reviewers** | Name, Name |
| **Status** | Draft / In Review / Final |

## Summary

One paragraph: what happened, how long, who was affected, how it was resolved.

## Impact

| Metric | Value |
|--------|-------|
| Users affected | ~N |
| Requests failed | N (X% of total) |
| Revenue impact | $N / None |
| SLO budget consumed | X% of 30-day budget |
| Data loss | Yes (describe) / None |

## Timeline (UTC)

| Time | Event |
|------|-------|
| HH:MM | First alert fired (`alert-name`) |
| HH:MM | IC declared, war room opened |
| HH:MM | Root cause identified |
| HH:MM | Mitigation applied (describe) |
| HH:MM | Full resolution confirmed |
| HH:MM | Monitoring confirms stable |

## Root Cause

Describe the technical root cause. Be specific — what component, what condition, what triggered it.

## 5 Whys

1. **Why** did users see errors? → Service returned 503.
2. **Why** did service return 503? → Database connection pool exhausted.
3. **Why** was the pool exhausted? → Connection leak in retry logic.
4. **Why** was there a leak? → Error path didn't close connection on timeout.
5. **Why** wasn't this caught? → No integration test for timeout + retry path.

## Contributing Factors

- Factor 1 (e.g., recent deploy introduced the bug)
- Factor 2 (e.g., alert threshold too high, delayed detection)
- Factor 3 (e.g., runbook outdated, slowed mitigation)

## Action Items

| # | Action | Owner | Priority | Due | Status |
|---|--------|-------|----------|-----|--------|
| 1 | Fix connection leak in retry handler | @name | P1 | YYYY-MM-DD | TODO |
| 2 | Add integration test for timeout path | @name | P1 | YYYY-MM-DD | TODO |
| 3 | Lower alert threshold to catch earlier | @name | P2 | YYYY-MM-DD | TODO |
| 4 | Update runbook with new mitigation steps | @name | P3 | YYYY-MM-DD | TODO |

## Lessons Learned

### What went well
- Detection was fast (< 2 min from symptom to alert)
- IC coordination was smooth

### What went poorly
- Runbook was outdated — added 10 min to mitigation
- No dashboard for connection pool metrics

### Where we got lucky
- Happened during low-traffic window; peak would have been 10x worse

## Appendix

- Link to relevant dashboards
- Link to deploy that introduced the issue
- Link to PR that fixed it
