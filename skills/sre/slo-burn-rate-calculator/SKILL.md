---
name: slo-burn-rate-calculator
description: "Use when an SLO burn rate alert fires, when assessing budget health during an incident, or when determining how long until the error budget exhausts at the current rate. Runs a bundled Python script that calculates multi-window burn rates (1h/6h/24h/72h) per the Google SRE Workbook model, classifies severity (CRITICAL_PAGE → WATCH), and recommends action. Requires sandbox. Collect error/total counts from VictoriaMetrics first."
---

# SLO Burn Rate Calculator (Executable)

## When to use this skill

- SLO burn rate alert fired (P1/P2/P3)
- Need to quantify "how bad is this?" during an incident
- Assessing whether current error rate will exhaust budget before period end
- Comparing burn rates across windows to distinguish spike vs sustained degradation

## When this skill does NOT apply

- Defining SLOs from scratch → use `sla-slo-design`
- Creating burn rate alert rules → use `error-budget-framework`
- General incident triage → use `incident-triage`
- Sandbox not enabled → this skill requires the sandbox environment

## Step 1: Collect error and total counts per window

Query VictoriaMetrics for the service under investigation. Use the CORRECT labels (`service_namespace`, `http_response_status_code`):

```
→ query: sum(increase(http_server_request_duration_seconds_count{service_namespace="dpm", http_response_status_code=~"5.."}[1h]))
→ query: sum(increase(http_server_request_duration_seconds_count{service_namespace="dpm"}[1h]))
→ repeat for 6h, 24h, 72h windows
```

> ⚠️ **Plataforma trap**: DPM/DCP/APPS APIs return HTTP 200 for everything. Use `BigBoost_SQStoLogStats_Requests_NumberOfQueries_total{AnyError="True"}` as the error count instead. See `plataforma-api-semantics`.

## Step 2: Write data file

```bash
cat > /tmp/slo_data.json << 'EOF'
{
  "service": "DataPlatform.People",
  "slo_target": 0.999,
  "budget_period_days": 30,
  "windows": {
    "1h":  {"errors": 12, "total": 8500},
    "6h":  {"errors": 45, "total": 51000},
    "24h": {"errors": 120, "total": 204000},
    "72h": {"errors": 290, "total": 612000}
  }
}
EOF
```

## Step 3: Extract and run the calculator

```bash
sed -n '/^```python$/,/^```$/p' /aidevops/skills/user/slo-burn-rate-calculator/references/burn-rate-script.md | sed '1d;$d' > /tmp/burn_rate.py
python3 /tmp/burn_rate.py --data-file /tmp/slo_data.json
```

Optional overrides: `--target 0.9999` (stricter SLO), `--budget-days 7` (weekly budget).

## Step 4: Interpret the output

The script classifies per the Google SRE multi-window model:

| Status | Meaning | Action |
|--------|---------|--------|
| `CRITICAL_PAGE` | Budget exhausts within hours | Immediate action |
| `WARNING_TICKET` | Sustained elevated burn | P2 ticket |
| `WARNING` | Fast burn in short window | Investigate now |
| `SLOW_BURN_TICKET` | Will exhaust before period end | Create ticket |
| `WATCH` | Elevated but sustainable | Monitor |
| `ok` | Within budget | No action |

Key insight: if 1h window shows CRITICAL but 72h shows `ok` → **spike, not sustained**. If both 1h and 72h show WARNING → **sustained degradation, budget in real danger**.

## Step 5: Summarize findings

1. **Status** — worst severity across all windows
2. **Burn rate** — cite the numeric burn_rate per window
3. **Time to exhaustion** — hours_to_exhaustion at current rate
4. **Recommendation** — action from the calculator output
5. **Confidence** — based on data volume (total requests in each window)

## Decision tree

```
SLO alert fired or budget concern?
├── Collect error/total per window via VictoriaMetrics
│   ├── DPM/DCP/APPS? → Use BigBoost AnyError, NOT http 5xx
│   └── Other services? → Use http_response_status_code=~"5.."
├── Run burn_rate.py
├── Read worst_status:
│   ├── CRITICAL_PAGE → Report as SEV-1, recommend immediate action
│   ├── WARNING* → Report as SEV-2, recommend investigation
│   ├── SLOW_BURN → Report as SEV-3, recommend ticket
│   └── ok/WATCH → Report healthy, no action
└── Compare windows:
    ├── Short window bad, long window ok → spike (may self-resolve)
    └── All windows bad → sustained degradation (escalate)
```

## Related skills

- `error-budget-framework` — alert rule design for burn rates
- `sla-slo-design` — choosing SLO targets and SLIs
- `incident-triage` — severity classification
- `plataforma-api-semantics` — correct error counting for Plataforma
