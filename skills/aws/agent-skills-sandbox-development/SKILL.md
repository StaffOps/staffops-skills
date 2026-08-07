---
name: agent-skills-sandbox-development
description: How to build skills with executable code for the AWS DevOps Agent sandbox — bundling Python/bash scripts, filesystem layout, pre-installed packages, and testing patterns.
---

# Building Executable Skills for the Sandbox

With Sandbox enabled, skills can include **executable code** that the agent runs during investigations. This transforms skills from "instructions the agent reasons about" to "tools the agent executes."

## When to use this skill

- Designing a new skill that should include runnable code
- Understanding what the sandbox can and cannot do
- Choosing between MCP tools vs bundled scripts
- Testing executable skills before import

## How the sandbox works

| Property | Value |
|----------|-------|
| Runtime | Lambda MicroVM (ephemeral, per-investigation) |
| Lifetime | Single investigation only — destroyed after |
| Filesystem | Skills mounted at `/aidevops/skills/user/<name>/` |
| AWS access | Pre-configured profiles, **READ-ONLY** (proxy blocks writes) |
| Python | Available with pre-installed pip packages |
| Node.js | Available with pre-installed npm packages |
| Shell | bash, grep, find, awk, sed, curl (standard Linux) |
| Networking | AWS endpoints always; other hosts only if allowlisted |

### Pre-installed pip packages (configured 2026-08-06)

`pandas`, `pyyaml`, `requests`, `jinja2`, `numpy`

The agent imports these directly — no `pip install` at runtime needed.

### What the agent can do in the sandbox

- Read skills with `cat`, `grep`, `find` (faster than virtual filesystem)
- Run Python scripts bundled with a skill
- Run bash scripts for data processing
- Use `aws` CLI and `boto3` (read-only, auto-configured for connected accounts)
- Write temporary files for intermediate results
- Parse large data (logs, metric dumps) with pandas

### What it CANNOT do

- Write to AWS resources (proxy blocks mutations)
- Access hosts not in the networking allowlist
- Install packages at runtime (must be pre-installed)
- Persist data between investigations (ephemeral)
- Run in chat or custom agents (preview: investigations only)

## VERIFIED PATTERN (homologated 2026-08-06)

The following was confirmed working in production (investigation `3ec36853`, 56 journal records):

### What the API accepts

- ✅ `.md` files with code in fenced blocks (`references/script-name.md`)
- ✅ `references/` directory
- ❌ `.py`, `.sh`, `.js` files (ValidationException: "Script files are not allowed")
- ❌ `scripts/` directory (ValidationException: "Files under a scripts/ directory are not allowed")

### How the agent uses bundled code

```
1. Loads SKILL.md → reads the procedure
2. Collects data via MCP tools (VictoriaMetrics, Grafana, etc.)
3. Writes collected data to /tmp/<file>.json
4. Reads references/<script>.md → extracts code with:
   sed -n '/^```python$/,/^```$/p' /aidevops/skills/user/<skill>/references/<script>.md | sed '1d;$d' > /tmp/script.py
5. Runs: python3 /tmp/script.py --data-file /tmp/<file>.json
6. Parses structured JSON output → reasons over it → produces conclusion
```

### The agent adapts parameters

In the homologation test, the agent ran the script MULTIPLE TIMES with different parameters (`--threshold 1.5` then `2.0`, `--window 300` then `600`) to refine the analysis. Design scripts to accept CLI args so the agent can iterate.

### Cost

~7 minutes investigation execution ≈ $3.50. The sandbox adds minimal overhead — most time is spent on MCP queries and reasoning, not script execution.

## Skill layout (verified working)

```
skills/my-executable-skill/
├── SKILL.md                        # Procedure — tells agent to extract and run code
├── references/
│   ├── analysis-script.md          # Python inside ```python fenced block
│   ├── helper-script.md            # Additional scripts (one per .md file)
│   └── thresholds.yaml             # Config data the scripts can read
└── evals/
    └── eval_queries.json            # Trigger routing tests
```

⚠️ **NO `scripts/` directory. NO `.py`/`.sh` files.** The API rejects them with ValidationException.

The agent accesses code at:
```
/aidevops/skills/user/my-executable-skill/references/analysis-script.md
```

## Writing the SKILL.md to invoke bundled code

The SKILL.md instructs the agent to run the code. Example:

```markdown
## Step 3: Analyze metric correlation

Run the bundled correlation script:

\```bash
python3 /aidevops/skills/user/my-skill/scripts/correlate.py \
  --metric "http_server_request_duration_seconds_count" \
  --namespace "dpm" \
  --window "30m"
\```

The script reads from VictoriaMetrics via boto3 (auto-configured) and outputs
a JSON report with correlated signals.
```

### Key patterns

1. **Always use absolute paths** — the skill is at `/aidevops/skills/user/<name>/`
2. **Accept parameters via CLI args** — the agent constructs the command
3. **Output structured results** (JSON/YAML) — the agent can parse and reason over them
4. **Handle errors gracefully** — print clear error messages, non-zero exit code
5. **Stay read-only** — boto3 calls through the proxy cannot write; design for reads

