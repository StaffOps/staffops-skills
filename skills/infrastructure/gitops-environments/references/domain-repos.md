# GitOps Environment Repositories — Full Catalog

## DCP (DataCapture)

| Repository | Environment | Cluster |
|-----------|-------------|---------|
| `kubernetes/environments/dcp/development/dcp-applications-dev` | DEV | applications-dev-nv |
| `kubernetes/environments/dcp/production/dcp-applications-prd` | PRD | applications-prd-nv |
| `kubernetes/environments/dcp/production/dcp-applications-prd-sp` | PRD | applications-prd-sp |
| `kubernetes/environments/dcp/production/dcp-events-prd` | PRD | applications-prd-nv |
| `kubernetes/environments/dcp/batch/dcp-applications-btc` | BTC | applications-prd-nv |
| `kubernetes/environments/dcp/development/dcp-coldstorage-test` | DEV | applications-dev-nv |

## DPM (DataPlatform)

| Repository | Environment | Cluster |
|-----------|-------------|---------|
| `kubernetes/environments/dpm/development/dpm-applications-dev` | DEV | applications-dev-nv |
| `kubernetes/environments/dpm/production/dpm-applications-prd` | PRD | applications-prd-nv |
| `kubernetes/environments/dpm/batch/dpm-applications-btc` | BTC | applications-prd-nv |

## APPS (Apps/OCR)

| Repository | Environment | Cluster |
|-----------|-------------|---------|
| `kubernetes/environments/apps/development/apps-applications-dev` | DEV | applications-dev-nv |
| `kubernetes/environments/apps/production/apps-applications-prd` | PRD | applications-prd-nv |
| `kubernetes/environments/apps/batch/apps-applications-btc` | BTC | applications-prd-nv |
| `kubernetes/environments/apps/production/apps-cronworkflows-prd` | PRD (cron) | applications-prd-nv |

## PLG (Plugins)

| Repository | Environment | Cluster |
|-----------|-------------|---------|
| `kubernetes/environments/plg/development/plg-applications-dev` | DEV | applications-dev-nv |
| `kubernetes/environments/plg/production/plg-applications-prd` | PRD | applications-prd-nv |

## MDT (Metadata)

| Repository | Environment | Cluster |
|-----------|-------------|---------|
| `kubernetes/environments/mdt/development/mdt-applications-dev` | DEV | applications-dev-nv |
| `kubernetes/environments/mdt/production/mdt-applications-prd` | PRD | applications-prd-nv |

## BM (Billing & Monetization)

| Repository | Environment | Cluster |
|-----------|-------------|---------|
| `kubernetes/environments/bm/development/bm-applications-dev` | DEV | applications-dev-nv |
| `kubernetes/environments/bm/production/bm-applications-prd` | PRD | applications-prd-nv |

## ACUM (AccessController User Management)

| Repository | Environment | Cluster |
|-----------|-------------|---------|
| `kubernetes/environments/acum/development/acum-applications-dev` | DEV | applications-dev-nv |
| `kubernetes/environments/acum/production/acum-applications-prd` | PRD | applications-prd-nv |

## SUP (Consumer Services)

| Repository | Environment | Cluster |
|-----------|-------------|---------|
| `kubernetes/environments/sup/production/sup-cronworkflows-prd` | PRD (cron) | applications-prd-nv |

## ApplicationSet Registry

| Repository | Purpose |
|-----------|---------|
| `kubernetes/argo/argo-cd/applicationsets` | Central ApplicationSet definitions |
| `kubernetes/argo/argo-cd/application-sets/apps-applicationsets` | APPS domain ApplicationSets |
