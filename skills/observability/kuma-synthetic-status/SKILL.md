---
name: kuma-synthetic-status
description: "Use when you need to verify whether an API endpoint is actually responding from an external perspective (synthetic test), check endpoint latency as seen by clients, determine 24h/30d uptime ratios, or identify which monitors are currently DOWN. Queries Uptime Kuma metrics already scraped into VictoriaMetrics (job=\"kuma-nv\"). Covers: DPM Platform (People, Companies, Custom, Batch, Tokens), Plugins (Validations), and DevOps health endpoints (Grafana, ArgoCD, Harbor, Alertmanager). This is the ground-truth check when internal metrics say \"healthy\" but clients report failures."
---

# Kuma Synthetic Test Status

## When to use this skill

- Internal metrics show healthy but clients report the API is broken
- Need external validation that an endpoint is actually responding
- Investigating a SEV-1/2 and need to confirm user impact from outside
- Checking endpoint latency as experienced by clients (not internal p99)
- Reviewing 24h/30d SLA compliance for a specific product
- Identifying all currently-DOWN monitors across the platform

## When this skill does NOT apply

- Internal service metrics investigation → use `incident-triage` or APM skills
- OTel pipeline health → use `collector-internal-metrics`
- Configuring or creating Kuma monitors → that's the synthetictests repo
- Kuma instance itself unreachable → check `up{job="kuma-nv"}` first

## CRITICAL: This is EXTERNAL validation

Kuma tests from **outside** the cluster, as a real client would. If `monitor_status == 0` (DOWN), the endpoint is genuinely unreachable to users — regardless of what internal pod status or metrics say. This is the ultimate ground-truth for "is it working for clients?"

## Step 1: Check if a specific endpoint is UP or DOWN

```promql
# People API — is it responding?
monitor_status{job="kuma-nv", monitor_name=~".*Pessoas.*Basic Data.*"}

# Companies API
monitor_status{job="kuma-nv", monitor_name=~".*Empresas.*Basic Data.*"}

# Token generation
monitor_status{job="kuma-nv", monitor_name=~".*TOKENS-API.*"}

# Any Platform endpoint
monitor_status{job="kuma-nv", monitor_name=~".*DPM.*"}
```

**Values**: 1 = UP, 0 = DOWN, 2 = PENDING (recovering)

## Step 2: Check response time (client-perceived latency)

```promql
# Current response time for People API
monitor_response_time{job="kuma-nv", monitor_name=~".*Pessoas.*Basic Data.*"}

# All DPM endpoints sorted by latency
sort_desc(monitor_response_time{job="kuma-nv", monitor_name=~".*DPM.*"})

# Endpoints above 5s (approaching timeout)
monitor_response_time{job="kuma-nv"} > 5000
```

**Thresholds**: Normal ~370ms (24h avg). Warning > 5000ms. Critical > 10000ms (timeout is 24s).

## Step 3: Check uptime ratio (SLA compliance)

```promql
# 24h uptime for People API
monitor_uptime_ratio{job="kuma-nv", monitor_name=~".*Pessoas.*", window="1d"}

# 30d uptime — SLA compliance view
monitor_uptime_ratio{job="kuma-nv", monitor_name=~".*Pessoas.*", window="30d"}

# All monitors below 99% in 24h (SLA breach candidates)
monitor_uptime_ratio{job="kuma-nv", window="1d"} < 0.99
```

**Thresholds**: < 99% (24h) = warning. < 95% (30d) = critical persistent issue.

## Step 4: Find all DOWN monitors (platform-wide outage check)

```promql
# Everything currently DOWN
monitor_status{job="kuma-nv", monitor_type!~"group|http"} == 0

# Everything PENDING (recovering)
monitor_status{job="kuma-nv"} == 2

# Count of DOWN monitors (blast radius)
count(monitor_status{job="kuma-nv", monitor_type!~"group|http"} == 0)
```

If multiple monitors are DOWN simultaneously → likely infrastructure issue (shared dependency, network, DNS).

## Step 5: Check DevOps infrastructure endpoints

