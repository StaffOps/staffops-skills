---
name: eks-node-troubleshooting
description: >
  Use when pods are Pending with scheduling failures, nodes show NotReady, Karpenter
  isn't provisioning, spot interruptions caused rescheduling, or nodes show resource
  pressure (MemoryPressure, DiskPressure). Covers Karpenter provisioning diagnostics,
  node condition analysis, spot interruption handling, and topology constraint debugging.
  This agent is STRICTLY read-only: node mutations (cordon, drain, terminate) are never executed, only recommended.
---

# EKS Node Troubleshooting

## When to use this skill

- Pods stuck in `Pending` state
- Node(s) in `NotReady` condition
- Karpenter not provisioning despite pending pods
- Spot interruption caused service disruption
- Node resource pressure (Memory/Disk/PID)
- Pods evicted unexpectedly

## When this skill does NOT apply

- Application-level failures (crash loops, error rates) → use `incident-triage`
- Karpenter consolidation tuning → use `karpenter-consolidation`
- Cost optimization of instance types → use `cost-explorer`
- IAM/IRSA issues on pods → use `iam-patterns`

## CRITICAL: Read-Only by Default

All commands below are **read-only**. If mitigation requires mutation (cordon, drain, terminate):
1. State what changes and which pods/services affected
2. Confirm rollback plan
3. Get explicit user approval

**Never manually terminate nodes** in a Karpenter-managed cluster without understanding why Karpenter hasn't already done so.

## Step 1: Identify the problem

```
→ get_nodes — list all nodes with status (look for NotReady)
→ detect_pending_pods — find unschedulable pods with reason
→ get_events — node-level warnings (last 15 min)
```

**What to look for**: scheduling failure reason in pod events, node conditions, node age (new = just provisioned, old = stable).

## Step 2: Diagnose by symptom

### Pods Pending — scheduling failure

```
→ detect_pending_pods — exact scheduling failure reason
```

| Failure message | Cause | Next step |
|-----------------|-------|-----------|
| `Insufficient cpu/memory` | Nodes full | Step 3 (Karpenter check) |
| `node(s) didn't match Pod's node affinity` | Label mismatch | Check pod nodeSelector vs node labels |
| `pod has unbound PersistentVolumeClaims` | PVC issue (not node) | Check PVC status |
| `unsatisfiable topology constraint` | Anti-affinity zone cap | See `karpenter-consolidation` skill |
| `node(s) had taint` | Missing toleration | Check pod tolerations |

### Node NotReady

```
→ kubectl_describe node <name> — check Conditions
→ node_logs <name> — kubelet logs for errors
→ get_events — filtered for the node
```

| Condition | Likely cause |
|-----------|-------------|
| MemoryPressure=True | Node OOM, system processes starved |
| DiskPressure=True | Disk full (images, logs, emptyDir) |
| PIDPressure=True | Process leak, too many containers |
| Ready=False | Kubelet crashed, network partition |

## Step 3: Check Karpenter provisioning

```promql
# Provisioning attempts (should be >0 if pods are pending)
sum(rate(karpenter_nodeclaims_created_total[5m]))

# Karpenter errors (explains WHY not provisioning)
sum(rate(karpenter_cloudprovider_errors_total[5m])) by (error)

# Pending pods visible to Karpenter
karpenter_pods_state{state="pending"}
```

**If Karpenter sees pending pods but isn't provisioning**: check NodePool limits, instance type availability, budget constraints.

```
→ kubectl get nodepools -o yaml | yq '.items[].spec.limits'
→ kubectl get nodepools -o yaml | yq '.items[].spec.disruption.budgets'
```

## Step 4: Check spot interruptions (if applicable)

```promql
# Spot interruption events
sum(rate(karpenter_interruption_received_messages_total[1h])) by (message_type)

# Nodes disrupted
sum(rate(karpenter_voluntary_disruption_decisions_total[1h])) by (decision, reason)
```

**Expected behavior**: Karpenter receives 2-min warning → cordons → drains → provisions replacement.

**Problem indicator**: pods stay Pending after interruption = no replacement capacity available.

## Step 5: Resource pressure analysis

```promql
# Node CPU saturation
sum(rate(node_cpu_seconds_total{mode!="idle"}[5m])) by (node) / count(node_cpu_seconds_total{mode="idle"}) by (node)

# Node memory usage
(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes

# Pods per node vs allocatable
count(kube_pod_info) by (node)
```

**Threshold**: CPU >85% sustained = pressure; Memory >90% = eviction risk.

## Step 6: Summarize findings

1. **Status** — healthy / degraded (pods pending) / critical (nodes NotReady)
2. **Root cause** — cite specific evidence (e.g., "3 pods Pending due to `Insufficient memory`; Karpenter blocked by NodePool limit of 100 nodes, currently at 100")
3. **Recommended remediation** — ranked:
   - ⚠️ RECOMMENDATION ONLY — read-only agent, a human executes: increase NodePool limit (blast radius: additional cost; rollback: reduce limit)
   - ⚠️ RECOMMENDATION ONLY — read-only agent, a human executes: cordon unhealthy node (blast radius: pods rescheduled; rollback: uncordon)
   - ⚠️ RECOMMENDATION ONLY — read-only agent, a human executes: drain node (blast radius: all pods evicted; rollback: pods reschedule automatically)
4. **Confidence** — number of confirming signals

## Decision tree

```
Node/scheduling issue
├── Pods Pending?
│   ├── Scheduling failure reason?
│   │   ├── Insufficient resources → Karpenter check (Step 3)
│   │   ├── Topology constraint → karpenter-consolidation skill
│   │   ├── Taint/affinity → check pod spec vs node labels
│   │   └── PVC unbound → not a node issue
│   └── No pending pods → check node health
├── Node NotReady?
│   ├── MemoryPressure → identify memory-heavy pods
│   ├── DiskPressure → check image/log usage
│   └── kubelet crash → check node_logs
└── Karpenter not provisioning?
    ├── Check NodePool limits
    ├── Check instance type availability
    └── Check disruption budget blocking replacement
```

## Related skills

- `karpenter-consolidation` — consolidation tuning, zone cap, disruption budgets
- `incident-triage` — if node issue is causing application-level impact
- `cost-explorer` — instance type cost optimization
- `helm-chart-app` — topology spread constraints in app values
