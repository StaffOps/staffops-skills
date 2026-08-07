---
name: aws-devops-agent-skills
description: Use when authoring, importing, validating, or troubleshooting skills for the AWS DevOps Agent (aidevops) — writing SKILL.md, choosing agent_types, importing via zip or sourceUrl, debugging ValidationException on import, or auditing an existing skill catalog. Covers the asset model, the official SKILL.md procedure structure, the verified agent_types enum, the GitHub-only sourceUrl constraint, and the verification discipline that prevents silent false-negative skills.
---

# AWS DevOps Agent — Skill Authoring & Import

The AWS DevOps Agent (API signing name `aidevops`) loads **skills** contextually during investigations. A skill is a directory of non-executable Markdown that the agent reads when its `description` matches the task at hand.

> Everything in this skill was verified against a live agentspace via the `aws devops-agent` CLI, not inferred from documentation. Where documentation and the API disagreed, the API won — twice. See "Verified API facts".

## When to use this skill

- Writing a new skill or refactoring an existing one
- Choosing `agent_types` scoping
- An import fails with `ValidationException`
- Auditing a skill catalog for correctness
- Deciding whether skill content belongs in `SKILL.md` or `references/`

## When this skill does NOT apply

- Writing skills for Kiro or Claude Code — different format and loading model
- Custom agents (`AGENTS.md` spec) — that is the `custom_agent` asset type, a different shape
- Authoring the observability content itself — see the relevant `apm-metrics/*` or `observability/*` skill

---

## CRITICAL: a wrong metric name is a silent false negative

This is the highest-severity defect class, and it is invisible in review.

A query referencing a metric that does not exist returns an **empty result**. The agent reads "no data" as "no problem" and closes the investigation. During a real incident that is a silent outage — worse than a skill that fails loudly.

### Verify against the live system, never against a secondary source

Documentation lags. A sibling skill can be wrong. Memory of "how this metric is usually named" is not evidence.

```bash
# Prometheus / VictoriaMetrics — the authoritative check
curl -s "$VM_SELECT/api/v1/label/__name__/values?match[]={__name__=~'otelcol_exporter_.*'}"
```
Or the `metrics` tool of a VictoriaMetrics MCP server with a `match` regex. The backend only returns names that actually exist with data.

**Real failure this rule exists to prevent**: an audit pass "corrected" metric names using another skill file as ground truth. It renamed four metrics that were real (`vm_active_merges`, `vm_merges_total`, `vm_pending_rows`, `vm_new_timeseries_created_total`) into names that do not exist, and deleted two valid ones — introducing regressions while claiming to fix them. Only a live query caught it.

### Two traps that produce empty results

| Trap | Symptom | Check |
|------|---------|-------|
| The `_total` suffix is **not** uniform | `..._spans_total` exists, `..._log_records_total` does not | Query the inventory per signal type. When both forms may occur, match `{__name__=~"metric(_total)?"}` |
| `histogram_quantile()` on a **Summary** | Always empty, no error | Confirm a `_bucket` series exists. A Summary is queried as `metric{quantile="0.99"}` |

Where a name genuinely cannot be confirmed, annotate `⚠️ verify with label_values(__name__) before use`. Never assert it.

---

## SKILL.md is a procedure, not a reference document

The most common authoring mistake is writing a catalog. The agent then has to invent the procedure itself, and every investigation produces a differently-shaped answer.

Reference tables belong in `references/`. `SKILL.md` holds the steps.

```
skills/my-skill/
├── SKILL.md              # Required — the procedure
├── references/           # Optional — catalogs, query banks, config examples
└── assets/               # Optional — diagrams, images
```

### The structure

```markdown
---
name: my-skill-name
description: >
  When the agent should load this skill — the specific symptoms, services,
  and error types that trigger it.
---

# Title

## When to use this skill
## When this skill does NOT apply     ← name the correct sibling skill

## Step 1: <concrete action>          ← exact query + threshold + why that threshold
## Step 2: ...
## Step N: Summarize findings
   1. Status — healthy / degraded / critical
   2. Root cause hypothesis — citing the actual observed values, not adjectives
   3. Recommended remediation — ranked; mutations marked ⚠️ REQUIRES APPROVAL
   4. Confidence — count of independent supporting signals

## Decision tree
## Related skills
```

`Summarize findings` is what makes output consistent across investigations. Without it the agent improvises a format each time.

