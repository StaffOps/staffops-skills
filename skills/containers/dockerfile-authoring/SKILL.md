---
name: dockerfile-authoring
description: "Write small, cacheable, secure Dockerfiles."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [docker, dockerfile, build, multi-stage, cache, image]
    category: containers
    related_skills: [container-image-optimization, docker-cli-operations]
---
# Dockerfile Authoring

Writing Dockerfiles that build fast, produce small images, and don't leak
secrets or build tooling into the final layer. Centers on multi-stage builds
and cache-friendly layer ordering — the two techniques that account for most
of the difference between an amateur and a production Dockerfile.

## When to Use

Use when writing a new Dockerfile, reviewing one for a pull request,
debugging a slow or bloated build, or explaining why changing one line
invalidated the entire build cache.

## Layer caching: order matters

Docker caches each instruction as a layer and reuses it if the instruction
and its inputs are unchanged. **Put what changes least at the top:**

```dockerfile
FROM node:20-slim

WORKDIR /app

# Dependency manifests change rarely -- this layer is cached across
# almost every code change.
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# Application code changes every commit -- put it LAST so only this
# layer (and everything after it) gets invalidated.
COPY . .

CMD ["node", "server.js"]
```

Reversing the order — copying everything first, then installing — means
every single code change reinstalls every dependency, turning a 2-second
build into a 2-minute one.

## Multi-stage builds

Separate the build environment (compilers, dev headers, source) from the
runtime image. Only the final stage ships:

```dockerfile
# Stage 1: build
FROM golang:1.23 AS builder
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /app ./cmd/server

# Stage 2: runtime -- none of the Go toolchain ends up here
FROM gcr.io/distroless/static-debian12
COPY --from=builder /app /app
USER nonroot:nonroot
ENTRYPOINT ["/app"]
```

This is the single highest-leverage technique in Dockerfile authoring: a Go
binary's runtime image can be tens of megabytes instead of the builder
image's several hundred, and the runtime image contains no compiler, no
shell, and no source code to leak.

Named stages (`AS builder`) can be targeted directly for debugging or CI:

```bash
docker build --target builder -t myapp:debug .
```

## Choosing a base image

| Base | Size | Shell/pkg mgr | Use when |
| --- | --- | --- | --- |
| `scratch` | 0 | None | A fully static binary, nothing else needed |
| `distroless` | ~20MB | None (no shell) | Compiled languages, minimal attack surface |
| `alpine` | ~5MB | `sh`, `apk` | Need a shell/tools; watch musl libc compatibility |
| `debian-slim` | ~80MB | `sh`, `apt` | glibc compatibility matters, still want small |
| Full distro | 100s of MB | Everything | Rarely justified for a container image |

Alpine's musl libc (vs glibc) occasionally breaks precompiled binaries and
changes DNS resolution behavior subtly — a real cost, not just a smaller
number. `distroless` and `-slim` variants are usually the better default
when the language ecosystem doesn't specifically need Alpine.

## .dockerignore

Without it, `COPY . .` sends everything in the build context to the daemon,
including `.git`, `node_modules`, and local secrets:

```
.git
node_modules
*.log
.env
.env.*
dist/
coverage/
.dockerignore
Dockerfile
```

A large build context slows every build (it's transferred before the first
instruction even runs) and is a real path for accidental secret leakage into
an image layer.

## Secrets: never bake them into a layer

```dockerfile
# WRONG -- the secret is permanently in the image's layer history, even
# if a LATER instruction deletes the file.
COPY secret.pem /tmp/secret.pem
RUN some-command --key=/tmp/secret.pem
RUN rm /tmp/secret.pem

# Correct -- BuildKit secret mount, never written to any layer.
RUN --mount=type=secret,id=mykey \
    some-command --key=/run/secrets/mykey
```

```bash
DOCKER_BUILDKIT=1 docker build --secret id=mykey,src=./secret.pem .
```

`docker history` and `docker save | tar -x` both expose every layer's
contents — deleting a file in a later instruction does not remove it from
the image, only from the final visible filesystem. Build secrets need
`--mount=type=secret`; runtime secrets belong in the orchestrator (Kubernetes
Secret, Docker secret), never `ENV` or `ARG` with a default.

## Running as non-root

```dockerfile
RUN groupadd -r app && useradd -r -g app app
USER app
```

Or, for a distroless/scratch image, reference the numeric UID directly since
there's no `useradd` available:

```dockerfile
COPY --from=builder --chown=65532:65532 /app /app
USER 65532:65532
```

Running as root inside a container is not equivalent to root on the host —
namespaces provide real isolation — but it is still unnecessary risk: a
container-escape vulnerability is strictly worse combined with root, and many
Kubernetes admission policies now reject root containers outright.

## Combining RUN instructions

```dockerfile
# Each RUN is a layer; apt update's effect is invisible to a LATER,
# separately-cached RUN apt install, which can silently install stale
# packages if the layers are cached independently.
RUN apt-get update
RUN apt-get install -y curl

# Correct: one layer, and the cache is invalidated together.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
```

