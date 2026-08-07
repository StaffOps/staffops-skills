---
name: chaos-engineering-patterns
description: Use when designing chaos experiments or running game days. Covers steady state hypothesis, experiment design (pod kill, network partition, CPU stress, disk fill), Litmus/Chaos Mesh CRDs, blast radius control, and abort conditions. Decision tree for what to break first based on SLO type.
---

# Chaos Engineering Patterns

## When to use

- Preparing for game days or chaos experiments
- Validating resilience claims before production launch
- Testing autoscaling, circuit breakers, or failover mechanisms
- Verifying that alerts fire correctly under failure conditions
- Building confidence in disaster recovery procedures
- Identifying single points of failure in architecture

## When NOT to use

- System is already in an incident (don't add chaos to chaos)
- No observability in place (can't measure impact without metrics)
- No rollback plan for the experiment (abort conditions undefined)
- Team hasn't agreed on blast radius (organizational readiness)
- Production system without error budget remaining

---

## Step 1: Define steady state hypothesis

Before breaking anything, document what "normal" looks like:

```markdown
## Steady State Hypothesis

**Service**: <service-name>
**SLO**: 99.9% availability, p99 latency < 500ms
**Current metrics (baseline)**:
- Error rate: <X>% (query: `rate(http_server_request_duration_seconds_count{status=~"5.."}[5m])`)
- p99 latency: <Y>ms
- Throughput: <Z> req/s

**Hypothesis**: When [fault injected], the system will:
- Maintain error rate < 1%
- Maintain p99 < 1000ms (degraded but acceptable)
- Recover within 60s of fault removal
```

---

## Step 2: Choose experiment type based on SLO

### Decision tree: what to break first

```
What SLO are you validating?
├── Availability (uptime)?
│   ├── Single replica → Pod kill experiment
│   ├── Multi-replica → Kill N-1 replicas simultaneously
│   └── Multi-AZ → AZ failure simulation
├── Latency (response time)?
│   ├── CPU-bound service → CPU stress experiment
│   ├── IO-bound service → Disk fill / slow IO
│   └── Network-bound → Network delay injection
├── Durability (data integrity)?
│   ├── Database → Kill primary, verify failover
│   ├── Queue → Fill queue, verify backpressure
│   └── Cache → Flush cache, verify cold-start behavior
└── Throughput (capacity)?
    ├── Horizontal scaling → Load + pod kill during scale-up
    └── Rate limiting → Burst traffic beyond limits
```

---

## Step 3: Experiment catalog

### Pod kill (availability)

```yaml
# Chaos Mesh — PodChaos
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: pod-kill-test
  namespace: chaos-testing
spec:
  action: pod-kill
  mode: fixed
  value: "1"
  selector:
    namespaces: [target-namespace]
    labelSelectors:
      app: target-service
  duration: "30s"
  scheduler:
    cron: "@every 2m"  # recurring (game day) or remove for one-shot
```

```yaml
# Litmus — ChaosEngine
apiVersion: litmuschaos.io/v1alpha1
kind: ChaosEngine
metadata:
  name: pod-kill-test
  namespace: target-namespace
spec:
  appinfo:
    appns: target-namespace
    applabel: app=target-service
  chaosServiceAccount: litmus-admin
  experiments:
  - name: pod-delete
    spec:
      components:
        env:
        - name: TOTAL_CHAOS_DURATION
          value: "30"
        - name: FORCE
          value: "false"
```

### Network partition (split-brain)

```yaml
# Chaos Mesh — NetworkChaos
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: network-partition
spec:
  action: partition
  mode: all
  selector:
    namespaces: [target-namespace]
    labelSelectors:
      app: service-a
  direction: both
  target:
    selector:
      namespaces: [target-namespace]
      labelSelectors:
        app: service-b
  duration: "60s"
```

### CPU stress (latency)

```yaml
# Chaos Mesh — StressChaos
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: cpu-stress
spec:
  mode: one
  selector:
    namespaces: [target-namespace]
    labelSelectors:
      app: target-service
  stressors:
    cpu:
      workers: 2
      load: 80  # percentage
  duration: "120s"
```

### Disk fill (durability)

```yaml
# Chaos Mesh — IOChaos (fill)
apiVersion: chaos-mesh.org/v1alpha1
kind: IOChaos
metadata:
  name: disk-fill
spec:
  action: fault
  mode: one
  selector:
    namespaces: [target-namespace]
    labelSelectors:
      app: target-service
  volumePath: /data
  path: "*"
  percent: 90
  duration: "60s"
```

---

## Step 4: Blast radius control

| Control | How |
|---------|-----|
| Namespace isolation | Run experiments only in designated namespaces |
| Label targeting | Target specific pods, never broad selectors |
| Duration limits | Always set `duration` — never open-ended |
| Time windows | Run only during business hours with team present |
| Single fault | One experiment at a time (don't stack failures) |
| Percentage mode | Kill 1 of 5 pods, not all (`mode: fixed, value: "1"`) |

```yaml
# Chaos Mesh — namespace-level protection (deny chaos on critical namespaces)
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
spec:
  selector:
    namespaces: [target-namespace]  # NEVER use kube-system, monitoring, etc.
```

---

## Step 5: Abort conditions

Define these BEFORE starting. If ANY trigger, abort immediately:

```markdown
## Abort Conditions

1. Error rate exceeds 5% (2x steady state tolerance)
2. p99 latency exceeds 5000ms for >30s
3. Data loss detected (missing writes, replication lag >60s)
4. Customer-facing impact confirmed (status page update triggered)
5. Team member calls abort (any reason, no questions asked)
6. Experiment runs longer than planned duration
7. Cascading failure detected (downstream services impacted beyond target)
```

### Automated abort (Chaos Mesh)

```yaml
# Use workflow with conditional abort
apiVersion: chaos-mesh.org/v1alpha1
kind: Workflow
metadata:
  name: safe-experiment
spec:
  entry: experiment
  templates:
  - name: experiment
    deadline: "5m"  # hard stop after 5 minutes regardless
```

---

## Step 6: Game day checklist

```markdown
### Before
- [ ] Steady state hypothesis documented
- [ ] Abort conditions defined and agreed
- [ ] Observability dashboards open (error rate, latency, saturation)
- [ ] Alerting confirmed working (test alert fires correctly)
- [ ] Rollback procedure documented and tested
- [ ] Team assembled and communication channel ready
- [ ] Change window approved (if production)

### During
- [ ] Announce experiment start in team channel
- [ ] Inject fault
- [ ] Observe metrics (does hypothesis hold?)
- [ ] Document actual behavior vs expected
- [ ] Remove fault (or let duration expire)
- [ ] Observe recovery (time to steady state?)

### After
- [ ] Document findings (passed/failed/unexpected)
- [ ] File follow-up tickets for weaknesses found
- [ ] Update runbooks if new failure mode discovered
- [ ] Share learnings with broader team
- [ ] Update SLO confidence level
```

---

## Anti-patterns

- ❌ Running chaos in production without error budget remaining
- ❌ No abort conditions defined before starting
- ❌ Experiments without observability (can't measure = can't learn)
- ❌ "Let's see what happens" without hypothesis (not science, just breaking things)
- ❌ Stacking multiple faults simultaneously (can't isolate cause)
- ❌ Running experiments outside agreed time windows
- ❌ Targeting shared infrastructure (monitoring, DNS, mesh control plane)
- ❌ Keeping experiment results undocumented (lost learnings)

---

## Related skills

- `sla-slo-design` — defining the SLOs that chaos experiments validate
- `error-budget-framework` — knowing when you have budget for experiments
- `incident-response-runbook` — what happens if chaos becomes a real incident
- `alerting-strategy` — verifying alerts fire correctly under failure
- `root-cause-analysis` — analyzing unexpected failures found during experiments
