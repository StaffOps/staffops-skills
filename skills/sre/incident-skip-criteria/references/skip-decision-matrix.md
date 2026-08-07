# Skip Decision Matrix

## Quick-reference lookup table

| Alert type | Environment | Condition | Decision |
|-----------|-------------|-----------|----------|
| ANY | ANY | Severity = P1/CRITICAL | **INVESTIGATE** |
| Data loss (`vm_rpc_rows_lost`, `enqueue_failed`) | ANY | ANY | **INVESTIGATE** |
| Security/Auth | ANY | ANY | **INVESTIGATE** |
| Error rate > 0% | PRD | User-facing service | **INVESTIGATE** |
| SLO burn > 1x | PRD | ANY | **INVESTIGATE** |
| First-ever occurrence | ANY | Unknown signal | **INVESTIGATE** |
| PodCrashLoopBackOff | PRD | Rollout in-progress, same service | SKIP |
| PodCrashLoopBackOff | PRD | No rollout | **INVESTIGATE** |
| PodPending | BTC | Batch schedule window | SKIP |
| PodPending | PRD | ANY | **INVESTIGATE** |
| OOMKilled | BTC | Batch window, known heavy job | SKIP |
| OOMKilled | PRD | ANY | **INVESTIGATE** |
| CPUThrottling < 25% | ANY | No latency impact | SKIP |
| CPUThrottling > 25% | PRD | Latency p99 degraded | **INVESTIGATE** |
| NodeNotReady (spot) | ANY | Karpenter replacing < 2 min | SKIP |
| NodeNotReady (on-demand) | ANY | ANY | **INVESTIGATE** |
| KubeDeploymentReplicasMismatch | ANY | < 5 min, rollout active | SKIP |
| KubeDeploymentReplicasMismatch | PRD | > 5 min | **INVESTIGATE** |
| TargetDown | ANY | Pod terminated by scale-down | SKIP |
| TargetDown | PRD | Pod unexpectedly gone | **INVESTIGATE** |
| Any alert | DEV | Transient < 5 min | SKIP |
| Any alert | DEV | Sustained > 15 min | **INVESTIGATE** |
| Child alert | ANY | Parent under active investigation | SKIP |
| Ambiguous | ANY | Cannot confidently classify | **INVESTIGATE** |

## Skip output template

```
**Decision**: SKIP
**Criterion**: [Step N — rule name]
**Evidence checked**:
  - [what was queried/verified]
  - [ArgoCD status / batch schedule / parent alert ID]
**Confidence**: HIGH | MEDIUM
**Auto-resolve expected**: [timeframe or condition]
```

## Error cases

| Mistake | Impact | Prevention |
|---------|--------|-----------|
| Skip a real PRD outage | Silent customer impact, SLO burn unmitigated | NEVER-SKIP rules in Step 1 |
| Skip data loss signal | Irrecoverable data gone undetected | NEVER-SKIP includes all `*_lost_*`, `*_failed_*` data metrics |
| Skip security alert | Breach window extended | NEVER-SKIP includes all auth/security signals |
| Investigate known noise | $2–5 wasted | Acceptable cost — wrong skips are worse |
