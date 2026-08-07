---
name: container-image-optimization
description: "Shrink image size and speed up builds and pulls."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [docker, image-size, layers, buildkit, cache, registry]
    category: containers
    related_skills: [dockerfile-authoring, docker-cli-operations]
---
# Container Image Optimization

Reducing image size and build time beyond the basics in
`dockerfile-authoring`. Smaller images pull faster (matters at deploy time,
multiplied across every node in a fleet), have a smaller attack surface, and
build faster when the cache is well-structured.

## When to Use

Use when an image is unexpectedly large, a build takes too long in CI, a
deploy is slow because nodes are pulling a multi-GB image, or reviewing a
Dockerfile specifically for size.

## Measure before optimizing

```bash
docker images myapp                        # total size
docker history myapp                        # size per layer
docker history --no-trunc myapp             # full commands, not truncated
dive myapp                                   # interactive layer explorer (if installed)
```

`docker history` immediately shows which instruction added the most size —
optimize that one first rather than guessing. A single `RUN apt-get install`
line that's 400MB is a better target than shaving a few MB off ten other
lines.

## The biggest lever: multi-stage builds

Covered in depth in `dockerfile-authoring` — worth restating as the single
highest-impact technique. A build stage with a full compiler toolchain can
be 800MB+; the runtime stage that copies out just the compiled artifact can
be under 50MB. Nothing else on this page moves the needle as much as this
one pattern.

## Choosing a smaller base

```
ubuntu:24.04            ~80MB
debian:12-slim          ~75MB
debian:12-slim (+cleanup) ~50MB
alpine:3.20              ~7MB
distroless/static         ~2MB (no libc at all -- fully static binaries only)
distroless/base           ~20MB (glibc, no shell/package manager)
scratch                    0MB (literally nothing; you provide everything)
```

Going from a full distro to `-slim` is usually free (same package
ecosystem, smaller default install). Going to Alpine or distroless is a real
trade-off — see `dockerfile-authoring`'s base image table for the
compatibility caveats before switching.

## Reducing layer size

```dockerfile
# Bad: three layers, and the middle one's temp files are only "deleted"
# in a LATER layer -- they still exist in the image's layer history.
RUN wget https://example.com/archive.tar.gz
RUN tar -xzf archive.tar.gz
RUN rm archive.tar.gz

# Good: one layer, cleanup happens before the layer is committed.
RUN wget https://example.com/archive.tar.gz \
    && tar -xzf archive.tar.gz \
    && rm archive.tar.gz
```

The same applies to package manager caches:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN apk add --no-cache curl        # --no-cache skips the index cache entirely
```

`--no-install-recommends` (apt) and `--no-cache` (apk) avoid pulling in
optional packages the image doesn't need in the first place — cheaper than
installing and then trying to remove them.

## BuildKit cache mounts

For package manager caches that should persist **across builds** (not baked
into the image, but reused to speed up rebuilds):

```dockerfile
# syntax=docker/dockerfile:1
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt/lists \
    apt-get update && apt-get install -y curl

RUN --mount=type=cache,target=/root/.npm \
    npm ci
```

This is different from the layer-caching discussed in `dockerfile-authoring`
— a cache mount persists across builds even when the layer itself is
invalidated (e.g., by a code change earlier in the Dockerfile), so
dependency downloads stay fast even when other cache is invalidated.
Requires BuildKit (default in Docker 23.0+; enable explicitly with
`DOCKER_BUILDKIT=1` on older versions).

## Multi-platform builds

```bash
docker buildx create --use
docker buildx build --platform linux/amd64,linux/arm64 -t myapp:latest --push .
```

Building for multiple architectures in one invocation avoids maintaining
separate Dockerfiles or CI jobs per platform. `--push` is required for
multi-platform output — a multi-arch manifest can't be loaded into the local
Docker daemon the way a single-platform build can with `--load`.

## Squashing layers (rarely the right tool)

```bash
docker build --squash -t myapp .     # experimental; merges all layers into one
```

`--squash` requires experimental features enabled on the daemon (or a
builder that supports it) — it is not available out of the box on every
Docker install; check `docker version` / `docker buildx version` for
support before relying on it in a CI pipeline. Squashing trades away
layer-level caching entirely — every build becomes a
full rebuild with no incremental reuse, and shared base-image layers can no
longer be deduplicated across images on the same host or in a registry.
Multi-stage builds achieve the same size benefit without this trade-off in
the overwhelming majority of cases; reach for `--squash` only when layer
count itself is the constraint (some older registries had layer limits).

## Registry-side considerations

```bash
docker manifest inspect myapp:latest    # inspect without a full pull
skopeo inspect docker://myapp:latest    # similar, no local Docker daemon needed
crane manifest myapp:latest              # another option, from the go-containerregistry tooling
```

Shared base-image layers are deduplicated at the registry and on each node's
local storage — this is why standardizing on one or two base images across
a fleet (rather than a different base per team) has a real, compounding
storage and pull-time benefit beyond any single image's own size.

## What to check first, in order

1. **Is this a multi-stage build?** If not, that's the fix, before anything
   else here.
2. **What does `docker history` show as the largest layer?** Optimize that
   one.
3. **Is a package manager cache being committed into a layer?** Clean it in
   the same `RUN`.
4. **Is the base image the smallest one that's actually compatible?**
5. **Is unnecessary build context being sent?** Check `.dockerignore`.

## Pitfalls

- **Deleting files in a later `RUN`** — they remain in an earlier layer's
  history; delete in the *same* instruction that created them.
- **Squashing as a first resort** — loses layer caching and cross-image
  deduplication for a benefit multi-stage builds usually already provide.
- **Switching to Alpine without checking compatibility** — musl libc can
  break native extensions or precompiled binaries silently.
- **A cache mount used for something that SHOULD ship in the image** — cache
  mounts are excluded from the final image; don't use one for application
  dependencies unless a separate `COPY`/install step also puts them where
  the runtime needs them.
- **Comparing image sizes without accounting for shared base layers** — two
  20MB images sharing a 15MB base cost the fleet 15MB once, not 40MB twice.

## Reference

- `dockerfile-authoring` — multi-stage builds, layer ordering fundamentals
- `docker-cli-operations` — `docker history`, `system df`, and cleanup commands

## When NOT to use

- Writing the Dockerfile itself (layer ordering, syntax) — use `dockerfile-authoring`
- Building golden/hardened base images with apko — use `container-image-apko`
- Debugging a running container that crashes — use `container-runtime-debugging`

## Related skills

- `dockerfile-authoring` — writing Dockerfiles that produce optimized images
- `container-image-apko` — apko-based minimal images (superset of optimization)
- `docker-cli-operations` — inspecting image layers and sizes with CLI
- `container-runtime-debugging` — when the optimized image fails at runtime