### `description` gates whether the skill loads at all

The agent evaluates **only** the `description` to decide relevance. Well-written instructions behind a vague description are never read.

- Write from the agent's perspective, naming symptoms, services, and error types
- 100–1024 characters (the UI recommends ≥100)
- `name`: lowercase, digits, hyphens; ≤64 chars; no leading or trailing hyphen; must equal the directory name

Good: *"Use when investigating database latency, connection errors, or query timeouts for Amazon RDS instances"*
Useless: *"RDS skill"*

### Order steps by diagnostic value

Application-level signals first (accepted vs sent vs dropped/refused/failed), resources last. Resource metrics **explain** a loss already measured; they never establish health.

A collector pod at CPU 0.6/1.0 and memory 1.6/2Gi, phase `Running`, was dropping 12% of logs. Resources said healthy. Only the application counter revealed it.

### Reference tables use the official column format

```markdown
| Metric | Type | Normal Range | Investigation Threshold | Notes |
|---|---|---|---|---|
| `metric_name_total` | Counter | 0 | > 0 sustained 5m = data loss | why it matters |
```

Every threshold justified. When genuinely workload-dependent, write `baseline-relative — compare to 7d p95` rather than inventing a number.

---

## Verified API facts

### Asset types (`aws devops-agent list-asset-types`)

`skill`, `artifact`, `attachment`, `agents_md`, `feedback`, `custom_agent`, `memory_store`, `memory`, `test_profile`.

### `agent_types` enum — the UI labels are NOT the API values

Two values commonly assumed from the Web App labels are rejected by the API.

| API value | Web App label | Purpose |
|-----------|---------------|---------|
| `GENERIC` | Generic | All agent types (default) |
| `CHAT` | **On-demand** | Conversational queries |
| `INCIDENT_TRIAGE` | Incident Triage | Initial assessment; can mark an incident *Skipped* |
| `INCIDENT_RCA` | Incident RCA | Root cause analysis |
| `INCIDENT_MITIGATION` | Incident Mitigation | Active remediation |
| `PREVENTION` | **Evaluation** | Proactive recommendations |

Also valid: `CHANGE_REVIEW`, `CHANGE_RELEASE`, `QUALITY_ASSURANCE_TESTING`, `RELEASE_SHEPHERD`, `RELEASE_READINESS_REVIEW`, `RELEASE_TESTING`, `SYSTEM_LEARNING`, `INCIDENT_UI`, `GRADER`.

`ON_DEMAND` and `EVALUATION` do **not** exist.

**Scope, do not leave everything `GENERIC`.** The agent evaluates every skill's description on every task; an unscoped catalog of 47 skills means 47 descriptions parsed each time.

### Technique: extract an undocumented enum from the API

Submit a deliberately invalid value and read the constraint error. Faster and more reliable than searching documentation:

```bash
aws devops-agent update-asset --agent-space-id "$AS" --asset-id "$ID" \
  --metadata '{"agent_types":["BOGUS"]}'
# ValidationException: ... Member must satisfy enum value set: [GENERIC, CHAT, ...]
```

---

## Import mechanics

`--content` is a **tagged union**: exactly one of `file`, `zip`, `sourceUrl`.

### `sourceUrl` is GitHub-only

Two independent constraints, both enforced server-side:

1. **The parser requires exactly `owner/repo` before `/tree/`.** A nested path (GitLab groups/subgroups, e.g. `org/dept/team/project`) cannot parse → `Invalid GitHub URL format. Expected a browser URL like https://<host>/owner/repo/tree/branch/path`.
2. **The host needs a GitHub association.** Even a well-formed two-segment URL on a non-GitHub host fails → `No GitHub access is configured for the repository's host.`

GitLab's `/-/tree/` separator also breaks the parse. There is no workaround; use `zip`.

### `zip` works from any host

```bash
cd skills/<skill-name>
zip -qr /tmp/skill.zip . -x '.gitkeep'        # SKILL.md must be at the ZIP ROOT

# The blob sits inside a JSON document, so it must be base64 INLINE.
# fileb:// is rejected for document-typed parameters.
printf '{"zip":{"zipFile":"%s"}}' "$(base64 -w0 /tmp/skill.zip)" > /tmp/content.json

aws devops-agent create-asset \
  --agent-space-id "$AGENTSPACE_ID" --asset-type skill \
  --metadata '{"agent_types":["INCIDENT_RCA"]}' \
  --content file:///tmp/content.json
```

