---
name: deploy-correlation-checker
description: >
  Use when an anomaly is detected and you need to determine if a recent deploy caused it.
  Cross-references deploy timestamps (from ArgoCD) with metric anomaly start times. Identifies
  the most likely causal deploy by temporal proximity. Requires sandbox. Collect deploy history
  and anomaly timestamps from ArgoCD MCP and VictoriaMetrics first.
---

# Deploy Correlation Checker (Executable)

## When to use this skill

- Anomaly detected and you suspect a recent deploy caused it
- Multiple deploys happened recently — which one is the culprit?
- Need to determine if the issue is deploy-related or infrastructure-related
- Building the timeline for a root cause analysis

## When this skill does NOT apply

- No recent deploys (cause is clearly not a deploy) → use `metric-correlation-analysis`
- Need to check ArgoCD sync status → use `argocd-metrics`
- Need to check Rollout canary progress → use `gitops-environments`
- Sandbox not enabled → this skill requires the sandbox environment

## Step 1: Collect recent deploys from ArgoCD

```
→ gitops_apps_list(namespace="<target-namespace>")
→ For each app with recent sync: get sync time, image tag, and namespace
```

Note: Argo Rollouts are the standard in PRD. Check `rollout_info{exported_namespace="<target-namespace>"}` for recent image changes.

## Step 2: Identify anomaly start times

From a prior investigation step (metric-correlation-analysis, incident-triage, or manual observation):
- When did the error rate start increasing?
- When did latency spike?
- When did the alert fire?

## Step 3: Write data file

```bash
cat > /tmp/deploy_data.json << 'EOF'
{
  "deploys": [
    {"service": "<service-a>", "timestamp": "2026-08-06T14:00:00Z", "image_tag": "v2.3.1", "namespace": "<target-namespace>"},
    {"service": "<service-b>", "timestamp": "2026-08-06T13:45:00Z", "image_tag": "v1.8.0", "namespace": "<target-namespace>"},
    {"service": "<service-c>", "timestamp": "2026-08-06T12:30:00Z", "image_tag": "v3.1.2", "namespace": "<target-namespace>"}
  ],
  "anomalies": [
    {"metric": "http_error_rate", "started_at": "2026-08-06T14:03:00Z", "value": 0.12},
    {"metric": "latency_p99", "started_at": "2026-08-06T14:05:00Z", "value": 2.8}
  ]
}
EOF
```

## Step 4: Run the correlation checker

```bash
sed -n '/^```python$/,/^```$/p' /aidevops/skills/user/deploy-correlation-checker/references/deploy-corr-script.md | sed '1d;$d' > /tmp/deploy_corr.py
python3 /tmp/deploy_corr.py --data-file /tmp/deploy_data.json --window 30
```

`--window 30` = only consider deploys within 30 minutes before the anomaly.

## Step 5: Interpret results

Key fields:
- `common_cause_deploy` — if ALL anomalies point to the same deploy → strong rollback candidate
- `correlation_strength` — 1.0 = deploy was seconds before anomaly, 0.0 = at edge of window
- `verdict: "No deploys found"` → cause is NOT a deploy (look at infra/dependencies)

## Step 6: Summarize findings

1. **Correlation** — deploy-caused or non-deploy-caused?
2. **Candidate** — which specific deploy (service + image_tag)?
3. **Timing** — how many minutes between deploy and first anomaly?
4. **Confidence** — correlation_strength + number of anomalies pointing to same deploy
5. **Action** — rollback recommendation (⚠️ RECOMMENDATION ONLY) or redirect to non-deploy investigation

## Decision tree

```
Anomaly detected — was it a deploy?
├── Collect recent deploys + anomaly timestamps
├── Run deploy_corr.py
├── Result:
│   ├── common_cause_deploy found → STRONG: one deploy caused all anomalies
│   │   └── ⚠️ RECOMMENDATION ONLY: Rollback via ArgoCD
│   ├── Multiple deploys in window → Each anomaly may have different cause
│   │   └── Investigate each deploy independently
│   └── No deploys in window → NOT deploy-caused
│       └── Investigate: traffic spike, dependency failure, infra issue
```

## Related skills

- `argocd-metrics` — ArgoCD sync failures and reconciliation health
- `gitops-environments` — which repo controls which service
- `metric-correlation-analysis` — find the anomaly timestamps to feed this skill
- `incident-triage` — overall severity classification
