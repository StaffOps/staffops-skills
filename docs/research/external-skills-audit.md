# External skills audit and build tracker

Research conducted 2026-07-31: 12 external "Claude Agent Skills" repos were cloned to a
scratch directory and analyzed (survey-level for the "unsure" list, full deep-dive for the
"definitely" list) to decide what is worth adapting into this catalog. No code was copied
from any source repo — everything below is analysis to guide an independent rewrite, with
source attribution kept for each item.

## Resume point (last updated 2026-08-01, mid-session, tiers 1 and 2 shipped)

**Tiers 1 and 2 are both fully done, validated, fixed, and committed** — commit `e197542`
(tier 1: systematic-debugging, session-handoff, skill-eval-harness, git-guardrails) and
commit `3b61f17` (tier 2: interactive-debugging, frontend-design, pdf-operations,
skill-authoring, plus the mcp-server-development enrichment) on `main`, not yet pushed to
`origin/main`. All 9 items caught at least one real, independently-verified issue during
validation (never a rubber stamp) and all were fixed and re-verified before committing —
see the table below for exactly what each fix was. `README.md` and the touched
`DESCRIPTION.md` files were regenerated via `tools/generate_catalog.py` (the catalog's own
canonical generator, discovered mid-session — earlier build agents had been hand-editing
`DESCRIPTION.md` instead, which the `skill-authoring` skill itself now tells future authors
not to do).

Two operational notes worth carrying forward: (1) the `git-guardrails` rework agent hit
this account's monthly API spend limit mid-run once during tier 1 — treat any future "hit
spend limit" notification as a signal to slow down and check in with the user, and prefer
direct Bash verification over spawning another agent when the check is a small, concrete
re-run rather than an open-ended review (this is how several tier-2 fixes were verified,
at zero extra agent cost); (2) before staging any commit in this repo, diff every
`DESCRIPTION.md`/`README.md` change line by line — `tools/generate_catalog.py` reads from
the *working tree*, so it will pick up any pre-existing, unrelated uncommitted changes to
other skills' frontmatter if they happen to be sitting in the tree when it runs. Both
commits in this effort were checked this way before staging and came back clean, but do
not skip that check on a future run.

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
| Generic `LinkedInBackend` adapter interface + SQLite state machine (accounts/leads/runs, runway-balanced assignment, liveness-locked scheduler, temporal-pattern error disambiguation, cross-account retry) — no default vendor, Linked API not included as a dependency | Linked-API/linkedin-skills (`linkedin`, `linkedin-growth`) | `skills/development/linkedin-automation-interface/` (name tentative, adjust at build time) | pending |

#### 11. Organizer family (4 skills, real implementations)

| Item | Source | Target path | Status |
|------|--------|-------------|--------|
| image-enhancer (real upscale/sharpen backend, objective quality metric, no fabricated example output) | ComposioHQ/awesome-claude-skills `image-enhancer` | `skills/documentation/image-enhancer/` or similar (decide category at build time — this is general file tooling, not clearly platform-engineering; note this at build time) | pending |
| invoice-organizer (real extraction incl. OCR fallback, confidence scoring, fixed CSV schema, real watcher script) | ComposioHQ/awesome-claude-skills `invoice-organizer` | `skills/documentation/invoice-organizer/` or similar | pending |
| file-organizer (real undo-log/manifest, default excludes for `.git`/`node_modules`/`.venv`, sha256 not md5, open-file/in-use detection) | ComposioHQ/awesome-claude-skills `file-organizer` | `skills/documentation/file-organizer/` or similar | pending |
| skill-share (real scaffold template, real validator, real zip packaging, vendor-agnostic "announce" step instead of hardcoded Slack/Rube) | ComposioHQ/awesome-claude-skills `skill-share` | `skills/workflows/skill-share/` — should reference `skill-authoring` (item 9) for the structural/validation part rather than duplicate it | pending |

#### 12. AI/LLM-ops + AI-security gap-fill (17 skills, new `ai` category)

