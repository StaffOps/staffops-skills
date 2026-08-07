---
name: helmfile-applicationset
description: "Register services in GitOps ApplicationSets."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [helmfile, applicationset, infrastructure]
    category: infrastructure
    related_skills: [helmfile-k8s-addon, helmfile-templating]
---
# Helmfile + ApplicationSet Pattern

## When to Use

Helmfile + bedag/raw chart pattern for ArgoCD ApplicationSets at <org>. Use when onboarding services into GitOps, configuring multi-environment deployments, or understanding the *-applicationsets repo structure. Covers directory generators, values layering, and environment repos.

## When NOT to Use

- Deploying cluster add-ons (monitoring, Istio, Kyverno) → use `helmfile-k8s-addon`
- Debugging ArgoCD sync errors → use `argocd-patterns`
- Understanding which env repo controls a service → use `gitops-environments`

## Overview

At <org>, every business domain manages its ArgoCD ApplicationSets through a dedicated `*-applicationsets/` repository. These repos use **helmfile** to render ArgoCD `ApplicationSet` resources via the **bedag/raw** Helm chart, which outputs raw Kubernetes manifests without opinionated templates.

The pattern decouples **what gets deployed** (ApplicationSet definition in `*-applicationsets/`) from **how it's configured per environment** (`*-environments/` repos).

## Repository structure

Each domain's applicationsets repo follows this layout:

```
<domain>-applicationsets/
├── helmfile.yaml.gotmpl              # Main helmfile (multi-environment)
├── applications/
│   └── values.yaml.gotmpl            # ApplicationSet for long-running services
├── bootstrap/
│   └── values.yaml.gotmpl            # ApplicationSet for bootstrap/infra resources
├── crons/
│   └── values.yaml.gotmpl            # ApplicationSet for CronWorkflows
└── environments/
    ├── default.yaml                   # Shared values across all envs
    ├── dev.yaml                       # DEV-specific overrides
    ├── prd.yaml                       # PRD-specific overrides
    └── btc.yaml                       # BTC-specific overrides
```

## Domain repos (8 active)

| Repo | Domain | CostCenter |
|------|--------|------------|
| `dpm-applicationsets` | DataPlatform | `Program-DataPlatform` |
| `dcp-applicationsets` | DataCapture | `Platform-DataCapture` / `Program-DataCapture` |
| `mdt-applicationsets` | Metadata | `Platform-Metadata` |
| `bm-applicationsets` | Billing & Monetization | `Platform-BaseServiceLayer-Billing` |
| `acum-applicationsets` | Access Control | `Platform-BaseServiceLayer-AccessControl` |
| `apps-applicationsets` | Apps | `Program-Apps` |
| `ai-applicationsets` | AI Services | `Platform-AIServices` |
| `ctp-applicationsets` | Client Tools | `Program-ClientToolsAndPrograms` |

## bedag/raw chart

The bedag/raw chart renders arbitrary YAML as Kubernetes resources. <org> uses it to generate `ApplicationSet` CRDs without needing a custom Helm chart.

```yaml
# applications/values.yaml.gotmpl produces:
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: dpm-applications
  namespace: argo
spec:
  generators:
    - git:
        repoURL: https://gitlab.internal/dpm/dpm-environments.git
        revision: HEAD
        directories:
          - path: "{{ .Values.environment }}/*"
  template:
    metadata:
      name: "{{`{{path.basename}}`}}"
    spec:
      project: dpm
      source:
        repoURL: https://gitlab.internal/devops/helm-charts.git
        chart: app
        targetRevision: HEAD
        helm:
          valueFiles:
            - "{{`{{path}}`}}/values.yaml"
      destination:
        server: "{{ .Values.clusterServer }}"
        namespace: "{{`{{path.basename}}`}}"
```

## Git directory generators

The ApplicationSet uses a **Git directory generator** that scans the `*-environments/` repo. Each subdirectory represents a service to deploy:

