---
name: cost-anomaly-detection
description: "Use when a cost spike appears in billing — AWS Cost Anomaly Detection, CUR queries via Athena, correlation with deploy/traffic changes. Decision tree: is it traffic, new resource, pricing change, or waste."
---

# Cost Anomaly Detection

## When to use

- Billing alert fires (cost exceeded threshold or anomaly detected)
- Monthly bill is higher than expected without obvious cause
- AWS Cost Anomaly Detection notifies of unusual spend
- Need to attribute a cost spike to a specific team, service, or event
- Post-incident cost impact assessment

## When NOT to use

- Data transfer-specific investigation (use `data-transfer-cost-analysis`)
- Long-term commitment evaluation (use `reserved-capacity-planning`)
- Routine right-sizing (use `ec2-rightsizing-patterns`)

## Investigation steps

### Step 1: Scope the spike

```bash
# Cost for last 7 days grouped by service
aws ce get-cost-and-usage \
  --time-period Start=$(date -d '7 days ago' +%Y-%m-%d),End=$(date +%Y-%m-%d) \
  --granularity DAILY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE

# Compare this week vs last week
aws ce get-cost-and-usage \
  --time-period Start=$(date -d '14 days ago' +%Y-%m-%d),End=$(date -d '7 days ago' +%Y-%m-%d) \
  --granularity DAILY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE
```

### Step 2: Check AWS Cost Anomaly Detection

```bash
# List recent anomalies
aws ce get-anomalies \
  --date-interval StartDate=$(date -d '30 days ago' +%Y-%m-%d),EndDate=$(date +%Y-%m-%d) \
  --max-results 10
```

### Step 3: Drill into the spike (CUR via Athena)

```sql
-- Daily cost by service + usage type (find the line item)
SELECT
  line_item_product_code AS service,
  line_item_usage_type AS usage_type,
  DATE(line_item_usage_start_date) AS day,
  SUM(line_item_unblended_cost) AS cost,
  SUM(line_item_usage_amount) AS usage
FROM cur_database.cur_table
WHERE month = '7' AND year = '2026'
  AND line_item_unblended_cost > 0
GROUP BY 1, 2, 3
ORDER BY cost DESC
LIMIT 50;
```

```sql
-- Spike attribution by resource ID
SELECT
  line_item_resource_id,
  line_item_usage_type,
  resource_tags_user_cost_center,
  resource_tags_user_environment,
  SUM(line_item_unblended_cost) AS cost
FROM cur_database.cur_table
WHERE month = '7'
  AND line_item_product_code = '<service-from-step-1>'
GROUP BY 1, 2, 3, 4
ORDER BY cost DESC
LIMIT 20;
```

### Step 4: Correlate with operational changes

```bash
# Recent deployments / scaling events
kubectl get events --all-namespaces --field-selector reason=Scaled \
  --sort-by='.lastTimestamp' | tail -20

# New nodes provisioned
kubectl get nodes --sort-by='.metadata.creationTimestamp' | tail -10
```

```promql
# Traffic increase? (HTTP request rate change vs 7d ago)
sum(rate(http_server_request_duration_seconds_count[1h]))
  /
sum(rate(http_server_request_duration_seconds_count[1h] offset 7d))
```

### Step 5: Check for waste

```bash
# Unattached EBS volumes
aws ec2 describe-volumes \
  --filters Name=status,Values=available \
  --query 'Volumes[].{ID:VolumeId,Size:Size,Type:VolumeType}'

# Stopped instances (still incur EBS costs)
aws ec2 describe-instances \
  --filters Name=instance-state-name,Values=stopped \
  --query 'Reservations[].Instances[].{ID:InstanceId,Type:InstanceType}'
```

## Decision tree: what caused the spike?

```
Cost spike detected
│
├── Same resources, higher usage?
│   ├── Traffic increase (requests/sec up)?
│   │   ├── Correlates with business event? → Expected growth
│   │   └── No business event? → Investigate (bot? retry storm?)
│   ├── Autoscaling kicked in? → Check if policy is too aggressive
│   └── Batch job ran longer? → Check input data size
│
├── New resources appeared?
│   ├── Recent deploy introduced new infra? → Attribute to team
│   ├── Karpenter provisioned bigger nodes? → Check pod requests
│   └── Manual creation (ClickOps)? → Tag, decide keep/delete
│
├── Same usage, higher cost?
│   ├── Savings Plan / RI expired? → Renew commitment
│   ├── Pricing tier change? → Expected at scale
│   └── Spot → On-Demand fallback? → Check Spot availability
│
└── Waste / zombie resources?
    ├── Unattached volumes? → Snapshot + delete
    ├── Idle load balancers? → Delete or consolidate
    ├── Dev resources left running? → Auto-stop policy
    └── Orphaned snapshots? → Lifecycle policy
```

## Proactive detection setup

```bash
# Create anomaly monitor
aws ce create-anomaly-monitor \
  --anomaly-monitor '{
    "MonitorName": "all-services",
    "MonitorType": "DIMENSIONAL",
    "MonitorDimension": "SERVICE"
  }'

# Budget alert at 80% threshold
aws budgets create-budget \
  --account-id <account-id> \
  --budget '{
    "BudgetName": "monthly-total",
    "BudgetLimit": {"Amount": "50000", "Unit": "USD"},
    "TimeUnit": "MONTHLY",
    "BudgetType": "COST"
  }' \
  --notifications-with-subscribers '[{
    "Notification": {
      "NotificationType":"ACTUAL",
      "ComparisonOperator":"GREATER_THAN",
      "Threshold":80
    },
    "Subscribers": [{"SubscriptionType":"EMAIL","Address":"finops@company.com"}]
  }]'
```

## Anti-patterns

- ❌ Reacting only at month-end (waste accumulates 30 days)
- ❌ Looking only at service-level totals (hides resource-level spikes)
- ❌ Blaming "traffic increase" without verifying with metrics
- ❌ No tagging → impossible to attribute cost to team/service
- ❌ Ignoring small spikes ($50-100) that compound monthly
- ❌ Not correlating with deploy events
- ❌ Assuming Spot savings are permanent (interruptions cause OD fallback)

## Related skills

- `data-transfer-cost-analysis` — Deep dive into transfer-specific costs
- `reserved-capacity-planning` — When spike is due to expired commitments
- `ec2-rightsizing-patterns` — When spike is due to over-provisioned compute
- `untagged-resources-bulk-fix` — When attribution fails due to missing tags