Cleaning the package cache **in the same RUN** matters — doing it in a later
instruction adds a new layer without shrinking the earlier one; the image
still contains the cache, just marked deleted in a subsequent layer.

## ARG scope in multi-stage builds

```dockerfile
# syntax=docker/dockerfile:1
ARG BASE_TAG=20-slim          # usable in FROM lines below, nowhere else yet

FROM node:${BASE_TAG} AS builder
ARG BASE_TAG                  # must be redeclared to use it INSIDE this stage
RUN echo "built from node:${BASE_TAG}"

FROM node:${BASE_TAG} AS runtime
# BASE_TAG is available here for the FROM line without redeclaring,
# but using it in a RUN/ENV below this point still needs its own ARG line.
```

An `ARG` declared before the first `FROM` is only in scope for `FROM`
instructions themselves; each stage that needs the value in a `RUN`,
`ENV`, or elsewhere must redeclare `ARG BASE_TAG` after its own `FROM`. A
value that silently resolves to empty inside a later stage's `RUN` is
almost always this — not a build-arg-passing failure at the `docker build
--build-arg` level.

## Common instructions, used correctly

```dockerfile
FROM node:20-slim AS base
ARG BUILD_VERSION=dev
ENV NODE_ENV=production
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s \
    CMD curl -f http://localhost:3000/health || exit 1
USER node
ENTRYPOINT ["node"]
CMD ["server.js"]
```

| Directive | Notes |
| --- | --- |
| `ARG` | Build-time only, not present in the running container; scope is per-stage (see below) |
| `ENV` | Persists into the running container; visible via `docker inspect` |
| `ENTRYPOINT` vs `CMD` | `ENTRYPOINT` is the fixed command; `CMD` supplies default arguments to it, and is fully replaceable at `docker run` |
| `HEALTHCHECK` | Lets `docker ps` and orchestrators see liveness without an external prober |
| `EXPOSE` | Documentation only — does not actually publish the port |

## Pitfalls

- **`COPY . .` before installing dependencies** — invalidates the dependency
  cache on every code change.
- **Secrets via `ARG`/`ENV`** — visible in `docker history` and image
  metadata even after being "overwritten" later.
- **`apt-get update` and `install` in separate `RUN`s** — breaks the cache
  coherence between them.
- **Not pinning the base image tag** — `FROM node:latest` means the build is
  not reproducible; pin a specific version (and ideally a digest).
- **Running as root with no `USER` instruction** — unnecessary privilege.
- **A `.dockerignore` that forgets `.git`** — leaks commit history and
  potentially secrets from old commits into the build context.
- **Multi-stage build where the final `FROM` still uses the builder image**
  — defeats the entire point; verify the last stage is genuinely minimal.
- **Using a global `ARG` inside a stage without redeclaring it** — it's in
  scope for `FROM` lines only until re-declared with `ARG` after that
  stage's own `FROM`; otherwise it silently resolves to empty.

## Verification

```bash
docker build -t myapp:test .
docker history myapp:test              # inspect every layer and its size
docker run --rm myapp:test whoami      # confirm it is NOT root, if intended
docker inspect myapp:test | grep -A5 '"Env"'   # check for leaked secrets
dive myapp:test                        # interactive layer explorer, if installed
```

`docker history` is the fastest sanity check that a secret didn't end up
baked into a layer — read every `RUN`/`COPY` line, not just the final image
size.

## Reference

- `container-image-optimization` — squeezing size further, layer analysis
- `docker-cli-operations` — build flags, BuildKit features, registry push


## Decision tree

```
Dockerfile design choice
├── Which base image?
│   ├── Golden apko image exists in bdc-images? → use it (signed, minimal, multi-arch)
│   ├── Need runtime only (no build tools) → use -slim or distroless variant
│   └── Need build tools at runtime? → probably wrong; use multi-stage instead
├── Multi-stage needed?
│   ├── Compiled language (.NET, Go, Rust) → YES: build stage + runtime stage
│   ├── Interpreted (Python, Node) → MAYBE: install deps in build stage, copy venv/node_modules
│   └── Simple script/single binary → NO: single FROM is fine
└── Secrets during build?
    ├── Need private repo access (pip/go/npm) → BuildKit --mount=type=secret (NEVER ARG/ENV)
    ├── Need AWS creds for asset download → --mount=type=secret + AWS_SHARED_CREDENTIALS_FILE
    └── Runtime secret → don't bake in; use ExternalSecret + volume mount at deploy time
```

## When NOT to use

- Building golden/hardened base images without Dockerfile — use `container-image-apko`
- Reducing size of an already-built image — use `container-image-optimization`
- Running/debugging containers after build — use `docker-cli-operations`

## Related skills

- `container-image-optimization` — advanced size reduction beyond Dockerfile best practices
- `container-image-apko` — declarative image builds that bypass Dockerfile entirely
- `docker-compose-patterns` — multi-stage builds in compose context
- `docker-cli-operations` — testing built images interactively
- `container-runtime-debugging` — when the built image misbehaves at runtime
