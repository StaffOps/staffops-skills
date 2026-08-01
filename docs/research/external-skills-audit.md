# External skills audit and build tracker

Research conducted 2026-07-31: 12 external "Claude Agent Skills" repos were cloned to a
scratch directory and analyzed (survey-level for the "unsure" list, full deep-dive for the
"definitely" list) to decide what is worth adapting into this catalog. No code was copied
from any source repo — everything below is analysis to guide an independent rewrite, with
source attribution kept for each item.

## Resume point (last updated 2026-07-31, mid-session, tier 1 complete)

**Tier 1 is fully done and validated** (all 4 items). The `git-guardrails` rework agent
hit this account's monthly API spend limit mid-run (visible as a `failed` task
notification) but a subsequent run of the same task completed successfully — treat any
future "hit spend limit" notification as a real signal to slow down and check in with the
user, not just retry silently. Given that signal fired once already in this session,
**tier 2 was deliberately not auto-started** — check with the user before dispatching more
build agents, and consider doing lightweight validation directly (Bash, no subagent) where
feasible instead of always spawning a second agent, to conserve spend.

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
| 5 | Interactive debugging (DAP) | AlmogBaku/debug-skill | `skills/development/interactive-debugging/` | pending |
| 6 | MCP server quality/eval methodology | anthropics/skills `mcp-builder` | enrich existing `skills/development/mcp-server-development/` | pending |
| 7 | PDF operations | anthropics/skills `pdf` | `skills/documentation/pdf-operations/` (or new category — decide at build time) | pending |
| 8 | Distinctive frontend/visual design | anthropics/skills `frontend-design` | new category or `skills/development/` — decide at build time | pending |
| 9 | Skill authoring meta-skill | anthropics/skills `skill-creator` | `skills/workflows/skill-authoring/` (references item 3, does not duplicate the eval harness) | pending |

### Tier 3 — needs a scope decision before building

| # | Item | Source | Open question | Status |
|---|------|--------|----------------|--------|
| 10 | LinkedIn automation idea (backend-agnostic) | Linked-API/linkedin-skills (`linkedin`, `linkedin-growth`) | Accept the paid-API dependency, or only build the vendor-agnostic backend interface + state machine? | needs-decision |
| 11 | Organizer family (image/invoice/file) + skill-share | ComposioHQ/awesome-claude-skills | These are prose-only stubs upstream — rebuilding means writing real implementations from scratch, not improving existing code. Worth the effort? | needs-decision |
| 12 | AI/LLM-ops + AI-security gap-fill | BagelHole/DevOps-Security-Agent-Skills `ai/` subtrees (~17 skills) | Which of the 17 are actually relevant to this org's stack? | needs-decision |

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
