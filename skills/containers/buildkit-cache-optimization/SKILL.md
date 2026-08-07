---
name: buildkit-cache-optimization
description: "Use when Docker builds are slow in CI. Covers layer ordering, cache mounts, registry cache backend, BuildKit inline cache, before/after patterns, and common mistakes that bust cache."
---

# BuildKit Cache Optimization

## When to use

- Docker builds are slow in CI (>5 minutes for incremental changes)
- Every push rebuilds from scratch despite minimal code changes
- Dependency installation (npm install, pip install, go mod download) repeats unnecessarily
- Need to share build cache across CI runners or branches
- Build times increased after a Dockerfile change

## When NOT to use

- Multi-architecture build setup (use `multi-arch-builds`)
- Registry management (use `registry-operations`)
- Image security/hardening (use `container-image-apko`)

## Core principle: layer ordering

Docker caches layers top-to-bottom. A changed layer invalidates ALL subsequent layers.

```dockerfile
# ❌ BAD — code change busts dependency cache
COPY . .
RUN pip install -r requirements.txt

# ✅ GOOD — dependencies cached until requirements.txt changes
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
```

## Cache optimization by language

### Go

```dockerfile
FROM golang:1.22-alpine AS builder
WORKDIR /src

# Layer 1: dependencies (cached until go.mod/go.sum change)
COPY go.mod go.sum ./
RUN go mod download

# Layer 2: code (rebuilds on any .go change)
COPY . .
RUN CGO_ENABLED=0 go build -o /app ./cmd/server/
```

### Python

```dockerfile
FROM python:3.11-slim
WORKDIR /app

# Layer 1: system deps (rarely changes)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Layer 2: Python deps (cached until requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Layer 3: code
COPY . .
```

### .NET

```dockerfile
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src

# Layer 1: restore (cached until .csproj changes)
COPY *.csproj .
RUN dotnet restore

# Layer 2: build (rebuilds on code change)
COPY . .
RUN dotnet publish -c Release -o /app --no-restore
```

### Node.js

```dockerfile
FROM node:20-slim
WORKDIR /app

# Layer 1: deps (cached until package-lock changes)
COPY package.json package-lock.json ./
RUN npm ci --production

# Layer 2: code
COPY . .
RUN npm run build
```

## BuildKit cache mounts

Cache mounts persist data across builds without adding to layers. Ideal for package manager caches.

```dockerfile
# syntax=docker/dockerfile:1

# Go module cache
RUN --mount=type=cache,target=/go/pkg/mod \
    go mod download

# Go build cache
RUN --mount=type=cache,target=/root/.cache/go-build \
    go build -o /app ./cmd/server/

# pip cache
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# npm cache
RUN --mount=type=cache,target=/root/.npm \
    npm ci

# apt cache
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt \
    apt-get update && apt-get install -y gcc
```

## Registry cache backend (cross-runner cache sharing)

### Inline cache (simplest, limited)

```bash
# Build with inline cache metadata
docker buildx build \
  --cache-from type=registry,ref=registry.example.com/myapp:cache \
  --cache-to type=inline \
  -t registry.example.com/myapp:latest \
  --push .
```

Limitation: only caches the final stage layers.

### Registry cache (full layer cache)

```bash
# Export full build cache to a dedicated cache image
docker buildx build \
  --cache-from type=registry,ref=registry.example.com/myapp:buildcache \
  --cache-to type=registry,ref=registry.example.com/myapp:buildcache,mode=max \
  -t registry.example.com/myapp:latest \
  --push .
```

`mode=max` caches ALL layers (including intermediate build stages).

### Local cache (single machine, fastest)

```bash
docker buildx build \
  --cache-from type=local,src=/tmp/buildcache \
  --cache-to type=local,dest=/tmp/buildcache,mode=max \
  -t myapp:latest .
```

### GitHub Actions cache

```bash
docker buildx build \
  --cache-from type=gha \
  --cache-to type=gha,mode=max \
  -t myapp:latest .
```

## CI configuration pattern

```yaml
# GitLab CI example with registry cache
build:
  stage: build
  script:
    - docker buildx build
        --cache-from type=registry,ref=${CI_REGISTRY_IMAGE}:buildcache
        --cache-to type=registry,ref=${CI_REGISTRY_IMAGE}:buildcache,mode=max
        -t ${CI_REGISTRY_IMAGE}:${CI_COMMIT_SHORT_SHA}
        --push .
```

## Common cache busters (mistakes that invalidate cache)

| Mistake | Why it busts cache | Fix |
|---------|-------------------|-----|
| `COPY . .` before `RUN install` | Any file change invalidates install | Copy only dep files first |
| `ARG BUILD_DATE` before deps | ARG changes layer hash | Move ARGs after dep install |
| `RUN apt-get update && install` without cache mount | Re-downloads every build | Use `--mount=type=cache` |
| `.dockerignore` missing | `.git/` changes hash | Add `.git`, `node_modules`, etc |
| Timestamp in generated files | Different every build | Use `SOURCE_DATE_EPOCH` |
| `ADD` with remote URL | Re-fetches every build | Use `RUN curl` + cache mount |

## .dockerignore (essential for cache)

```
.git
.gitignore
node_modules
__pycache__
*.pyc
.env
.vscode
.idea
dist
build
coverage
*.log
docker-compose*.yml
Makefile
README.md
```

## Before/after comparison

```
BEFORE (no optimization):
  Layer 1: FROM python:3.11       (cached)
  Layer 2: COPY . .               (BUSTED — any file change)
  Layer 3: RUN pip install ...     (BUSTED — depends on layer 2)
  Layer 4: RUN python setup.py    (BUSTED)
  Total: ~4 minutes every push

AFTER (optimized):
  Layer 1: FROM python:3.11       (cached)
  Layer 2: COPY requirements.txt  (cached unless deps change)
  Layer 3: RUN pip install ...     (cached — cache mount)
  Layer 4: COPY . .               (rebuilt — fast, just file copy)
  Layer 5: RUN python setup.py    (rebuilt — fast, no downloads)
  Total: ~30 seconds for code-only changes
```

## Anti-patterns

- ❌ `COPY . .` as the first instruction (invalidates everything)
- ❌ Not using `.dockerignore` (`.git/` changes invalidate all layers)
- ❌ `ARG` or `ENV` with dynamic values (timestamp, commit SHA) before dep install
- ❌ `apt-get update` without cache mount (downloads package lists every time)
- ❌ Multi-stage builds without `--mount=type=cache` on expensive stages
- ❌ Not using `--cache-from` in CI (every runner builds from scratch)
- ❌ `npm install` instead of `npm ci` (non-deterministic, slower)
- ❌ Inline cache only (`mode=min`) when intermediate stages are expensive

## Related skills

- `multi-arch-builds` — Multi-architecture builds (cache per-platform)
- `registry-operations` — Cache image storage and lifecycle
- `container-image-apko` — Alternative build system (apko has own cache)