## Script design principles

### Input: from args or stdin

```python
#!/usr/bin/env python3
"""Correlate metric spikes with recent deploys."""
import argparse
import json
import subprocess

def query_vm(expr: str, time_range: str = "30m") -> dict:
    """Query VictoriaMetrics via the MCP tool (agent runs this in sandbox)."""
    # The agent will call this script; it already has VM data from MCP
    # This pattern is for offline analysis of data the agent has collected
    pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-file", required=True, help="Path to JSON data from agent")
    parser.add_argument("--threshold", type=float, default=0.05)
    args = parser.parse_args()

    with open(args.data_file) as f:
        data = json.load(f)

    # ... analysis logic ...
    results = {"correlations": [...], "confidence": 0.85}
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
```

### Output: structured for the agent to parse

```json
{
  "status": "degraded",
  "findings": [
    {"signal": "error_rate", "value": 0.12, "threshold": 0.05, "breached": true},
    {"signal": "latency_p99", "value": 2.3, "threshold": 2.0, "breached": true}
  ],
  "correlation": {
    "deploy_sha": "abc123",
    "deployed_at": "2026-08-06T14:02:00Z",
    "degradation_started": "2026-08-06T14:05:00Z",
    "temporal_match": true
  },
  "confidence": 3,
  "recommendation": "Rollback to previous version (⚠️ RECOMMENDATION ONLY)"
}
```

## When to use bundled code vs MCP tools

| Use case | Bundled script | MCP tool |
|----------|---------------|----------|
| Single metric query | ❌ Overkill | ✅ Direct |
| Correlate 10+ metrics | ✅ pandas analysis | ❌ Too many calls |
| Parse large log dump | ✅ grep/awk/python | ❌ MCP returns limited |
| Statistical analysis (percentiles, trends) | ✅ numpy/pandas | ❌ Not available |
| Template generation (runbook, report) | ✅ jinja2 | ❌ Not available |
| Cross-signal join (metric × trace × log) | ✅ Script joins data | ❌ Each is separate MCP |

**Rule of thumb**: if the task is "query one thing and reason about it" → MCP tool. If the task is "compute over multiple data points" → bundled script.

## Testing locally before import

```bash
# Test the script works in isolation (same Python version as sandbox)
docker run --rm -v "$(pwd)/skills/my-skill:/skill" -w /skill \
  python:3.11-slim sh -c "pip install -q pandas pyyaml numpy && python3 scripts/analyze.py --help"

# Test with sample data
echo '{"metrics": [...]}' > /tmp/test-data.json
docker run --rm -v "$(pwd)/skills/my-skill:/skill" -v /tmp/test-data.json:/data.json \
  python:3.11-slim sh -c "pip install -q pandas numpy && python3 /skill/scripts/analyze.py --data-file /data.json"
```

## Importing executable skills

Same as any skill — the `scripts/` directory is included in the zip:

```bash
./import-skills.sh --agentspace-id $AS --update --skill my-executable-skill
```

The import respects the 6MB / 100 files limit. Python scripts are small; this is rarely a constraint.

## FUTURE: Networking allowlist for active health checks

When we have confirmed internal endpoints (product APIs, health check URLs):
- Add to the sandbox networking allowlist (Console → Capabilities → Sandbox → Allowlist)
- Skills can then use `requests.get("http://internal-service/healthz")` to **validate** that a service is responding
- This turns investigations from "the metric says X" to "I checked and the service responds/doesn't respond"
- Scope narrowly: specific hosts, GET only, specific paths

## LEARNED (2026-08-06): Secrets Manager is BLOCKED by session policy

The sandbox proxy uses a **session policy** that restricts which AWS actions the sandbox can call. `secretsmanager:GetSecretValue` is NOT in the allowed set — this is an AWS architectural decision, not configurable.

**Even if the IAM role has the permission**, the session boundary blocks it:
```
"no session policy allows the secretsmanager:GetSecretValue action"
```

**Consequence**: scripts that need production secrets (API tokens, passwords) CANNOT work in the sandbox. Alternatives:
1. Query metrics that already contain the validation result (e.g., Kuma `monitor_status`) — **preferred**
2. Build a Custom MCP Server (IRSA pod) that has SM access and exposes a validation tool
3. Pass the token in the investigation description (manual, not automated)

**The Kuma approach** (query `monitor_status{job="kuma-nv"}` via VictoriaMetrics MCP) is the correct solution for "is the API working?" — no sandbox, no secrets, just a PromQL query.

## When NOT to use

- Writing a skill that only returns text (no code execution) — use `agent-skills-new-skill-checklist`
- Debugging a sandbox skill that fails at runtime — use `agent-skills-debugging`
- Importing the finished sandbox bundle into the agentspace — use `agent-skills-import-and-harness`

## Related skills

- `agent-skills-new-skill-checklist` — general skill creation workflow
- `agent-skills-import-and-harness` — import mechanics and API constraints
- `agent-skills-agentspace-operations` — managing the agentspace