```
dpm-environments/
├── dev/
│   ├── people-api/
│   │   └── values.yaml
│   ├── people-process/
│   │   └── values.yaml
│   └── kyc-api/
│       └── values.yaml
├── prd/
│   ├── people-api/
│   │   └── values.yaml
│   └── people-process/
│       └── values.yaml
└── btc/
    └── people-batch/
        └── values.yaml
```

ArgoCD auto-discovers directories and creates one `Application` per service per environment.

## helmfile.yaml.gotmpl example

```yaml
environments:
  default:
    values:
      - environments/default.yaml
  dev:
    values:
      - environments/default.yaml
      - environments/dev.yaml
  prd:
    values:
      - environments/default.yaml
      - environments/prd.yaml
  btc:
    values:
      - environments/default.yaml
      - environments/btc.yaml

---

releases:
  - name: dpm-applications
    namespace: argo
    chart: bedag/raw
    version: 2.0.0
    values:
      - applications/values.yaml.gotmpl

  - name: dpm-crons
    namespace: argo
    chart: bedag/raw
    version: 2.0.0
    values:
      - crons/values.yaml.gotmpl

  - name: dpm-bootstrap
    namespace: argo
    chart: bedag/raw
    version: 2.0.0
    values:
      - bootstrap/values.yaml.gotmpl
```

## Values layering

Values are merged in order (last wins):

1. `environments/default.yaml` — shared config (repo URLs, project name, chart version)
2. `environments/<env>.yaml` — environment-specific (cluster server, namespace prefix, revision)
3. `applications/values.yaml.gotmpl` — template that consumes merged values

Example `environments/default.yaml`:
```yaml
domain: dpm
environmentsRepo: https://gitlab.internal/dpm/dpm-environments.git
chartRepo: https://gitlab.internal/devops/helm-charts.git
chartVersion: HEAD
project: dpm
```

Example `environments/prd.yaml`:
```yaml
environment: prd
clusterServer: https://kubernetes.default.svc
syncPolicy:
  automated:
    prune: true
    selfHeal: true
```

## Onboarding a new service

1. **Create directory** in the environments repo: `<env>/<service-name>/values.yaml`
2. **Populate values.yaml** with <org> app chart values (image, replicas, env vars, labels)
3. **Commit and push** — ArgoCD auto-discovers the new directory via Git generator
4. **ArgoCD syncs** — creates the Application and deploys the service

No changes needed in the applicationsets repo unless adding a new release type.

## Rendering and validation

```bash
# Preview what helmfile will render (read-only)
helmfile -e prd template

# Show diff against live cluster
helmfile -e prd diff

# Apply (requires approval — modifies ArgoCD resources)
helmfile -e prd apply
```

## Anti-patterns

- ❌ Creating ArgoCD `Application` resources manually (bypasses ApplicationSet auto-discovery)
- ❌ Hardcoding cluster URLs or repo paths in values.yaml.gotmpl (use environment layering)
- ❌ Skipping the environments repo (putting service values directly in applicationsets repo)
- ❌ Using `latest` as `targetRevision` for Helm charts (pin to specific version or HEAD with SHA)
- ❌ Mixing multiple domains in one applicationsets repo (one repo per domain)
- ❌ Deploying without `syncPolicy.automated` in PRD (manual sync defeats GitOps)
- ❌ Forgetting `prune: true` (orphaned resources accumulate)
- ❌ Editing live Applications in ArgoCD UI (changes get overwritten by ApplicationSet)

## Related

- `helm-chart-app` skill — the <org> app chart consumed by ApplicationSets
- `helmfile-templating` skill — escaping gotchas in gotmpl files

Branch-to-environment mapping follows the same `dev`/`prd`/`btc` split used throughout this catalog: each branch in the `*-environments/` repo corresponds to the matching directory scanned by the Git directory generator (see "Repository structure" above).

## Related skills
- `argocd-patterns` — ArgoCD configuration
- `helm-chart-app` — the app chart being deployed
- `gitops-environments` — environment topology
- `helmfile-k8s-addon` — cluster add-on management
