---
name: registry-operations
description: "Use when managing container registries (Harbor, ECR, GHCR). Covers garbage collection, retention policies, replication, vulnerability scanning integration, pull-through cache setup, and which registry for what."
---

# Container Registry Operations

## When to use

- Setting up or managing container registries (Harbor, ECR, GHCR)
- Configuring image retention and garbage collection
- Setting up registry replication (cross-region, cross-registry)
- Integrating vulnerability scanning into push/pull workflows
- Configuring pull-through cache for public registries
- Debugging `ImagePullBackOff` errors related to registry

## When NOT to use

- Building multi-arch images (use `multi-arch-builds`)
- Optimizing Docker build speed (use `buildkit-cache-optimization`)
- Image signing with cosign (use `cosign-image-signing`)

## Decision tree: which registry for what

```
What type of image?
├── Application deployable (team builds, ships to K8s)?
│   └── ECR (or primary cloud registry)
│       - Integrated with cloud IAM (no separate creds)
│       - Lifecycle policies built-in
│       - Cross-region replication native
├── Golden/base image (used in FROM, hardened)?
│   └── Harbor (or self-hosted registry)
│       - Cosign signature visibility
│       - Project-based access control
│       - Vulnerability scanning + policy
├── CI ephemeral / MR review builds?
│   └── Harbor (short retention project)
│       - Aggressive GC (7-14 day TTL)
│       - Separate from production images
├── Public image cache (Docker Hub, quay, gcr)?
│   └── Harbor pull-through cache OR ECR pull-through
│       - Avoids Docker Hub rate limits
│       - Faster pulls (local network)
│       - Audit trail of what's pulled
└── Open-source distribution?
    └── GHCR or Docker Hub
        - Public visibility
        - GitHub Actions integration
```

## ECR operations

### Lifecycle policies (automatic cleanup)

```bash
# Set retention: keep last 30 tagged images, expire untagged after 7 days
aws ecr put-lifecycle-policy \
  --repository-name myapp \
  --lifecycle-policy-text '{
    "rules": [
      {
        "rulePriority": 1,
        "description": "Expire untagged after 7 days",
        "selection": {
          "tagStatus": "untagged",
          "countType": "sinceImagePushed",
          "countUnit": "days",
          "countNumber": 7
        },
        "action": {"type": "expire"}
      },
      {
        "rulePriority": 2,
        "description": "Keep last 30 tagged images",
        "selection": {
          "tagStatus": "tagged",
          "tagPrefixList": ["v"],
          "countType": "imageCountMoreThan",
          "countNumber": 30
        },
        "action": {"type": "expire"}
      }
    ]
  }'
```

### Cross-region replication

```bash
aws ecr put-replication-configuration \
  --replication-configuration '{
    "rules": [{
      "destinations": [
        {"region": "eu-west-1", "registryId": "<account-id>"}
      ],
      "repositoryFilters": [
        {"filter": "prod-", "filterType": "PREFIX_MATCH"}
      ]
    }]
  }'
```

### Pull-through cache (public → ECR)

```bash
# Create pull-through cache rule for Docker Hub
aws ecr create-pull-through-cache-rule \
  --ecr-repository-prefix docker-hub \
  --upstream-registry-url registry-1.docker.io

# Usage: pull via ECR instead of Docker Hub directly
# docker pull <account>.dkr.ecr.<region>.amazonaws.com/docker-hub/library/nginx:latest
```

### Scanning on push

```bash
# Enable scanning
aws ecr put-image-scanning-configuration \
  --repository-name myapp \
  --image-scanning-configuration scanOnPush=true

# Get scan findings
aws ecr describe-image-scan-findings \
  --repository-name myapp \
  --image-id imageTag=v1.2.3
```

## Harbor operations

### Garbage collection

```bash
# Harbor GC via API (schedule or manual trigger)
curl -X POST "https://harbor.example.com/api/v2.0/system/gc/schedule" \
  -H "Authorization: Basic $(echo -n admin:password | base64)" \
  -H "Content-Type: application/json" \
  -d '{"schedule":{"type":"Manual"},"parameters":{"delete_untagged":true}}'

# Check GC status
curl "https://harbor.example.com/api/v2.0/system/gc" \
  -H "Authorization: Basic $(echo -n admin:password | base64)"
```

