# External skills audit and build tracker

Research conducted 2026-07-31: 12 external "Claude Agent Skills" repos were cloned to a
scratch directory and analyzed (survey-level for the "unsure" list, full deep-dive for the
"definitely" list) to decide what is worth adapting into this catalog. No code was copied
from any source repo — everything below is analysis to guide an independent rewrite, with
source attribution kept for each item.

## Resume point (last updated 2026-08-03, mid-session, tiers 1-2 and item 12 shipped)

**Tiers 1 and 2 are both fully done, validated, fixed, and committed** — commit `e197542`
(tier 1: systematic-debugging, session-handoff, skill-eval-harness, git-guardrails) and
commit `3b61f17` (tier 2: interactive-debugging, frontend-design, pdf-operations,
skill-authoring, plus the mcp-server-development enrichment) on `main`. All 9 items caught
at least one real, independently-verified issue during validation (never a rubber stamp)
and all were fixed and re-verified before committing — see the table below for exactly
what each fix was.

**Tier 3, item 12 (all 17 `skills/ai/` skills) is DONE** — landed in four batches, each
committed separately: commit `e888a13`+`ffb5fd2`+`839d68d` (batch 1, security-focused
cluster: ai-agent-security, prompt-injection-defense, mcp-server-security, ai-red-teaming),
commit `2c708c9` (batch 2, LLM-ops-fundamentals cluster: agent-evals, agent-observability,
llm-caching, llm-cost-optimization), commit `de63cfa` (batch 3, CI/CD-and-pipelines
cluster: ai-pipeline-orchestration, llmops-platform-engineering, model-registry-governance,
rag-observability-evals), and commit `6c99f02` (batch 4, the final 5:
ai-sre-incident-response, ai-coding-agent-guardrails, ai-security-hardening,
llm-app-security, model-supply-chain-security). `tools/generate_catalog.py` was run once at
the very end (commit `8207312`, which also added a missing `BLURBS` entry for the new `ai`
category to the generator itself) — catalog is now 191 skills across 17 categories. Every
one of the 17 caught at least one real, independently-verified issue during validation
except 5 that came back clean on the first pass (`agent-observability`, `llm-caching`,
`rag-observability-evals`, `ai-security-hardening`, `model-supply-chain-security`) — see
the table below for exactly what each fix was.

**Tier 3, items 10 and 11 are now also DONE**, closing out the full 22-item plan:
- **Item 11 (organizer family, 4 skills)** — `image-enhancer`, `invoice-organizer`,
  `file-organizer`, `skill-share`, committed as `22e163c`. Two real bugs found and fixed by
  independent validation: `image-enhancer`'s `split_alpha()` crashed on palette-mode images
  (GIFs, indexed PNGs) because Pillow's filters only accept L/RGB/CMYK-class modes, and its
  worked-example Laplacian-variance numbers were found non-reproducible and replaced with
  real re-run numbers plus a corrected, more instructive narrative (salt noise inflates the
  metric rather than lowering it). `skill-share`'s own dangling-reference checker
  false-positived on its own illustrative examples and on a sibling's external-repo
  citation, blocking it from packaging itself — fixed. `invoice-organizer` and
  `file-organizer` validated clean (the latter with a builder-found-and-fixed macOS
  case-insensitive-filesystem collision bug, independently reproduced).
