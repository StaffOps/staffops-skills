---
name: gitops-environments
description: "Use when tracing which GitOps repo controls a service, understanding the organization domain-to-namespace-to-cluster mapping, investigating why a deploy isn't reaching a specific environment, or onboarding a new service into the GitOps pipeline. Covers domain repos (DPM, DCP, APPS, MDT, BM, ACUM, PLG, SUP), ApplicationSet topology, namespace conventions, and deployment flow."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [gitops, environments, argocd, applicationset, deploy]
    category: infrastructure
    related_skills: [helmfile-applicationset, argocd-patterns, helm-chart-app, gitops-environment-onboard]
---

# GitOps Environments

## When to use this skill

- Need to find which repo controls a specific service's deployment
- Investigating why a deploy isn't reaching target environment
- Onboarding a new service into the GitOps pipeline
- Understanding namespace conventions per domain/environment

## When this skill does NOT apply

- ArgoCD sync failure troubleshooting → use `argocd-patterns`
- Helm values structure → use `helm-chart-app`
- Active incident in a deployed service → use `incident-triage`
- Cost of deployed resources → use `cost-explorer`

## CRITICAL: Safety Gate

- ❌ **FORBIDDEN**: `kubectl apply` in PRD — all PRD changes through environment repo → ArgoCD
- Image tags must be **immutable** (SHA-based), never `latest`

## Step 1: Identify the controlling repository

Map from what you know (pod/namespace/cluster) to the repo:

```
1. Identify namespace: kubectl get pod <pod> -o jsonpath='{.metadata.namespace}'
2. Map namespace → domain (table below)
3. Identify environment from cluster (dev-nv=DEV, prd-nv=PRD)
4. Repo path: kubernetes/environments/<domain>/<env>/<domain>-applications-<env>
```

## Step 2: Verify current state in GitOps

```
→ gitops_app_status (check sync status for the application)
→ Check recent commits in the environment repo (image tag updates)
→ Verify image tag exists in Harbor: <harbor-registry>
```

## Step 3: Diagnose deployment gaps

| Symptom | Cause | Resolution |
|---------|-------|------------|
| Service not deployed | Directory missing in env repo | Create service directory with values.yaml |
| Wrong image version | values.yaml has old tag | Update image.tag in env repo |
| Deploy to DEV but not PRD | Only dev repo updated | Update prd repo values.yaml |
| ArgoCD doesn't see the service | ApplicationSet doesn't match path | Check generator directory pattern |

## Step 4: Propose change

**Expected output**: exact file path + change needed + which ArgoCD app will re-sync.

⚠️ RECOMMENDATION ONLY — read-only agent, a human executes: any commit to environment repo (triggers deployment).

## Namespace conventions

| Domain | PRD namespace | BTC namespace | DEV namespace |
|--------|--------------|---------------|---------------|
| DCP | `dcp` | `dcp-btc` | `dcp` (on dev cluster) |
| DPM | `dpm` | `dpm-btc` | `dpm` (on dev cluster) |
| APPS | `apps` | `apps-btc` | `apps` (on dev cluster) |
| PLG | `plg` | — | `plg` (on dev cluster) |
| MDT | `mdt` | — | `mdt` (on dev cluster) |
| BM | `bm` | — | `bm` (on dev cluster) |
| ACUM | `acum` | — | `acum` (on dev cluster) |

## Cluster mapping

| Cluster | Environment | eks_cluster label |
|---------|-------------|-------------------|
| `applications-dev-nv` | DEV | `dev` |
| `applications-prd-nv` | PRD + BTC | `prd` |
| `applications-prd-sp` | PRD (sa-east-1) | `prd` |
| `devops-core` | Platform | `core` |

See `references/domain-repos.md` for the full repository list by domain.

## Related skills

- `argocd-patterns` — sync troubleshooting, ApplicationSet generators
- `helm-chart-app` — values.yaml structure
- `observability-tooling` — cluster endpoints and topology
