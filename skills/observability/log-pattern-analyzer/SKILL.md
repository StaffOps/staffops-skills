---
name: log-pattern-analyzer
description: "Use when investigating log volume spikes, identifying dominant error patterns, or detecting anomalous log messages during an incident. Runs a bundled Python script that normalizes log lines into patterns, clusters errors by similarity, and detects time-based spikes. Handles large log dumps that are impractical to reason over manually. Requires sandbox. Collect logs from Loki MCP first."
---

# Log Pattern Analyzer (Executable)

## When to use this skill

- Log volume spiked and you need to identify what's new/different
- Need to find the dominant error pattern among hundreds of error lines
- Want to detect temporal clustering (did errors all happen in one minute?)
- Raw log dump is too large to read manually (>100 lines)
- Need to quantify error rate from a log sample

## When this skill does NOT apply

- Building LogQL queries → use `loki-logql-patterns`
- Loki/Tempo backend health → use `loki-tempo-self-metrics`
- Single specific error to trace → use `tempo-trace-investigation`
- Sandbox not enabled → this skill requires the sandbox environment

## Step 1: Collect logs from Loki

Query Loki for the relevant logs. Get enough lines for statistical significance (50-500):

### LogQL patterns for collection (copy-paste)

```logql
# Errors from a specific service (most common starting point)
{service_namespace="dpm", service_workload="dpm-people-api"} |= "error" | json

# All errors in a namespace (broader investigation)
{service_namespace="dpm"} | json | level="error"

# Specific HTTP status codes (5xx)
{service_namespace="dpm"} | json | status >= 500

# Errors with stack traces (multi-line captured by Fluent Bit)
{service_namespace="dpm", service_workload="dpm-people-api"} |= "Exception" or |= "Traceback"

# Volume spike investigation — ALL logs in time window (not filtered)
{service_namespace="dpm", service_workload="dpm-people-api"}

# Logs from a specific pod (when you know the pod)
{pod="dpm-people-api-7f8d9c-abc12"} | json

# Correlated by trace_id (after finding trace in Tempo)
{service_namespace="dpm"} | json | trace_id="abc123def456"

# Timeout/connection errors specifically
{service_namespace="dpm"} |~ "timeout|connection refused|ETIMEDOUT|ECONNRESET"

# Rate-limited or throttled
{service_namespace="dpm"} |~ "429|rate.?limit|throttl"

# OOM-related messages
{service_namespace="dpm"} |~ "OutOfMemory|OOM|memory.?limit|allocation failed"
```

### MCP tool invocation examples

```
→ query_loki_logs(datasourceUid="loki", logql='{service_namespace="dpm", service_workload="dpm-people-api"} |= "error"', limit=200, direction="backward")
```

Or for all logs in a time window (not just errors):
```
→ query_loki_logs(datasourceUid="loki", logql='{service_namespace="dpm"}', limit=500, startRfc3339="now-30m")
```

### Quick volume check BEFORE heavy queries

```
→ query_loki_stats(datasourceUid="loki", logql='{service_namespace="dpm", service_workload="dpm-people-api"}')
```

This returns approximate stream count / bytes — confirms data exists before running expensive log queries.

## Step 2: Write log data to file

Format as JSON with optional timestamps and levels:

```bash
cat > /tmp/logs.json << 'EOF'
{
  "lines": [
    {"timestamp": "2026-08-06T14:02:00Z", "message": "Connection refused to redis:6379", "level": "ERROR"},
    {"timestamp": "2026-08-06T14:02:01Z", "message": "Request completed in 150ms path=/api/v1/people", "level": "INFO"},
    {"timestamp": "2026-08-06T14:02:01Z", "message": "Connection refused to redis:6379", "level": "ERROR"},
    {"timestamp": "2026-08-06T14:02:02Z", "message": "Timeout waiting for response from mongodb:27017", "level": "ERROR"}
  ]
}
EOF
```

## Step 3: Extract and run the analyzer

```bash
sed -n '/^```python$/,/^```$/p' /aidevops/skills/user/log-pattern-analyzer/references/pattern-script.md | sed '1d;$d' > /tmp/log_analyzer.py
python3 /tmp/log_analyzer.py --data-file /tmp/logs.json --top 20
```

Options: `--top 30` (more patterns), `--min-count 1` (show even single-occurrence patterns).

## Step 4: Interpret the output

Key sections in the JSON output:

### `top_patterns` — what's flooding the logs
```json
{"pattern": "Connection refused to <IP>", "count": 847, "percentage": 42.3}
```
The top pattern at 42% means one error type dominates — focus investigation there.

### `error_analysis` — error clustering
```json
{"total_errors": 1200, "error_rate_pct": 60.0, "top_error_patterns": [...]}
```
If one error pattern is >80% of errors → single root cause likely.

### `time_analysis` — temporal distribution
```json
{"spike_detected": true, "rate": {"max_per_minute": 450, "max_at": "2026-08-06T14:02:00", "mean_per_minute": 12}}
```
Spike detected = errors concentrated in time (correlate with deploy/event).

### `interpretation` — auto-severity
- `severity: HIGH` = >20% error rate
- `pattern_diversity: HIGH` = logs are mostly unique (high-cardinality issue)
- `SPIKE DETECTED` = temporal clustering (look for trigger event at that timestamp)

## Step 5: Summarize findings

1. **Dominant pattern** — what single pattern accounts for most of the volume?
2. **Error rate** — what % of total logs are errors?
3. **Temporal cluster** — did errors spike at a specific time? (correlate with deploys)
4. **Pattern diversity** — is it one problem or many?
5. **Recommendation** — investigate the dominant pattern's root cause

## Decision tree

```
Log volume spike or need to understand error composition?
├── Collect logs from Loki (50-500 lines)
├── Run log_analyzer.py
├── Check interpretation.severity:
│   ├── HIGH (>20% errors) → Dominant error pattern is the investigation target
│   ├── MEDIUM (5-20%) → Multiple issues, prioritize by count
│   └── LOW (<5%) → Volume spike is non-error traffic (scaling event?)
├── Check time_analysis.spike_detected:
│   ├── Yes → Correlate max_at timestamp with deploys, config changes
│   └── No → Gradual increase, not event-triggered
└── Check pattern_diversity:
    ├── LOW → One pattern dominates (single root cause)
    ├── HIGH → Many unique messages (possible log format issue or many independent errors)
    └── Compare top pattern % — if >50%, that's your target
```

## Related skills

- `loki-logql-patterns` — building LogQL queries to collect the logs
- `metric-correlation-analysis` — correlate log spike timing with metric anomalies
- `incident-triage` — severity classification after identifying the pattern
- `root-cause-analysis` — formal RCA with the identified pattern as starting evidence