Write the payload to a file rather than passing it as an argument — large skills hit `ARG_MAX`.

**Trade-off**: `zip` forfeits the Operator Web App **Sync** button and the *Last synced* timestamp. Updates require re-pushing content via `update-asset`.

### Update an existing skill

`create-asset` does not upsert. Look up the `assetId` by name first:

```bash
aws devops-agent list-assets --agent-space-id "$AS" --asset-type skill \
  --query 'items[].[metadata.name,assetId]' --output text
```

Then `update-asset` with the same `--content` shape. Version increments on each call, including metadata-only changes.

### Limits and behavior

| Constraint | Value |
|---|---|
| Size per skill | 6 MB (zip and directory both) |
| Files per skill | 100 |
| Skills per agentspace | 200 |
| Scripts | Rejected unless Sandbox (preview) is enabled |
| `skill_type` | `USER` for authored skills; `LEARNED` for agent-generated |
| `name` / `description` after import | Read-only in the UI — owned by `SKILL.md` |

Useful commands: `list-asset-files`, `get-asset-file`, `get-asset-content` (zip), `list-asset-versions`.

---

## Staged rollout, not bulk

Importing a whole catalog at once means discovering a mechanism error 47 assets late. Each stage answers a different question that the previous one cannot.

| Stage | Scope | Question it answers |
|-------|-------|--------------------|
| 1 | 1 skill | Does the import mechanism work? Is the metadata shape accepted? |
| 2 | ~5 skills | Do the descriptions actually trigger? Does the agent follow the steps? |
| 3 | The rest | — |

Stage 1 is cheap to undo: one `delete-asset`. Stage 2 is the only one that validates **behavior**, and it needs a real question posed to the agent plus observing which skills it loaded.

Agent-seconds are billed, so a runaway investigation costs money and consumes the concurrent-chat quota. Check the agentspace pricing and quota before bulk-importing, and consider an `investigation-cost-guardrail`-style skill that bounds spend per severity.

---

## Skill archetypes worth having

Beyond per-component investigation skills, the [AWS sample gallery](https://aws-samples.github.io/sample-devops-agent-tools/) shows archetypes that are easy to overlook:

| Archetype | Agent type | Purpose |
|-----------|------------|---------|
| Symptom router | `GENERIC` | Entry point — maps a human-language symptom to the skill to load and the first query to run |
| Cost guardrail | `GENERIC` | Bounds investigation spend per severity; defines stop conditions |
| Skip criteria | `INCIDENT_TRIAGE` | Skip-vs-investigate decision with a mandatory reason. Never skip P1, data loss, security, or production user impact |
| Operational review | `PREVENTION` | Proactive report with pass/fail per dimension — a clean review must be distinguishable from an incomplete one |
| Tool amplifier | `GENERIC` / `CHAT` | For each symptom: which MCP tool, which parameters, how to read the result |

Skills compose — the agent loads whichever are relevant. Cross-reference siblings instead of duplicating content.

---

## Anti-patterns

- ❌ `SKILL.md` as a metric catalog with no procedure
- ❌ A metric name not verified against the live backend
- ❌ Blanket `_total` suffixing across signal types
- ❌ `histogram_quantile()` without confirming a `_bucket` series exists
- ❌ Vague `description` — the skill never loads
- ❌ `name` differing from the directory name
- ❌ Everything `GENERIC` — wastes context on every task
- ❌ Trusting UI labels as API enum values
- ❌ `fileb://` for the zip blob (document-typed parameter needs base64 inline)
- ❌ Bulk-importing before validating the mechanism with one skill
- ❌ A threshold stated as a bare number with no reasoning
- ❌ A mutating recommendation without blast radius, rollback, and an approval gate

## Reference

- [DevOps Agent Skills](https://docs.aws.amazon.com/devopsagent/latest/userguide/about-aws-devops-agent-devops-agent-skills.html)
- [Managing Assets](https://docs.aws.amazon.com/devopsagent/latest/userguide/about-aws-devops-agent-managing-assets.html)
- [Agent Skills specification](https://agentskills.io)
- [Sample skills gallery](https://aws-samples.github.io/sample-devops-agent-tools/)
- [Agent Skill Eval harness](https://github.com/aws-samples/sample-agent-skill-eval)