- **Item 10 (linkedin backend-agnostic interface, 1 skill)** — `linkedin-connection-pipeline`
  under `skills/development/`. Ships a vendor-agnostic `LinkedInBackend` abstract interface
  plus a real SQLite state machine (accounts/leads/runs, round-robin assignment, a
  PID-liveness-locked scheduler ported faithfully from the source's Node.js design,
  temporal-pattern streak-vs-isolated disambiguation for an ambiguous "restricted" outcome)
  with a normalized `Outcome`/`ConnectionStatus` enum vocabulary replacing the source's
  hardcoded Linked API JSON error strings — no default production backend ships, only a
  test-only `FakeBackend`. Independent validation reproduced all 9 checks directly (a real
  subprocess kill/reclaim test of the PID lock, a from-scratch two-batch round-robin fixture
  driven through the real CLI, reverting-then-restoring a `sys.modules` module-identity fix
  to prove both the bug and the fix were real, a vendor-neutrality grep across every code
  file) and found one dangling-reference false positive (an external-repo citation read as a
  same-skill path, same class of bug as `skill-eval-harness`'s) plus one documentation
  precision issue (the "resolves itself naturally" framing on the streak/isolated edge case
  undersold a structural property: an account with zero successful sends ever cannot reach
  `'terminate'` for any lead until it lands at least one success) — both fixed.

Catalog is now 196 skills across 17 categories.

**Patterns worth carrying forward from the whole `skills/ai/` effort** (12 items x 4
batches, higher volume than tiers 1-2 combined):

1. **Stale cross-references from concurrent sibling builds were the single most common
   finding class**, by a wide margin. Skills built in the same batch routinely cite each
   other, and whichever one finishes first correctly says "sibling X doesn't exist yet"
   (accurate at the moment it checked) — then the sibling lands moments later and that
   claim goes stale. Not a build defect, a race condition inherent to building
   interdependent skills in parallel. The fix pattern that worked every time: let each
   batch's independent validators run first and flag every stale/missing cross-reference
   precisely, then do ONE consolidated fix pass across the whole batch at the end (cheaper
   than re-dispatching a build agent per file), then re-run `tools/validate_skills.py`
   once, then commit the whole batch together.
2. **Lexical collision-check has a real blind spot**: two skills built concurrently in
   batch 4 (`ai-security-hardening`, `llm-app-security`) had genuine semantic overlap on
   rate-limiting/DoS content that scored near-zero on the tokenizer-based collision-check
   because the two sections used non-overlapping vocabulary ("GPU"/"batch"/"queue-depth"
   vs. "gateway"/"tenant"/"credential") to describe complementary controls. Independent
   validators caught this by actually reading both files, not by trusting the mechanical
   check. When two skills are topically adjacent, read them side by side even if the
   collision-check comes back clean.
3. **Independent validators occasionally over-flag or under-flag process claims** (e.g.
   one validator noted a builder's "I validated 4 cases" report described scratch-file
   testing that didn't fully match what was checked into the repo) — for a skill catalog,
   what matters is whether the checked-in artifact's own claims are reproducible, not
   whether the build session's narrated process is perfectly auditable after the fact.
   Validators were correctly told to focus on the former.
4. Operational notes that held up across the whole effort: the `git-guardrails` rework
   agent hit this account's monthly API spend limit once, and separately one batch of 4
   parallel build agents partially hit a *session* limit (a different, shorter-cycle cap),
   losing 2 of 4 builds with no file written — both are signals to check `git status` and
   what actually landed on disk before re-dispatching anything (never assume a "failed"
   notification means zero side effects, never assume "completed" means nothing was
   lost). Prefer direct Bash verification over spawning another agent when the check is a
   small, concrete re-run rather than an open-ended review — this caught things like a
   builder's claimed-verbatim CLI output that had silently substituted `--` for `—`, and a
   `DESCRIPTION.md`/README generator picking up unrelated pre-existing uncommitted changes
   from the working tree if run at the wrong time (which is exactly why `skills/ai/`'s
   catalog generation was deliberately deferred to the very end of item 12 rather than run
   per-batch).

**If the `/tmp` scratchpad with cloned source repos is gone in a future session** (it will
be — it's session-scoped and already had to be re-cloned twice this session): two source
repos still matter for the rest of tier 3 — `Linked-API/linkedin-skills` (item 10) and
`ComposioHQ/awesome-claude-skills` (item 11, the organizer family). `BagelHole/DevOps-Security-Agent-Skills`
is no longer needed (item 12 is done). Re-clone only those two — the "Full research report"
section below already has everything needed from the rest.

**Tier 3 (items 10-12) still needs a scope decision from the user before building anything**
— see the table below for the open question on each. Do not default into a scope choice
without asking.

Working method: one subagent builds an item, a different subagent (or the orchestrator
directly, via Bash) independently validates it (runs `tools/validate_skills.py` itself,
does not trust the builder's self-report, and for anything security-relevant — like
`git-guardrails` — actively tries to break it rather than just reading the code). Findings
go back to a rework agent until validation is clean. Nothing is committed to git; every
change so far is sitting as uncommitted working-tree diff in this repo.

**Not started:** tier 2 (items 5-9) and tier 3 (items 10-12, each needs a scope decision
from the user before building — do not just pick a default and build, ask first, per the
original plan).

**If resuming in a new session:** the source repos were cloned to a `/tmp`-based scratch
directory that will very likely no longer exist (macOS periodically clears `/private/tmp`,
and scratch dirs are session-scoped). The full analysis in this file's "Full research
report" section below is the durable record — re-cloning is only needed if someone wants to
re-verify a specific claim against the original source rather than trust this summary.
Check `git status` and `git diff` in this repo first to see exactly what's already written
before re-dispatching any build agent, to avoid duplicating work.

## Build tracker

Legend: `pending` (not started) · `in-progress` (build agent dispatched) · `built` (build
agent finished, awaiting validation) · `needs-fixes` (validation found issues, back to
build) · `validated` (a second, independent agent confirmed it meets `CONTRIBUTING.md` and
`tools/validate_skills.py`) · `needs-decision` (scope call required before building) ·
`skipped` (decided against).

### Tier 1 — high value, moderate effort

| # | Item | Source | Target path | Status |
|---|------|--------|-------------|--------|
| 1 | Systematic debugging methodology | obra/superpowers `skills/systematic-debugging` | `skills/troubleshooting/systematic-debugging/` | validated (4 findings fixed: invented "circuit breaker per runbook" claim corrected, tracesToLogsV2 terminology fixed, weak python-otel-patterns citation removed, mitigation table reworded) |
| 2 | Session/incident handoff | mattpocock/skills `productivity/handoff` + `in-progress/claude-handoff` | `skills/workflows/session-handoff/` | validated (5 minor findings fixed: cause-category field added to template, Rollback Plan added to section list, SEV4 added, unused related_skills entry removed, CLI version caveat added) |
| 3 | Skill eval harness (unified) | ayghri/i-have-adhd `evals/` + anthropics/skills `skill-creator` eval loop | `skills/workflows/skill-eval-harness/` | validated (budget gate confirmed to actually block spend before invoking any executor, isolation flags confirmed via a live prompt-injection test; 2 minor findings fixed: unhandled `FileNotFoundError` on bad `--executor-cmd` now caught cleanly, SKILL.md's own worked `plan` example had a per-1k vs per-million pricing unit bug making it fail against its own sample data) |
| 4 | Git safety guardrails | mattpocock/skills `misc/git-guardrails-claude-code` | `skills/workflows/git-guardrails/` | validated (rewritten around a real quote-aware tokenizer instead of substring matching; all 7 original bypasses re-tested directly by the orchestrator, not just the rework agent's self-report, and confirmed closed: quoted flags, `+refspec`, `bash -c`/`sh -c`/`eval`, command substitution now blocked-by-design, separated/case-varied `rm -rf`, cross-repo `-C` handling with fail-closed on unresolvable paths, and a working jq-missing fallback parser with an explicit warning; all legitimate-use sanity checks still pass, e.g. `--force-with-lease`) |

### Tier 2 — high value, more effort

| # | Item | Source | Target path | Status |
|---|------|--------|-------------|--------|
| 5 | Interactive debugging (DAP) | AlmogBaku/debug-skill | `skills/development/interactive-debugging/` | validated (1 finding fixed: a `kubectl debug` example wrongly attributed PID-namespace sharing to `--share-processes`, which only applies to the unrelated `--copy-to` workflow — corrected to attribute it to `--target` and dropped the no-op flag; all other technical claims, incl. exact truncation numbers cross-checked against cached upstream source, held up) |
| 6 | MCP server quality/eval methodology | anthropics/skills `mcp-builder` | enrich existing `skills/development/mcp-server-development/` | validated (0 findings; version bumped 1.0.0 to 1.1.0; new sections integrate cleanly, all new related_skills cross-references verified accurate) |
| 7 | PDF operations | anthropics/skills `pdf` | `skills/documentation/pdf-operations/` | validated (3 findings fixed: dead/unreachable code in `cmd_encrypt` gave a misleading error on an already-encrypted input — refactored `_load_reader` into a password-requiring path and a plain `_open_pdf_reader` probe so `encrypt` can check `.is_encrypted` without tripping the password gate; two dangling `references/*.md` pointers in the script's own docstrings corrected to point at the real SKILL.md sections; `decrypt` on an already-unencrypted input now prints a note instead of silently no-op copying) |
| 8 | Distinctive frontend/visual design | anthropics/skills `frontend-design` | `skills/development/frontend-design/` | validated (1 licensing/attribution finding fixed: two examples were near-verbatim from the Apache-2.0 original despite the skill's own "wording is original" claim — rewritten with genuinely different examples and the claim corrected to describe what's actually new; plus 3 script bugs fixed: `distinct_accent_colors` field renamed to `distinct_hex_colors` to match what it measures, `lint-tokens.py`'s hex regex extended to catch 8-digit alpha hex so a cliche color with an alpha suffix isn't missed, `--help`/missing-file handling separated from lint-warning exit code per this catalog's own `contrast-check.py` convention; contrast-ratio math independently re-verified as correct) |
| 9 | Skill authoring meta-skill | anthropics/skills `skill-creator` | `skills/workflows/skill-authoring/` (references item 3, does not duplicate the eval harness) | validated (3 findings fixed: a fabricated claim folding `ubuntu-administration` into README's "tested in a real Ubuntu container" tier — corrected to name only the skills README actually lists there; overstated what `validate_skills.py` mechanically checks re: "reads as one sentence" — reworded to distinguish the mechanical check from the style expectation; added a pointer to `tools/generate_catalog.py`, the actual canonical way to regenerate `DESCRIPTION.md`/README, which this whole session's build agents had been hand-editing instead of running) |

### Tier 3 — scoped by the user on 2026-08-01, now building

Decisions made (via AskUserQuestion): linkedin-skills builds only the vendor-agnostic
backend interface, no default vendor/paid dependency. The organizer family builds all 4
with real implementations, not prose stubs. AI/LLM-ops gap-fill builds all 17 skills found
in `DevOps-Security-Agent-Skills`' `devops/ai/` and `security/ai/` subtrees. This is
roughly 2.5x the volume of tiers 1+2 combined (22 items vs. 9) — being built in smaller
batches (not all-parallel like tiers 1-2) given tier 1 already hit this account's monthly
API spend limit once at lower volume. Same build-then-independently-validate process as
tiers 1-2 for every item; do not skip validation just because the batch is larger.

#### 10. LinkedIn backend-agnostic interface

| Item | Source | Target path | Status |
|------|--------|-------------|--------|
| Generic `LinkedInBackend` adapter interface + SQLite state machine (accounts/leads/runs, round-robin assignment, liveness-locked scheduler, temporal-pattern error disambiguation, cross-account retry) — no default vendor, Linked API not included as a dependency | Linked-API/linkedin-skills (`linkedin-growth`) | `skills/development/linkedin-connection-pipeline/` | built, validated, fixed — READY TO SHIP. Independent validator reproduced all 9 checks directly (real subprocess kill/reclaim test of the PID-liveness lock, a from-scratch two-batch round-robin fixture driven through the real CLI, reverting-then-restoring the `sys.modules` identity fix to prove both the bug and the fix are real, a vendor-neutrality grep across every code file). One documentation-accuracy fix applied: the "restricted-outcome disambiguation resolves itself naturally" claim was corrected — for an account with zero successful sends ever, the streak check's unbounded lookback means `'terminate'` is structurally unreachable for any of its leads until the account lands at least one success (not unsafe, just needed to be stated precisely rather than implied as transient) |

#### 11. Organizer family (4 skills, real implementations)

| Item | Source | Target path | Status |
|------|--------|-------------|--------|
| image-enhancer (real upscale/sharpen backend, objective quality metric, no fabricated example output) | ComposioHQ/awesome-claude-skills `image-enhancer` | `skills/documentation/image-enhancer/` | built, validated, fixed — palette-mode (`P`/GIF/indexed PNG) crash in `split_alpha()` found by independent validator and fixed (converts to RGB/RGBA before filtering); worked-example Laplacian-variance numbers found non-reproducible from the stated recipe and replaced with real, re-run numbers plus a corrected (and more honest) salt-noise-inflates-the-metric narrative |
| invoice-organizer (real extraction incl. OCR fallback, confidence scoring, fixed CSV schema, real watcher script) | ComposioHQ/awesome-claude-skills `invoice-organizer` | `skills/documentation/invoice-organizer/` | built, validated — READY TO SHIP (dry-run side-effect-free, `organize`/`export-csv` idempotency on repeat runs, comma+embedded-quote CSV round-trip via RFC4180 doubled-quote escaping, and corrupted/malformed PDFs in batch mode all independently reproduced with real fixtures; unreadable files route to a distinct errors bucket, readable-but-low-confidence files route to `_NeedsReview/` — both confirmed correct) |
| file-organizer (real undo-log/manifest, default excludes for `.git`/`node_modules`/`.venv`, sha256 not md5, open-file/in-use detection) | ComposioHQ/awesome-claude-skills `file-organizer` | `skills/documentation/file-organizer/` | built, validated — READY TO SHIP (undo round-trip, all-or-nothing apply gate, sensitive-file gate, and a builder-found-and-fixed macOS case-insensitive-filesystem collision bug all independently reproduced; only 2 cosmetic non-blocking notes) |
| skill-share (real scaffold template, real validator, real zip packaging, vendor-agnostic "announce" step instead of hardcoded Slack/Rube) | ComposioHQ/awesome-claude-skills `skill-share` | `skills/workflows/skill-share/` | built, validated, fixed — dangling-reference checker false-positived on its own illustrative examples and on `skill-eval-harness`'s external-repo citation (blocking `skill-share` from packaging itself); fixed by rewording the illustrative examples out of inline-code spans and disambiguating the external citation's path so it no longer looks like a same-skill pointer; `skill-share` now validates and packages itself cleanly |

#### 12. AI/LLM-ops + AI-security gap-fill (17 skills, new `ai` category)

Proposing a new top-level category `skills/ai/` for these — 17 skills is enough coherent
volume to justify one rather than scattering them across `development`/`security`, and it
keeps those two categories from being diluted by a distinct sub-domain. Confirm this reads
right once a few are built; not locked in.

| # | Skill | Source path (`DevOps-Security-Agent-Skills/`) | Target | Status |
|---|-------|-----------------------------------------------|--------|--------|
| 12.1 | agent-evals | `devops/ai/agent-evals` | `skills/ai/agent-evals/` | validated (1 finding fixed: a fabricated quote in quotation marks attributed to `skill-authoring` that doesn't appear there, replaced with an accurate real quote; plus a cosmetic double-hyphen-vs-em-dash mismatch in a claimed-verbatim CLI output, re-verified against the real command) |
| 12.2 | agent-observability | `devops/ai/agent-observability` | `skills/ai/agent-observability/` | validated (0 findings in content -- cross-referenced ~9 existing skills, every specific quote/metric-name verified accurate; 1 stale cross-reference to llm-cost-optimization fixed in a follow-up pass once that sibling landed) |
| 12.3 | ai-pipeline-orchestration | `devops/ai/ai-pipeline-orchestration` | `skills/ai/ai-pipeline-orchestration/` | validated (0 findings in content -- grounded in real Argo Workflows infra, every metric name/chart version/YAML convention cross-checked exact; 1 stale "no llmops-platform-engineering exists" claim fixed once that sibling landed) |
| 12.4 | ai-sre-incident-response | `devops/ai/ai-sre-incident-response` | `skills/ai/ai-sre-incident-response/` | validated (1 finding fixed: a severity-table summary cell for cost-spike incidents contradicted its own detailed criteria and anti-patterns -- said escalation "requires customer impact" when the detailed cell correctly said financial materiality alone is enough; corrected the summary label. Real SEV1-4 scale and post-mortem cause taxonomy both reused verbatim from the actual source skills, independently confirmed accurate) |
| 12.5 | llm-caching | `devops/ai/llm-caching` | `skills/ai/llm-caching/` | validated (0 findings in content -- READY TO SHIP on first pass; 1 stale cross-reference to llm-cost-optimization fixed in a follow-up pass once that sibling landed) |
| 12.6 | llm-cost-optimization | `devops/ai/llm-cost-optimization` | `skills/ai/llm-cost-optimization/` | validated (0 findings in content; 5 stale "sibling skill doesn't exist yet" claims fixed in a follow-up pass once agent-evals/llm-caching/agent-observability all landed, since this one was built before them) |
| 12.7 | llmops-platform-engineering | `devops/ai/llmops-platform-engineering` | `skills/ai/llmops-platform-engineering/` | validated (1 finding fixed: eval-gate CI example's prose said "its own stage between test and deploy" but the YAML used `stage: test` -- reworded prose to match reality as a job within the test stage; every technical claim incl. the eval-harness's real exit-code logic verified accurate; added bilateral cross-reference with model-registry-governance once it landed) |
| 12.8 | model-registry-governance | `devops/ai/model-registry-governance` | `skills/ai/model-registry-governance/` | validated (0 findings in content -- the honest 3-way SBOM-parallel split held up exactly, every gate/citation cross-checked; added a clause on cosign sign-blob's operational difference from image signing, removed a self-contradictory "mlops" tag, added bilateral cross-reference with llmops-platform-engineering once it landed) |
| 12.9 | rag-observability-evals | `devops/ai/rag-observability-evals` | `skills/ai/rag-observability-evals/` | validated (0 findings -- READY TO SHIP on first pass; builder self-corrected a stale cross-reference to ai-pipeline-orchestration mid-build and caught its own copy-paste error in the worked example by actually running the real command, both independently reproduced by the validator) |
| 12.10 | ai-agent-security | `security/ai/ai-agent-security` | `skills/ai/ai-agent-security/` | validated (1 finding fixed: mischaracterized git-guardrails as having a confirmation tier for "the rest" of destructive ops — it's actually a strict deny-by-default binary gate; corrected in two spots, plus a grammar typo) |
| 12.11 | ai-coding-agent-guardrails | `security/ai/ai-coding-agent-guardrails` | `skills/ai/ai-coding-agent-guardrails/` | validated (2 minor findings fixed: two sibling quotes presented in quotation marks were paraphrases, not verbatim -- reworded to accurately reflect what was quoted vs. summarized; the deliberate deny-list exception to ai-agent-security's allow-list guidance was independently confirmed to be a real, well-bounded, justified exception rather than a hand-wave) |
| 12.12 | ai-red-teaming | `security/ai/ai-red-teaming` | `skills/ai/ai-red-teaming/` | validated (0 findings in the file itself; independent reviewer reproduced the harness-integration claim from scratch and confirmed READY TO SHIP; only note was that the builder's own report overstated what was checked into the repo vs. its scratch testing, not a defect in the skill) |
| 12.13 | ai-security-hardening | `security/ai/ai-security-hardening` | `skills/ai/ai-security-hardening/` | validated (0 findings -- self-run collision-check against the 3 most overlap-prone siblings independently reproduced with the identical score; added a bilateral cross-reference with llm-app-security once a validator caught a real semantic overlap the lexical collision-check tool structurally cannot detect on rate-limiting/DoS content) |
| 12.14 | llm-app-security | `security/ai/llm-app-security` | `skills/ai/llm-app-security/` | validated (2 findings fixed: cited a nonexistent `cost_usd` field instead of the real `agent_llm_cost_dollars_total` metric from `agent-observability`; added the bilateral `ai-security-hardening` cross-reference and disambiguating clause for the same rate-limiting/DoS overlap noted on that skill's row) |
| 12.15 | mcp-server-security | `security/ai/mcp-server-security` | `skills/ai/mcp-server-security/` | validated (2 minor findings fixed on retry: "four attackers" intro contradicted its own 5-row threat model table, awkward anti-pattern sentence fragment; also fixed prompt-injection-defense's now-stale "once that skill lands" reference to this skill) |
| 12.16 | model-supply-chain-security | `security/ai/model-supply-chain-security` | `skills/ai/model-supply-chain-security/` | validated (0 findings -- self-run collision-check against model-registry-governance reproduced identically at 0.19/note; pickle-deserialization-RCE and safetensors technical claims confirmed accurate against public ML-security knowledge; every cross-reference citation checked word-for-word against source) |
| 12.17 | prompt-injection-defense | `security/ai/prompt-injection-defense` | `skills/ai/prompt-injection-defense/` | validated (2 findings fixed: stale "once ai-agent-security lands" framing when that skill already existed — updated to present tense and added to related_skills; misattributed an agent-platform-design table entry that actually lives in a different section) |

Note: the source repo's originals are uniformly terse (1-3 sentences, no version pinning,
no org-specific grounding) per the original survey — treat them as topic scaffolding to
ground with real specifics (actual OTel/eval-harness/K8s conventions this catalog already
has), not as content to lightly reword. Cross-reference existing skills aggressively:
`mcp-server-security` should build on `mcp-server-development`'s existing security section
rather than duplicate it; `ai-agent-security`/`prompt-injection-defense` should reference
`agent-platform-design`; `agent-evals`/`rag-observability-evals` should reference
`skill-eval-harness`'s harness mechanics rather than inventing a second one.

### Also flagged (from the "unsure" survey, lower priority, not yet scheduled)

| Item | Source | Note |
|------|--------|------|
| `vanity-engineering-review`, `negentropy-lens`, `human-architect-mindset` | bencium/bencium-marketplace | Domain-agnostic meta/process skills, could fit `workflows/` |
| `vercel-optimize` methodology (metric → gate → evidence) | vercel-labs/agent-skills | Pattern worth studying, not the React content itself |
| `wayfinder`, `to-tickets`, `diagnosing-bugs`, `writing-great-skills` | mattpocock/skills | Complements `spec-writing`/`adr-template`/`post-mortem-templates` |

## How this tracker is used

Each item is built by one subagent and independently validated by a second subagent
(never the same one that wrote it) against `CONTRIBUTING.md` conventions and
`tools/validate_skills.py`. Status is updated here as work lands, in the same commit/PR
that adds or changes the skill, so the table stays truthful without depending on any
particular chat session's task list.

---

# Full research report

<details>
<summary>Expand for the complete per-repo survey and per-skill deep-dive</summary>

## PART 1 — Uncertain (survey, decide what is worth a closer look)

### 1. BagelHole/DevOps-Security-Agent-Skills — 163 skills

Generated/templated catalog (identical frontmatter across all, short descriptions, no Helm
chart version or real context). Heavy overlap with what staffops-skills already covers well
(basic AWS/Azure/GCP, K8s, observability, secrets, scanning). The real differentiator is in
AI/LLM-ops and AI-security — something the current catalog lacks entirely.

Categories: compliance/ (18), devops/ (39), infrastructure/ (71), security/ (35).

Top picks (real gaps vs. current catalog):

| Skill | Why |
|---|---|
| `security/ai/mcp-server-security` | MCP server security (transport encryption, tool authz, audit log) — no equivalent today |
| `security/ai/ai-agent-security`, `prompt-injection-defense` | Defense-in-depth for agentic systems |
| `security/ai/ai-red-teaming` | Red-team methodology for jailbreak/exfiltration |
| `devops/ai/llmops-platform-engineering`, `model-registry-governance` | CI/CD, promotion, eval gates, model governance |
| `devops/ai/rag-observability-evals`, `agent-evals` | RAG/agent quality metrics |
| `infrastructure/networking/llm-gateway` | LiteLLM Proxy: rate limiting, semantic cache, cost tracking |
| `infrastructure/local-ai/multi-tenant-llm-hosting`, `llm-inference-scaling`, `gpu-kubernetes-operations` | Multi-tenant isolation and inference autoscaling |
| `devops/orchestration/model-serving-kubernetes` | KServe/Triton canary+A/B+GPU |
| `infrastructure/iac/opentofu-migration` | Terraform→OpenTofu migration playbook |
| `security/scanning/supply-chain-attack-response` | IR framing for supply chain |
| `compliance/frameworks/*` | SOC2, HIPAA, PCI-DSS, ISO27001, GDPR, FedRAMP |
| `devops/developer-experience/devcontainers-nix` | Missing DX/onboarding category |

Verdict: worth mining only the `ai/` section (~17 skills) as a source of real gaps.

### 2. vercel-labs/agent-skills — 9 skills

Focus on React/Next.js/Vercel. `vercel-optimize` and `react-best-practices` use
`references/`, `scripts/`, `test-cases.json` — a "deterministic gate →
evidence" structure similar to the current catalog's style.

| Skill | Description |
|---|---|
| `deploy-to-vercel` | Deploy with preview by default |
| `vercel-cli-with-tokens` | Deploy via CLI with token |
| `vercel-optimize` | Data-driven cost/performance audit |
| `vercel-react-best-practices` | 70 React/Next performance rules |
| `vercel-composition-patterns` | React composition patterns |
| `vercel-react-view-transitions` | View Transition API |
| `vercel-react-native-skills` | RN/Expo best practices |
| `web-design-guidelines` | UI review against accessibility guidelines |
| `writing-guidelines` | Prose review against style handbook |

Verdict: maybe, only the `vercel-optimize` methodology and the `skills.sh.json` manifest.

### 3. nextlevelbuilder/ui-ux-pro-max-skill — 6 skills

Mega-skill with embedded database (84 styles, 192 palettes, 74 font pairs, 98
UX guidelines). Zero overlap with DevOps/SRE. Verdict: no.

### 4. bencium/bencium-marketplace — 15 skills

Domain-agnostic meta-cognitive skills of interest:

| Skill | Why |
|---|---|
| `vanity-engineering-review` | Lens for catching over-engineering |
| `negentropy-lens` | Decision framework for architecture trade-offs |
| `human-architect-mindset` | What should stay human vs. AI-generated |
| `emotion-statusline` (hook, not skill) | Agent "emotional state" classifier, signals risk of reward-hacking |

Verdict: maybe, only these 4 items.

### 5. AccessLint/skills — 3 skills

`audit`, `scan`, `diff` — WCAG 2.2 audit via CDP (live DOM). Verdict: no, unless the
org has internal UIs with accessibility requirements.

### 6. mattpocock/skills — ~38 skills

Repo with its own philosophy (`CONTEXT.md`), installable as a Claude Code plugin or via
`skills.sh`.

The "handoff" skill — two versions:
- **`handoff`** (stable): generates a handoff document in the OS temp directory, references
  specs/ADRs/PRs by path, redacts secrets/PII, "suggested skills" section.
  `disable-model-invocation: true`.
- **`claude-handoff`** (experimental): same logic, but fires a background agent
  (`claude --bg --name "..." "<summary>"`) already seeded with the summary.

Others of interest: `diagnosing-bugs`, `code-review` (dual review), `git-guardrails-claude-code`
(PreToolUse hook blocking destructive git ops), `wayfinder`/`to-tickets`, `writing-great-skills`.

Verdict: yes for a subset — handoff, git-guardrails, diagnosing-bugs, wayfinder.

## PART 2 — Definitely (full deep dive)

### 2.1 AlmogBaku/debug-skill

Go CLI (`dap`) + thin SKILL.md. Real debugger via DAP protocol, daemon+Unix socket, not
print-debugging. Supports Python/Go/Node/Rust/C/C++ (missing .NET).

Key mechanics: every blocking command automatically returns location + surrounding source
code + local variables + call stack + buffered stdout/stderr. Multi-session isolated
by named socket. Methodology: "two strikes, rethink", bisection via wolf-fence,
conditional breakpoint as runtime assertion.

Keep: auto-context on every blocking command; invisible daemon; explicit truncation.

Fix: add .NET backend; native Kubernetes remote debug (port-forward);
orphan daemon reaper at session start; decision trees per real-stack language.

### 2.2 anthropics/skills — pdf

Complete PDF operations. Richest part: form filling — 3-level decision tree
(structure → visual → hybrid), two validation gates that fail loudly, visual
verification round-trip.

Fix: clear decision on when OCR is required; harden watermark/encrypt/image
extraction; single dispatcher script; document checkbox heuristic fragility.

### 2.3 anthropics/skills — frontend-design

Distinctive visual design, persona + process, zero scripts. Names 3 exact clichés of
"AI-generated design" and instructs avoiding them. Two passes: token system brainstorm →
self-critique → only then code.

Fix: structured token system template; operationalize screenshot/self-critique;
mandatory WCAG AA contrast; lightweight objective lint.

### 2.4 anthropics/skills — mcp-builder

4 phases: research (live spec/SDK) → implementation (schemas, DRY, tool annotations) →
review/test → evaluation (quality measured by downstream LLM task success, not
coverage).

Fix: tool count ceiling (currently tends to bloat); plug into existing
`external-secrets-aws-sm` and `bdc-telemetry-standard`; real sanitization instead
of generic OWASP; deploy guidance for Dockerfile/Helm.

### 2.5 anthropics/skills — skill-creator

Meta-skill for creating/editing/evaluating/optimizing skills. Grader (objective) → comparator
(blind) → analyst (non-blind, only at the end). Heuristic: 3 transcripts writing the same
helper → promote to `scripts/`. Description optimization via blind train/test loop.

Fix: generalize the executor (don't hardcode `claude -p`); real versioning tied to
git; `quick_validate` checking broken references; visible budget cap before running;
check trigger collision with 100+ existing skills.

### 2.6 ComposioHQ/awesome-claude-skills — 6 skills

Implementation maturity varies greatly: `webapp-testing` has real tested code;
`video-downloader` has a raw real script; `skill-share`, `image-enhancer`,
`invoice-organizer`, `file-organizer` are pure prose with no executable artifacts.

**webapp-testing** (the strongest): scripts as black-box (`--help` before reading
source), `with_server.py` spins up multiple servers with guaranteed cleanup in `finally`,
"reconnaissance before action" (screenshot + DOM dump + mandatory `networkidle`).
Fix: no assertion framework; no network mocking; no a11y check; no visual regression.

**video-downloader**: real script via yt-dlp. Fix: no playlist, no retry, no
filename sanitization, no ToS warning.

**The 4 stubs**: `image-enhancer` has fabricated output example. `invoice-organizer` and
`file-organizer` have the best common pattern (plan → confirmation → execution, copy by
default) but "undo log" is never specified. Rebuilding = writing a real implementation from
scratch for all 4.

### 2.7 obra/superpowers — systematic-debugging (standout item)

By far the most rigorous skill of the 15. Iron Law: "NO FIXES WITHOUT ROOT CAUSE
INVESTIGATION FIRST". 4 mandatory phases in order (investigation → pattern → hypothesis →
implementation). Sharpest rule: 3+ failed fixes ⇒ architecture problem, not just another
hypothesis. Anti-rationalization scaffolding: self-talk red-flags, human partner signal
table, common rationalization table. Pressure-tested against itself with documented
adversarial scenarios.

Supporting files: `root-cause-tracing.md`, `defense-in-depth.md` (4 layers),
`condition-based-waiting.md`, `find-polluter.sh`.

Fix: connect Phase 1 to the real observability stack (Tempo/Loki/VictoriaMetrics) instead
of generic "add instrumentation"; time-boxing per phase + branching by incident severity
(SEV1 needs to stop the bleeding before the full process); auditable attempt counter
(not self-reported); examples in Go/Python/.NET instead of TS/JS; Phase 1 output feeding
`post-mortem-templates`/`root-cause-analysis` directly.

### 2.8 Linked-API/linkedin-skills — 2 skills

Critical finding: 100% dependent on a paid product (Linked API) running a real remote
browser logged into LinkedIn. `linkedin-growth` (lead pipeline) is sophisticated: SQLite
orchestrating import → qualification via cheap LLM in batches → assignment to account with
lowest queue/limit ratio → scheduler with PID liveness lock → error classification by
temporal pattern → cross-account reassignment.

Keep (reusable independent of the vendor): separation of policy (deterministic code)
vs. judgment (only ICP-fit goes to LLM); balanced distribution by runway; liveness
lock; pacing by last success; ICP as durable state.

Fix: abstract a pluggable `LinkedInBackend` interface; add explicit ToS/account-ban
risk warning (the original normalizes without warning); suppression against contacts
already made through another channel.

### 2.9 ayghri/i-have-adhd — 1 skill + eval harness

Multi-harness (not Cursor-specific). Changes how the agent communicates: 5 causal facts → 10
rules → 6 exceptions → 5-item checklist before sending. Activation only explicit, opt-in
for "always on" via flag file.

The eval harness is the most valuable part: 14 cases covering 12 categories, weighted
5-dimension rubric judged blind, release gate with budget cap, resumability,
pairing enforcement, documented isolation flags.

Fix: scoring is manual today (add automated `judge` subcommand); only 2 example runners;
extract the harness as a reusable utility separate from any specific skill;
no longitudinal regression tracking.

## Cross-cutting observations

1. Implementation maturity varies greatly across the 6 ComposioHQ skills — the highest-leverage
   gain on the 4 stubs is simply shipping real code.
2. "Plan → confirmation → execution" and "script as black-box, `--help` first" are the
   two most reusable primitives to turn into a cross-cutting convention for the entire catalog.
3. `systematic-debugging` is the gold standard — needs less structural rework and more
   domain deepening.
4. The eval harness from i-have-adhd and skill-creator solve the same problem from
   different angles — worth unifying into a single internal harness.
5. None of the 15 skills addresses security/privacy of the data they touch — systemic gap.

</details>
