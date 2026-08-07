---
name: reserved-capacity-planning
description: "Use when evaluating commitment purchases (Reserved Instances, Savings Plans, capacity reservations). Covers utilization analysis, break-even calculation, coverage gaps, and the broader decision framework."
---

# Reserved Capacity Planning

## When to use

- Evaluating whether to purchase Savings Plans, Reserved Instances, or Capacity Reservations
- Current commitments approaching expiration (renewal decision)
- Significant On-Demand spend that could benefit from commitments
- Planning commitment portfolio for a new workload or expansion
- Assessing break-even point for commitment vs On-Demand

## When NOT to use

- Savings Plans-specific strategy details (use `savings-plans-strategy`)
- Instance type selection / right-sizing (use `ec2-rightsizing-patterns`)
- Investigating cost spikes (use `cost-anomaly-detection`)

## Commitment types comparison

| Type | Flexibility | Discount | Term | Best for |
|------|-------------|----------|------|----------|
| Compute Savings Plan | Any family/region/OS | 30-40% | 1yr/3yr | K8s, variable workloads |
| EC2 Instance SP | Specific family+region | 40-50% | 1yr/3yr | Stable, predictable |
| Standard RI | Specific type+AZ | 40-60% | 1yr/3yr | Legacy (rarely best now) |
| Convertible RI | Exchangeable | 30-45% | 1yr/3yr | Long-term + flexibility |
| On-Demand Capacity Reservation | Guaranteed capacity | 0% | None | Mission-critical AZ guarantee |
| Spot | Interruption-tolerant | 60-90% | None | Batch, fault-tolerant |

## Investigation steps

### Step 1: Current spend profile

```bash
# On-Demand vs covered spend (last 3 months)
aws ce get-cost-and-usage \
  --time-period Start=$(date -d '90 days ago' +%Y-%m-%d),End=$(date +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=PURCHASE_TYPE

# Current SP coverage
aws ce get-savings-plans-coverage \
  --time-period Start=$(date -d '30 days ago' +%Y-%m-%d),End=$(date +%Y-%m-%d) \
  --granularity MONTHLY

# Current SP utilization
aws ce get-savings-plans-utilization \
  --time-period Start=$(date -d '30 days ago' +%Y-%m-%d),End=$(date +%Y-%m-%d) \
  --granularity MONTHLY
```

### Step 2: Find the steady-state baseline

```sql
-- CUR: hourly On-Demand compute cost (find the floor)
SELECT
  DATE_TRUNC('hour', line_item_usage_start_date) AS hour,
  SUM(line_item_unblended_cost) AS od_cost
FROM cur_database.cur_table
WHERE line_item_product_code = 'AmazonEC2'
  AND pricing_term = 'OnDemand'
  AND line_item_line_item_type = 'Usage'
  AND line_item_usage_type LIKE '%BoxUsage%'
  AND month >= '5'
GROUP BY 1
ORDER BY 1;
-- MINIMUM hourly cost = safe commitment floor
```

### Step 3: Break-even analysis

```
Break-even formula:
  Monthly savings = OD_monthly - SP_monthly_effective
  Months to break-even (upfront) = Upfront / Monthly_savings

Example:
  On-Demand: $10,000/month
  3yr No Upfront Compute SP: $6,500/month (35% off)
  Monthly savings: $3,500
  Total 3yr savings: $126,000

  IF workload drops 50% after 12 months:
  Net = ($3,500 × 12) + (-$3,250 × 24) = -$36,000 LOSS
  → Only commit what stays for full term
```

### Step 4: AWS recommendations

```bash
# Savings Plans recommendations
aws ce get-savings-plans-purchase-recommendation \
  --savings-plans-type COMPUTE_SP \
  --term-in-years THREE_YEARS \
  --payment-option NO_UPFRONT \
  --lookback-period-in-days SIXTY_DAYS
```

### Step 5: Coverage target

```
Optimal coverage = 70-80% of steady-state baseline

Why not 100%:
- Traffic varies (nights, weekends, seasonality)
- Workloads change (migrations, decommissions)
- Over-commitment = paying for unused capacity

Remaining 20-30%:
- Spot (60-90% discount, interruption-tolerant)
- On-Demand (peaks, new workloads, testing)
```

## Decision tree: which commitment?

```
Need to commit?
├── Stable for 1-3 years?
│   ├── Instance family will change (K8s)? → Compute SP
│   ├── Instance family is fixed (DB)? → EC2 Instance SP
│   └── Need guaranteed AZ capacity? → ODCR + SP/RI
├── Growing but direction unclear?
│   └── Commit to floor only (70%) → Compute SP 1yr No Upfront
├── Might shrink or migrate?
│   ├── <12 months certainty? → Stay On-Demand + Spot
│   ├── 12-24 months? → 1yr No Upfront
│   └── Migrating service type? → Compute SP (covers all)
└── Payment option?
    ├── Max discount? → All Upfront
    ├── Cash flow flexibility? → No Upfront
    └── Compromise? → Partial Upfront
```

## Portfolio strategy

| Layer | Coverage | Vehicle | Risk |
|-------|----------|---------|------|
| Base (always-on) | 60-70% | 3yr Compute SP No Upfront | Low |
| Growth buffer | 10-15% | 1yr Compute SP No Upfront | Medium |
| Variable | 15-30% | Spot + On-Demand | None |

**Review cadence**: quarterly reassessment of baseline + gaps.

## Renewal checklist

- [ ] Utilization of expiring commitment (was it fully used?)
- [ ] Forecast next-term usage (growing/shrinking/migrating?)
- [ ] Instance family still correct? (or switch to Compute SP)
- [ ] 1yr vs 3yr based on stability confidence
- [ ] Spot coverage increased? (reduces commitment need)
- [ ] Planned migration that would strand the commitment?

## Anti-patterns

- ❌ Committing to 100% of current spend (no room for variance)
- ❌ 3yr All Upfront for volatile workloads (max lock-in + risk)
- ❌ Buying RIs when SP covers with more flexibility
- ❌ Not checking utilization before buying more
- ❌ Committing before right-sizing (commit to waste = locked-in waste)
- ❌ Single annual purchase (stagger quarterly for flexibility)
- ❌ Ignoring Spot as part of the portfolio
- ❌ Per-account SP when Organization-level could share benefits

## Related skills

- `savings-plans-strategy` — SP-specific deep dive
- `ec2-rightsizing-patterns` — Right-size BEFORE committing
- `cost-anomaly-detection` — Detect expired commitment spikes
- `karpenter-consolidation` — Node optimization affects sizing