```promql
# Grafana
monitor_status{job="kuma-nv", monitor_name=~".*Grafana.*"}

# ArgoCD
monitor_status{job="kuma-nv", monitor_name=~".*ArgoCD.*"}

# Harbor
monitor_status{job="kuma-nv", monitor_name=~".*Harbor.*"}

# All infra endpoints
monitor_status{job="kuma-nv", monitor_name=~".*(Grafana|ArgoCD|Harbor|Alertmanager|Loki|Tempo|Pyroscope).*"}
```

## Step 6: Check Kuma itself is healthy

```promql
# Is Kuma reachable? (if not, ALL synthetic tests are blind)
up{job="kuma-nv"}
```

If `up{job="kuma-nv"} == 0` → Kuma is unreachable. All monitor data is stale. This is itself a critical issue.

## Step 7: Summarize findings

1. **Endpoint status** — UP / DOWN / PENDING (cite monitor_name and value)
2. **Response time** — current ms vs normal (~370ms baseline)
3. **SLA compliance** — 24h and 30d uptime ratios
4. **Blast radius** — how many monitors are DOWN? Is it isolated or platform-wide?
5. **Confidence** — Kuma itself is UP (data is fresh) or DOWN (data is stale, cannot trust)

## Decision tree

```
Need to verify an endpoint is working for clients?
├── Check Kuma is UP: up{job="kuma-nv"} == 1?
│   ├── No → Kuma unreachable — data is stale, cannot validate
│   └── Yes → proceed
├── Check specific endpoint: monitor_status{monitor_name=~".*<name>.*"}
│   ├── 1 (UP) → Endpoint is responding from outside. If clients still report issues, it's intermittent or client-specific
│   ├── 0 (DOWN) → CONFIRMED DOWN from external perspective. User impact confirmed.
│   └── 2 (PENDING) → Recovering, may be intermittent
├── Check latency: monitor_response_time{monitor_name=~".*<name>.*"}
│   ├── < 1000ms → Normal
│   ├── 1000-5000ms → Elevated but responding
│   └── > 5000ms → Approaching timeout, effectively degraded
└── Check blast radius: count(monitor_status == 0)
    ├── 1 endpoint → Isolated issue (specific service)
    ├── Multiple in same group → Shared dependency failure
    └── Platform-wide → Infrastructure issue (DNS, network, load balancer)
```

## Monitor groups and what they cover

| Group | Endpoints | Tests | Assertion |
|-------|-----------|-------|-----------|
| DPM-ERROR-CLIENTAPI | `/pessoas`, `/empresas`, `/customizado`, `/processos`, `/veiculos`, `/enderecos`, `/produtos` | 20 | `Status.*[0].Message == "OK"` |
| DPM-TIME-CLIENTAPI | Same + `/pessoas` GA variant | 20 | Same (timeout-focused) |
| DPM-ERROR-BATCHAPI | Batch mode endpoints | 7 | Same |
| DPM-CUSTOM | OnDemand, Tokens API | 3 | `Status.*[0].Message == "OK"` / `success == "true"` |
| PLUGINS-ERROR-CLIENTAPI | `plugin.<org-domain>/validacoes` | 16 | Same |
| DEVOPS | Health endpoints (alertmanager, argocd, grafana, harbor, etc.) | 20 | HTTP 200 |

**Total: 90 monitors** covering the full external surface.

## Quick one-liners (copy-paste for fast triage)

```promql
# EVERYTHING DOWN right now (blast radius check)
count(monitor_status{job="kuma-nv"} == 0)

# All endpoints with latency above 5s (degraded)
monitor_response_time{job="kuma-nv"} > 5000

# SLA breaches in last 24h (any monitor below 99%)
monitor_uptime_ratio{job="kuma-nv", window="1d"} < 0.99

# Is Kuma itself alive? (if not, all data is stale)
up{job="kuma-nv"}

# DPM Platform — all endpoints status at a glance
monitor_status{job="kuma-nv", monitor_name=~".*DPM.*"}
```

## Related skills

- `plataforma-api-semantics` — understanding Platform error model (5xx ≠ error)
- `incident-triage` — severity classification after confirming user impact
- `product-escalation-map` — who to escalate to based on affected endpoint
- `observability-tooling` — route to other investigation tools after confirming external impact
