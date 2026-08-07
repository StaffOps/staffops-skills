---
name: data-transfer-cost-analysis
description: "Use when investigating high data transfer costs in AWS/cloud — cross-AZ, cross-region, internet egress. Covers VPC Flow Logs analysis, OTel eBPF network metrics, NAT Gateway costs, ELB cross-AZ charges, and S3 transfer patterns."
---

# Data Transfer Cost Analysis

## When to use

- Monthly bill shows unexpected data transfer charges
- Cost Explorer reveals "EC2-Other" or "DataTransfer" line item spikes
- Need to identify which workloads generate cross-AZ or internet egress traffic
- Planning architecture to minimize transfer costs
- Investigating NAT Gateway processing charges

## When NOT to use

- General cost optimization without a transfer-specific signal (use `cost-anomaly-detection`)
- Evaluating commitment purchases (use `reserved-capacity-planning`)
- Network connectivity troubleshooting without cost context

## Data transfer cost hierarchy

From most to least expensive (AWS):

| Path | Cost (approx.) | Example |
|------|----------------|---------|
| Internet egress | $0.09/GB | Pod → external API |
| Cross-region | $0.02/GB | S3 replication us-east-1 → eu-west-1 |
| NAT Gateway processing | $0.045/GB | Pod → internet via NAT |
| Cross-AZ (same region) | $0.01/GB each direction | Pod AZ-a → Pod AZ-b |
| Same-AZ | Free | Pod → Pod (same AZ) |
| S3 → CloudFront | Free | Origin fetch |
| VPC endpoints | $0.01/GB (but saves NAT) | Pod → S3 via gateway endpoint |

## Investigation steps

### Step 1: Identify the category (Cost Explorer)

```sql
-- CUR via Athena — top transfer costs by usage type
SELECT
  line_item_usage_type,
  product_from_location,
  product_to_location,
  SUM(line_item_unblended_cost) AS cost,
  SUM(line_item_usage_amount) AS gb_transferred
FROM cur_database.cur_table
WHERE line_item_product_code = 'AmazonEC2'
  AND line_item_usage_type LIKE '%DataTransfer%'
  AND month = '7' AND year = '2026'
GROUP BY 1, 2, 3
ORDER BY cost DESC
LIMIT 20;
```

### Step 2: Cross-AZ traffic (biggest hidden cost)

```promql
# OTel eBPF inter-zone bytes by workload
sum by (source_workload, destination_workload, source_zone, destination_zone) (
  rate(network_io_bytes_total{
    source_zone!="", destination_zone!="",
    source_zone!=destination_zone
  }[1h])
)
```

```promql
# Estimated monthly cross-AZ cost ($0.01/GB each direction = $0.02 round-trip)
sum by (source_workload, destination_workload) (
  increase(network_io_bytes_total{source_zone!=destination_zone}[30d])
) / 1e9 * 0.02
```

### Step 3: NAT Gateway charges

```sql
-- CUR — NAT Gateway processing costs
SELECT
  line_item_resource_id,
  SUM(line_item_usage_amount) AS gb_processed,
  SUM(line_item_unblended_cost) AS cost
FROM cur_database.cur_table
WHERE line_item_usage_type LIKE '%NatGateway%'
  AND month = '7'
GROUP BY 1
ORDER BY cost DESC;
```

### Step 4: VPC Flow Logs — top talkers

```sql
-- Athena on VPC Flow Logs
SELECT
  srcaddr, dstaddr, protocol,
  SUM(bytes) AS total_bytes,
  COUNT(*) AS flow_count
FROM vpc_flow_logs
WHERE action = 'ACCEPT'
  AND start >= cast('2026-07-01' as timestamp)
GROUP BY 1, 2, 3
ORDER BY total_bytes DESC
LIMIT 50;
```

### Step 5: S3 cross-region transfers

```sql
SELECT
  line_item_resource_id AS bucket,
  product_from_location, product_to_location,
  SUM(line_item_usage_amount) AS gb,
  SUM(line_item_unblended_cost) AS cost
FROM cur_database.cur_table
WHERE line_item_product_code = 'AmazonS3'
  AND line_item_usage_type LIKE '%DataTransfer%'
  AND month = '7'
GROUP BY 1, 2, 3
ORDER BY cost DESC;
```

## Decision tree: reducing transfer costs

```
High transfer costs?
├── Internet egress dominant?
│   ├── Cacheable content? → CloudFront (S3→CF is free)
│   ├── API responses? → Compress (gzip/brotli), paginate
│   └── Pulling from external? → Cache locally (Redis/S3)
├── Cross-AZ dominant?
│   ├── Service-to-service? → Topology-aware routing (Istio locality)
│   ├── DB replication? → Expected, document as baseline
│   └── Log/metric shipping? → Colocate collector with source
├── NAT Gateway dominant?
│   ├── S3/DynamoDB access? → VPC Gateway Endpoint (free)
│   ├── ECR pulls? → VPC Interface Endpoint or pull-through cache
│   └── SQS/SNS/Secrets Manager? → VPC Interface Endpoint
└── Cross-region dominant?
    ├── S3 replication? → Evaluate necessity, use same-region replica
    └── App calling cross-region service? → Deploy service locally
```

## Common culprits

| Culprit | Typical monthly cost | Fix |
|---------|---------------------|-----|
| NAT Gateway for S3 | $500-5000+ | S3 Gateway Endpoint (free) |
| Cross-AZ service mesh | $200-2000+ | Topology-aware routing |
| ELB cross-AZ to pods | $100-1000+ | Zone-affinity |
| ECR pulls via NAT | $50-500+ | ECR VPC Endpoint |
| CloudWatch Logs egress | $100-1000+ | Reduce volume, filter at source |

## Anti-patterns

- ❌ Ignoring "EC2-Other" charges (often hides massive transfer costs)
- ❌ Multi-AZ everything without calculating the cross-AZ tax
- ❌ NAT Gateway for AWS service access when VPC Endpoints exist
- ❌ S3 bucket in different region than compute workloads
- ❌ Assuming "internal traffic is free" (cross-AZ is NOT free)
- ❌ Not using topology-aware routing when service mesh supports it

## Related skills

- `cost-anomaly-detection` — Initial triage of cost spikes
- `reserved-capacity-planning` — Commitment decisions for compute
- `otel-ebpf-instrumentation` — Network metrics for inter-zone visibility