### Retention policies

```bash
# Set retention via API: keep last 10 tags matching semver
curl -X POST "https://harbor.example.com/api/v2.0/retentions" \
  -H "Authorization: Basic $(echo -n admin:password | base64)" \
  -H "Content-Type: application/json" \
  -d '{
    "algorithm": "or",
    "rules": [{
      "action": "retain",
      "template": "latestPushedK",
      "params": {"latestPushedK": 10},
      "tag_selectors": [{"kind": "doublestar", "decoration": "matches", "pattern": "v*"}],
      "scope_selectors": {"repository": [{"kind": "doublestar", "decoration": "repoMatches", "pattern": "**"}]}
    }],
    "trigger": {"kind": "Schedule", "settings": {"cron": "0 0 0 * * *"}},
    "scope": {"level": "project", "ref": 1}
  }'
```

### Replication (Harbor → Harbor or Harbor → ECR)

```bash
# Create replication policy
curl -X POST "https://harbor.example.com/api/v2.0/replication/policies" \
  -H "Authorization: Basic $(echo -n admin:password | base64)" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "golden-to-dr",
    "src_registry": null,
    "dest_registry": {"id": 2},
    "dest_namespace": "golden-images",
    "trigger": {"type": "event_based"},
    "filters": [{"type": "name", "value": "golden/**"}],
    "enabled": true
  }'
```

### Pull-through cache (proxy projects)

In Harbor UI: Projects → New Project → Type: Proxy Cache → Endpoint: `https://registry-1.docker.io`

Pull pattern: `harbor.example.com/dockerhub-cache/library/nginx:latest`

## Debugging ImagePullBackOff

```bash
# Check pod events for pull errors
kubectl describe pod <pod> | grep -A5 "Events:"

# Common causes:
# 1. Auth failure → check imagePullSecrets
kubectl get pod <pod> -o jsonpath='{.spec.imagePullSecrets}'

# 2. Image doesn't exist → verify tag
# ECR:
aws ecr describe-images --repository-name myapp --image-ids imageTag=v1.2.3
# Harbor:
curl "https://harbor.example.com/api/v2.0/projects/myproject/repositories/myapp/artifacts?q=tags%3Dv1.2.3"

# 3. Rate limited (Docker Hub) → check pull-through cache
kubectl get events --field-selector reason=Failed | grep -i "toomanyrequests"

# 4. Wrong architecture → inspect manifest
docker manifest inspect <image> | jq '.manifests[].platform'
```

## Vulnerability scanning integration

### Scan gate in CI

```bash
# Trivy scan before push (fail on HIGH/CRITICAL)
trivy image --exit-code 1 --severity HIGH,CRITICAL \
  --ignore-unfixed ${IMAGE}:${TAG}

# Grype alternative
grype ${IMAGE}:${TAG} --fail-on high
```

### Admission control (runtime)

```yaml
# Kyverno policy: block images with critical CVEs
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: block-vulnerable-images
spec:
  validationFailureAction: Enforce
  rules:
  - name: check-vulnerabilities
    match:
      any:
      - resources:
          kinds: ["Pod"]
    verifyImages:
    - imageReferences: ["*"]
      attestations:
      - predicateType: cosign.sigstore.dev/attestation/vuln/v1
        conditions:
        - all:
          - key: "{{ scanner.result.summary.criticalCount }}"
            operator: Equals
            value: "0"
```

## Anti-patterns

- ❌ No lifecycle/retention policy (registry grows unbounded, costs increase)
- ❌ Pulling from Docker Hub directly (rate limits, no audit, slower)
- ❌ `latest` tag in production (mutable, unreproducible)
- ❌ Single registry for all image types (no separation of concerns)
- ❌ No vulnerability scanning gate (vulnerable images reach production)
- ❌ Manual GC only (should be scheduled)
- ❌ Storing build cache in the same repo as production images
- ❌ No replication for disaster recovery (single point of failure)

## Related skills

- `multi-arch-builds` — Building for multiple architectures
- `buildkit-cache-optimization` — Registry cache backend for builds
- `cosign-image-signing` — Signing images in registries
- `container-image-apko` — Building minimal base images