Proposing a new top-level category `skills/ai/` for these — 17 skills is enough coherent
volume to justify one rather than scattering them across `development`/`security`, and it
keeps those two categories from being diluted by a distinct sub-domain. Confirm this reads
right once a few are built; not locked in.

| # | Skill | Source path (`DevOps-Security-Agent-Skills/`) | Target | Status |
|---|-------|-----------------------------------------------|--------|--------|
| 12.1 | agent-evals | `devops/ai/agent-evals` | `skills/ai/agent-evals/` | pending |
| 12.2 | agent-observability | `devops/ai/agent-observability` | `skills/ai/agent-observability/` | pending |
| 12.3 | ai-pipeline-orchestration | `devops/ai/ai-pipeline-orchestration` | `skills/ai/ai-pipeline-orchestration/` | pending |
| 12.4 | ai-sre-incident-response | `devops/ai/ai-sre-incident-response` | `skills/ai/ai-sre-incident-response/` | pending |
| 12.5 | llm-caching | `devops/ai/llm-caching` | `skills/ai/llm-caching/` | pending |
| 12.6 | llm-cost-optimization | `devops/ai/llm-cost-optimization` | `skills/ai/llm-cost-optimization/` | pending |
| 12.7 | llmops-platform-engineering | `devops/ai/llmops-platform-engineering` | `skills/ai/llmops-platform-engineering/` | pending |
| 12.8 | model-registry-governance | `devops/ai/model-registry-governance` | `skills/ai/model-registry-governance/` | pending |
| 12.9 | rag-observability-evals | `devops/ai/rag-observability-evals` | `skills/ai/rag-observability-evals/` | pending |
| 12.10 | ai-agent-security | `security/ai/ai-agent-security` | `skills/ai/ai-agent-security/` | validated (1 finding fixed: mischaracterized git-guardrails as having a confirmation tier for "the rest" of destructive ops — it's actually a strict deny-by-default binary gate; corrected in two spots, plus a grammar typo) |
| 12.11 | ai-coding-agent-guardrails | `security/ai/ai-coding-agent-guardrails` | `skills/ai/ai-coding-agent-guardrails/` | pending |
| 12.12 | ai-red-teaming | `security/ai/ai-red-teaming` | `skills/ai/ai-red-teaming/` | validated (0 findings in the file itself; independent reviewer reproduced the harness-integration claim from scratch and confirmed READY TO SHIP; only note was that the builder's own report overstated what was checked into the repo vs. its scratch testing, not a defect in the skill) |
| 12.13 | ai-security-hardening | `security/ai/ai-security-hardening` | `skills/ai/ai-security-hardening/` | pending |
| 12.14 | llm-app-security | `security/ai/llm-app-security` | `skills/ai/llm-app-security/` | pending |
| 12.15 | mcp-server-security | `security/ai/mcp-server-security` | `skills/ai/mcp-server-security/` | validated (2 minor findings fixed on retry: "four attackers" intro contradicted its own 5-row threat model table, awkward anti-pattern sentence fragment; also fixed prompt-injection-defense's now-stale "once that skill lands" reference to this skill) |
| 12.16 | model-supply-chain-security | `security/ai/model-supply-chain-security` | `skills/ai/model-supply-chain-security/` | pending |
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

## PARTE 1 — Em dúvida (survey, decida o que vale olhar de perto)

### 1. BagelHole/DevOps-Security-Agent-Skills — 163 skills

Catálogo gerado/templated (frontmatter idêntico em todas, descrições curtas, sem versão de
Helm chart nem contexto real). Muita sobreposição com o que o staffops-skills já cobre bem
(AWS/Azure/GCP básico, K8s, observability, secrets, scanning). O diferencial real está em
AI/LLM-ops e AI-security — algo que o catálogo atual não tem.

Categorias: compliance/ (18), devops/ (39), infrastructure/ (71), security/ (35).

Top picks (gap real vs. catálogo atual):

| Skill | Por quê |
|---|---|
| `security/ai/mcp-server-security` | Segurança de MCP servers (transport encryption, tool authz, audit log) — nada equivalente hoje |
| `security/ai/ai-agent-security`, `prompt-injection-defense` | Defesa em profundidade para sistemas agênticos |
| `security/ai/ai-red-teaming` | Metodologia de red-team para jailbreak/exfiltração |
| `devops/ai/llmops-platform-engineering`, `model-registry-governance` | CI/CD, promotion, eval gates, governance de modelos |
| `devops/ai/rag-observability-evals`, `agent-evals` | Métricas de qualidade de RAG/agentes |
| `infrastructure/networking/llm-gateway` | LiteLLM Proxy: rate limiting, semantic cache, cost tracking |
| `infrastructure/local-ai/multi-tenant-llm-hosting`, `llm-inference-scaling`, `gpu-kubernetes-operations` | Isolamento multi-tenant e autoscaling de inferência |
| `devops/orchestration/model-serving-kubernetes` | KServe/Triton canary+A/B+GPU |
| `infrastructure/iac/opentofu-migration` | Playbook de migração Terraform→OpenTofu |
| `security/scanning/supply-chain-attack-response` | Framing de IR para supply chain |
| `compliance/frameworks/*` | SOC2, HIPAA, PCI-DSS, ISO27001, GDPR, FedRAMP |
| `devops/developer-experience/devcontainers-nix` | Categoria DX/onboarding ausente |

Veredito: vale minerar só a seção `ai/` (~17 skills) como fonte de gaps reais.

### 2. vercel-labs/agent-skills — 9 skills

Foco React/Next.js/Vercel. `vercel-optimize` e `react-best-practices` usam
`references/`, `scripts/`, `test-cases.json` — estrutura de "gate determinístico →
evidência" parecida com o estilo do catálogo atual.

| Skill | Descrição |
|---|---|
| `deploy-to-vercel` | Deploy com preview por padrão |
| `vercel-cli-with-tokens` | Deploy via CLI com token |
| `vercel-optimize` | Auditoria de custo/performance data-driven |
| `vercel-react-best-practices` | 70 regras de performance React/Next |
| `vercel-composition-patterns` | Padrões de composição React |
| `vercel-react-view-transitions` | View Transition API |
| `vercel-react-native-skills` | Boas práticas RN/Expo |
| `web-design-guidelines` | Revisão de UI contra guidelines de acessibilidade |
| `writing-guidelines` | Revisão de prosa contra handbook de estilo |

Veredito: talvez, só a metodologia de `vercel-optimize` e o manifesto `skills.sh.json`.

### 3. nextlevelbuilder/ui-ux-pro-max-skill — 6 skills

Mega-skill com banco de dados embutido (84 estilos, 192 paletas, 74 pares de fonte, 98
diretrizes de UX). Zero sobreposição com DevOps/SRE. Veredito: não.

### 4. bencium/bencium-marketplace — 15 skills

Skills meta-cognitivas agnósticas de domínio que interessam:

| Skill | Por quê |
|---|---|
| `vanity-engineering-review` | Lente para pegar over-engineering |
| `negentropy-lens` | Framework de decisão para trade-offs de arquitetura |
| `human-architect-mindset` | O que deve ficar humano vs. IA gerar |
| `emotion-statusline` (hook, não skill) | Classificador de "estado emocional" do agente, sinaliza risco de reward-hacking |

Veredito: talvez, só esses 4 itens.

### 5. AccessLint/skills — 3 skills

`audit`, `scan`, `diff` — auditoria WCAG 2.2 via CDP (live DOM). Veredito: não, a menos que
a org tenha UIs internas com requisito de acessibilidade.

### 6. mattpocock/skills — ~38 skills

Repo com filosofia própria (`CONTEXT.md`), instalável como plugin Claude Code ou via
`skills.sh`.

A skill "handoff" — duas versões:
- **`handoff`** (estável): gera documento de handoff no diretório temp do SO, referencia
  specs/ADRs/PRs por path, redige segredos/PII, seção "suggested skills".
  `disable-model-invocation: true`.
- **`claude-handoff`** (experimental): mesma lógica, mas dispara um agente em background
  (`claude --bg --name "..." "<resumo>"`) já seedado com o resumo.

Outras que interessam: `diagnosing-bugs`, `code-review` (dual review), `git-guardrails-claude-code`
(hook PreToolUse bloqueando git ops destrutivos), `wayfinder`/`to-tickets`, `writing-great-skills`.

Veredito: sim para um subconjunto — handoff, git-guardrails, diagnosing-bugs, wayfinder.

## PARTE 2 — Com certeza (deep dive completo)

### 2.1 AlmogBaku/debug-skill

CLI Go (`dap`) + SKILL.md fino. Debugger real via DAP protocol, daemon+socket Unix, não
print-debugging. Suporta Python/Go/Node/Rust/C/C++ (falta .NET).

Mecânica-chave: todo comando bloqueante retorna automaticamente localização + código-fonte
ao redor + variáveis locais + call stack + stdout/stderr bufferizado. Multi-sessão isolada
por socket nomeado. Metodologia: "two strikes, rethink", bisection por wolf-fence,
breakpoint condicional como assertion de runtime.

Preservar: auto-context a cada comando bloqueante; daemon invisível; truncamento explícito.

Corrigir: adicionar backend .NET; debug remoto em Kubernetes nativo (port-forward);
reaper de daemons órfãos no início da sessão; decision trees por linguagem do stack real.

### 2.2 anthropics/skills — pdf

Operações de PDF completas. Parte mais rica: preenchimento de formulário — árvore de
decisão de 3 níveis (estrutura → visual → híbrido), dois gates de validação que falham
alto, round-trip de verificação visual.

Corrigir: decisão clara de quando OCR é necessário; endurecer watermark/encrypt/extração
de imagem; script dispatcher único; documentar fragilidade da heurística de checkbox.

### 2.3 anthropics/skills — frontend-design

Design visual distintivo, persona + processo, zero scripts. Nomeia 3 clichês exatos de
"design gerado por IA" e instrui evitá-los. Duas passadas: brainstorm de token system →
auto-crítica → só então código.

Corrigir: template de token system estruturado; operacionalizar screenshot/auto-crítica;
contraste WCAG AA obrigatório; lint objetivo leve.

### 2.4 anthropics/skills — mcp-builder

4 fases: pesquisa (spec/SDK ao vivo) → implementação (schemas, DRY, tool annotations) →
review/test → avaliação (qualidade medida por sucesso de tarefa do LLM downstream, não
coverage).

Corrigir: teto de quantidade de tools (hoje tende a inchar); plugar em
`external-secrets-aws-sm` e `bdc-telemetry-standard` já existentes; sanitização real em
vez de OWASP genérico; guidance de deploy Dockerfile/Helm.

### 2.5 anthropics/skills — skill-creator

Meta-skill para criar/editar/avaliar/otimizar skills. Grader (objetivo) → comparator
(cego) → analyst (não-cego, só no fim). Heurística: 3 transcrições escrevendo o mesmo
helper → promover para `scripts/`. Otimização de descrição via loop train/test blindado.

Corrigir: generalizar o executor (não fixar em `claude -p`); versionamento real ligado ao
git; `quick_validate` checando referências quebradas; budget cap visível antes de rodar;
checar colisão de trigger com as 100+ skills já existentes.

### 2.6 ComposioHQ/awesome-claude-skills — 6 skills

Maturidade de implementação varia muito: `webapp-testing` tem código real testado;
`video-downloader` tem script real cru; `skill-share`, `image-enhancer`,
`invoice-organizer`, `file-organizer` são prosa pura sem nenhum artefato executável.

**webapp-testing** (o mais forte): scripts como caixa-preta (`--help` antes de ler
source), `with_server.py` sobe múltiplos servidores com cleanup garantido no `finally`,
"reconhecimento antes da ação" (screenshot + DOM dump + `networkidle` obrigatório).
Corrigir: sem framework de assertion; sem mock de rede; sem a11y check; sem regressão
visual.

**video-downloader**: script real via yt-dlp. Corrigir: sem playlist, sem retry, sem
sanitização de filename, sem aviso de ToS.

**Os 4 stubs**: `image-enhancer` tem exemplo de output fabricado. `invoice-organizer` e
`file-organizer` têm o melhor padrão comum (plano → confirmação → execução, copiar por
padrão) mas "log de undo" nunca especificado. Reconstruir = escrever implementação real do
zero para todos os 4.

### 2.7 obra/superpowers — systematic-debugging (item de destaque)

De longe a skill mais rigorosa das 15. Lei de Ferro: "NO FIXES WITHOUT ROOT CAUSE
INVESTIGATION FIRST". 4 fases obrigatórias em ordem (investigação → padrão → hipótese →
implementação). Regra mais afiada: 3+ correções falhadas ⇒ problema de arquitetura, não
mais uma hipótese. Andaimes anti-racionalização: red-flags de auto-fala, tabela de sinais
do parceiro humano, tabela de racionalizações comuns. Pressure-tested contra si mesma com
cenários adversariais documentados.

Arquivos de apoio: `root-cause-tracing.md`, `defense-in-depth.md` (4 camadas),
`condition-based-waiting.md`, `find-polluter.sh`.

Corrigir: ligar a Fase 1 ao stack real de observability (Tempo/Loki/VictoriaMetrics) em
vez de "adicione instrumentação" genérico; time-boxing por fase + branch por severidade de
incidente (SEV1 precisa estancar sangramento antes do processo completo); contador de
tentativas auditável (não autoreportado); exemplos em Go/Python/.NET em vez de TS/JS; saída
de Fase 1 alimentando `post-mortem-templates`/`root-cause-analysis` diretamente.

### 2.8 Linked-API/linkedin-skills — 2 skills

Achado crítico: 100% dependente de um produto pago (Linked API) rodando browser remoto
real logado no LinkedIn. `linkedin-growth` (pipeline de leads) é sofisticado: SQLite
orquestrando importação → qualificação via LLM barato em lotes → atribuição por conta com
menor razão fila/limite → scheduler com lock por liveness de PID → classificação de erro
por padrão temporal → reatribuição entre contas.

Preservar (reusável independente do vendor): separação política (código determinístico)
vs. julgamento (só fit-com-ICP vai pro LLM); distribuição balanceada por runway; lock por
liveness; pacing por último sucesso; ICP como estado durável.

Corrigir: abstrair uma interface `LinkedInBackend` pluggable; adicionar aviso explícito de
risco de ToS/banimento de conta (o original normaliza sem avisar); supressão contra
contatos já feitos por outro canal.

### 2.9 ayghri/i-have-adhd — 1 skill + harness de eval

Multi-harness (não é Cursor-específico). Muda como o agente comunica: 5 fatos causais → 10
regras → 6 exceções → checklist de 5 itens antes de enviar. Ativação só explícita, opt-in
de "sempre ligado" via arquivo-flag.

O harness de eval é a parte mais valiosa: 14 casos cobrindo 12 categorias, rubrica
ponderada de 5 dimensões julgada cega, release gate com cap de orçamento, resumability,
enforcement de pareamento, flags de isolamento documentados.

Corrigir: scoring manual hoje (adicionar subcomando `judge` automatizado); só 2 runners de
exemplo; extrair o harness como utilitário reusável separado de qualquer skill específica;
sem tracking longitudinal de regressão.

## Observações transversais

1. Maturidade de implementação varia muito entre as 6 do ComposioHQ — o ganho de maior
   alavancagem nos 4 stubs é simplesmente shippar código de verdade.
2. "Plano → confirmação → execução" e "script como caixa-preta, `--help` primeiro" são os
   dois primitivos mais reusáveis para virar convenção transversal do catálogo inteiro.
3. `systematic-debugging` é o padrão-ouro — precisa de menos retrabalho estrutural e mais
   aprofundamento de domínio.
4. O harness de eval do i-have-adhd e do skill-creator resolvem o mesmo problema de
   ângulos diferentes — vale unificar num único harness interno.
5. Nenhuma das 15 skills trata segurança/privacidade dos dados que toca — gap sistêmico.

</details>
