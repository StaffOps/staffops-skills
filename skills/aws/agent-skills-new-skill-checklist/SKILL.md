---
name: agent-skills-new-skill-checklist
description: Step-by-step procedure for adding a new skill to the AWS DevOps Agent catalog — from scaffolding through import and validation.
---

# New Skill Checklist

Procedure for adding a skill to the `aws-devops-agent-skills` catalog. Follow every step in order — skipping verification (step 7) is the #1 cause of silent false-negative skills.

---

## Step 1: Scaffold from template

```bash
cp -r .template/ skills/<new-skill-name>
cd skills/<new-skill-name>
```

Directory name becomes the skill's `name` in frontmatter. Use kebab-case, descriptive (`eks-node-pressure`, not `node-fix`).

---

## Step 2: Write SKILL.md

Structure:

```markdown
---
name: <dir-name>
description: <100–1024 chars, from the agent's perspective — "Use when..." not "This skill...">
---

# <Title>

## When to use
- <symptom or trigger that activates this skill>

## When NOT to use
- <conditions where a different skill applies>

## Steps

### 1. <Action verb> — <what to check>
Query: `<exact PromQL/LogQL/TraceQL/AWS CLI>`
Look for: <threshold or pattern>

### 2. ...

## Summarize findings

| Field | Content |
|-------|---------|
| **Status** | HEALTHY / DEGRADED / CRITICAL |
| **Root cause** | <1-sentence diagnosis> |
| **Remediation** | <concrete action — annotated ⚠️ RECOMMENDATION ONLY if mutating> |
| **Confidence** | HIGH / MEDIUM / LOW + reasoning |

## Decision tree

- IF <condition> → <next step or conclusion>
- ELIF <condition> → ...
- ELSE → escalate / try <related-skill>

## Related skills
- `<skill-name>` — <when to pivot there>
```

### Frontmatter rules
- `name` MUST equal the directory name exactly.
- `description` MUST be 100–1024 characters. Write from the agent's POV ("Use when diagnosing...").

---

## Step 3: Add references/ (optional)

For lookup tables, metric catalogs, or threshold matrices that support the procedure but are NOT procedure themselves:

```bash
mkdir -p skills/<new-skill-name>/references/
# Example: metric-catalog.md, threshold-matrix.md, error-codes.tsv
```

Do NOT put procedural steps in references — only data the steps refer to.

---

## Step 4: Add eval_queries.json

```bash
mkdir -p evals/<new-skill-name>/
cat > evals/<new-skill-name>/eval_queries.json << 'EOF'
{
  "positive": [
    "Why is my EKS node showing MemoryPressure?",
    "Node is NotReady with memory pressure taint"
  ],
  "negative": [
    "How do I create a new S3 bucket?",
    "What is the cost of my Lambda functions?"
  ]
}
EOF
```

- **positive**: queries that SHOULD trigger this skill (≥3 recommended).
- **negative**: queries that MUST NOT trigger this skill (≥2 recommended).

---

## Step 5: Register in agent-types.tsv

```bash
# Append row — TAB-separated
echo -e "<new-skill-name>\t<AGENT_TYPE>\t<brief justification>" >> agent-types.tsv
```

Valid `agent_type` values (API-enforced):
- `GENERIC`
- `CHAT`
- `INCIDENT_TRIAGE`
- `INCIDENT_RCA`
- `INCIDENT_MITIGATION`
- `PREVENTION`

❌ `ON_DEMAND` and `EVALUATION` are NOT valid — import will throw `ValidationException`.

---

## Step 6: Add symptoms to routing table

Edit `symptom-router.tsv` (or equivalent routing config):

```bash
# Format: symptom_pattern → skill_name
echo -e "node memory pressure\t<new-skill-name>" >> symptom-router.tsv
echo -e "MemoryPressure taint\t<new-skill-name>" >> symptom-router.tsv
```

Ensure no overlap with existing routes — check with:
```bash
grep -i "<keyword>" symptom-router.tsv
```

---

## Step 7: Verify metric names against live backend

**This is the highest-severity gate.** A skill that references non-existent metrics is worse than no skill — it produces confident wrong answers.

```bash
# For every metric in your SKILL.md:
grep -c '<metric_name>' skills/<new-skill-name>/SKILL.md

# Then verify each one exists in VictoriaMetrics:
curl -s "https://<vm-read-endpoint>/select/0/prometheus/api/v1/query?query=<metric_name>" \
  | jq '.data.result | length'

# If result is 0 → the metric does NOT exist. Fix or remove it.
```

**Rule: if `grep` against live inventory returns nothing, the skill has a highest-severity defect.** Do not import until every metric is confirmed present.

---

## Step 8: Annotate mutating suggestions

Any remediation step that suggests a **change** (scale, restart, patch, delete, apply) MUST carry:

```markdown
⚠️ **RECOMMENDATION ONLY** — This action modifies resources. Validate in your environment before executing.
```

Place it inline with the suggestion, not hidden in a footer. The agent surfaces this to the user.

---

## Step 9: Import the skill

```bash
./import-skills.sh --agentspace-id "$AGENTSPACE_ID" --skill <new-skill-name>
```

If the script doesn't exist or you need manual import:
```bash
aws aidevops import-skill \
  --agentspace-id "$AGENTSPACE_ID" \
  --skill-name "<new-skill-name>" \
  --source-url "https://github.com/<org>/aws-devops-agent-skills" \
  --path "skills/<new-skill-name>"
```

Watch for `ValidationException` — common causes:
- `description` outside 100–1024 char range
- Invalid `agent_type` value
- `name` mismatch between frontmatter and directory

---

## Step 10: Validate import

```bash
# Confirm skill appears in asset list
aws aidevops list-assets --agentspace-id "$AGENTSPACE_ID" \
  | grep "<new-skill-name>"

# If the skill is safety-adjacent (touches IAM, delete, scaling):
# Run the eval harness
./run-eval.sh --skill <new-skill-name> --queries evals/<new-skill-name>/eval_queries.json
```

**Done when:**
- [ ] `list-assets` shows the skill
- [ ] Positive eval queries trigger the skill
- [ ] Negative eval queries do NOT trigger the skill
- [ ] No metric references return empty from live backend

---

## Quick reference: file tree after completion

```
skills/<new-skill-name>/
├── SKILL.md              # Procedure + frontmatter
└── references/           # (optional) lookup data
evals/<new-skill-name>/
└── eval_queries.json     # Trigger tests
agent-types.tsv           # +1 row
symptom-router.tsv        # +N symptom routes
```
