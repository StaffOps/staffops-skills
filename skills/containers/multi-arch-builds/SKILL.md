---
name: multi-arch-builds
description: "Use when building container images for mixed amd64/arm64 clusters (Graviton). Covers buildx setup, Dockerfile TARGETARCH, CI parallel builds, tag conventions, testing both architectures, and manifest list vs suffixed tags decision."
---

# Multi-Architecture Container Builds

## When to use

- Building images for clusters with mixed amd64/arm64 nodes (e.g., Graviton)
- Setting up CI pipeline for multi-arch image builds
- Debugging scheduling failures on arm64 nodes
- Migrating from single-arch to multi-arch images
- Choosing between manifest lists and suffixed tags

## When NOT to use

- Building for a single-arch environment (no arm64 nodes)
- Optimizing build speed (use `buildkit-cache-optimization`)
- Registry management (use `registry-operations`)

## Why multi-arch matters

arm64 nodes (AWS Graviton, Apple Silicon) offer 20-40% cost savings. If your image only supports amd64:
- Scheduler avoids arm64 nodes → expensive x86 nodes used instead
- Pod stays `Pending` if only arm64 capacity available
- Cost optimization tools (Karpenter) can't leverage cheaper instances

## Buildx setup

```bash
# Create a multi-platform builder
docker buildx create --name multiarch --driver docker-container --use
docker buildx inspect --bootstrap

# Verify QEMU is available for cross-platform emulation
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes

# Check available platforms
docker buildx ls
```

## Dockerfile patterns

### Go (static binary — best case)

```dockerfile
FROM --platform=$BUILDPLATFORM golang:1.22-alpine AS builder
ARG TARGETARCH
ARG TARGETOS

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
    go build -ldflags="-s -w" -o /app ./cmd/server/

FROM gcr.io/distroless/static:nonroot
COPY --from=builder /app /app
ENTRYPOINT ["/app"]
```

### .NET (runtime is multi-arch)

```dockerfile
FROM --platform=$BUILDPLATFORM mcr.microsoft.com/dotnet/sdk:8.0 AS build
ARG TARGETARCH
WORKDIR /src
COPY *.csproj .
RUN dotnet restore -a ${TARGETARCH}
COPY . .
RUN dotnet publish -a ${TARGETARCH} -c Release -o /app --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:8.0
COPY --from=build /app .
ENTRYPOINT ["dotnet", "MyApp.dll"]
```

### Python (mostly arch-agnostic, watch for native deps)

```dockerfile
FROM --platform=$TARGETPLATFORM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "myapp"]
```

**Warning**: Python packages with C extensions (numpy, grpcio, cryptography) need arch-specific wheels. Ensure wheels exist for both platforms or compile from source.

## Build strategies

### Strategy 1: Single manifest list (preferred for registries that support it)

```bash
# Build and push both architectures as one manifest
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t registry.example.com/myapp:v1.2.3 \
  --push .
```

Pros: single tag, Docker runtime pulls correct arch automatically.
Cons: slower build (sequential on single machine unless remote builders).

### Strategy 2: Parallel CI jobs + manifest create

```yaml
# GitLab CI example
build:amd64:
  stage: build
  tags: [docker-amd64]
  script:
    - docker buildx build --platform linux/amd64
        -t ${IMAGE}:${SHA}-amd64 --push .

build:arm64:
  stage: build
  tags: [docker-arm64]  # native arm64 runner (faster than QEMU)
  script:
    - docker buildx build --platform linux/arm64
        -t ${IMAGE}:${SHA}-arm64 --push .

manifest:
  stage: publish
  needs: [build:amd64, build:arm64]
  script:
    - docker manifest create ${IMAGE}:${SHA}
        ${IMAGE}:${SHA}-amd64
        ${IMAGE}:${SHA}-arm64
    - docker manifest push ${IMAGE}:${SHA}
```

Pros: much faster (native builds, no QEMU emulation), parallelizable.
Cons: requires per-arch runners, extra manifest step.

### Strategy 3: Suffixed tags (simplest, no manifest)

```bash
# amd64
docker buildx build --platform linux/amd64 -t myapp:v1.2.3 --push .
# arm64
docker buildx build --platform linux/arm64 -t myapp:v1.2.3-arm64 --push .
```

Pros: works everywhere, no manifest support needed.
Cons: Kubernetes manifests must specify correct tag per node arch (complex).

## Decision tree: manifest list vs suffixed tags

```
Registry supports OCI manifests?
├── Yes (ECR, Harbor 2.x+, GHCR, Docker Hub)
│   └── Use manifest list (Strategy 1 or 2)
│       ├── Have native arm64 runners? → Strategy 2 (parallel)
│       └── No native runners? → Strategy 1 (QEMU, slower)
└── No (legacy registry)
    └── Use suffixed tags (Strategy 3)
        └── Set nodeSelector or nodeAffinity in K8s manifests
```

## Testing both architectures

```bash
# Validate image runs on both platforms
docker run --rm --platform linux/amd64 ${IMAGE}:${TAG} /healthz
docker run --rm --platform linux/arm64 ${IMAGE}:${TAG} /healthz

# Inspect manifest to confirm both archs present
docker manifest inspect ${IMAGE}:${TAG} | jq '.manifests[].platform'

# Expected output:
# {"architecture": "amd64", "os": "linux"}
# {"architecture": "arm64", "os": "linux"}
```

## Tag conventions

| Tag | Meaning |
|-----|---------|
| `v1.2.3` | Multi-arch manifest (preferred) |
| `<sha>` | Multi-arch manifest from CI |
| `<sha>-amd64` | Explicit amd64 (used during build) |
| `<sha>-arm64` | Explicit arm64 (used during build) |
| `latest` | Multi-arch manifest of main branch |

## Common issues

| Problem | Cause | Fix |
|---------|-------|-----|
| `exec format error` | Wrong arch binary | Check `TARGETARCH` in Dockerfile |
| QEMU crash during build | Complex native code + emulation | Use native runners |
| Slow arm64 builds | QEMU emulation on amd64 host | Use native arm64 runner |
| Missing Python wheel | No arm64 wheel published | Build from source or find alternative |
| `.node_modules` native addon fails | npm install ran on wrong arch | Use `--platform=$BUILDPLATFORM` for install |

## Anti-patterns

- ❌ `--platform linux/amd64` only (breaks arm64 scheduling)
- ❌ `FROM amd64/alpine` (arch-pinned base image)
- ❌ Skipping arm64 testing ("it compiles so it works")
- ❌ QEMU for production builds (too slow, use native runners)
- ❌ Not using `$BUILDPLATFORM` for build stage (forces emulation)
- ❌ Architecture-specific system libs without conditional install
- ❌ Single-arch base images in multi-stage builds

## Related skills

- `buildkit-cache-optimization` — Speed up multi-arch builds
- `registry-operations` — Manifest list support, replication
- `container-image-apko` — apko handles multi-arch by default
