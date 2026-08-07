# Image Size Reduction Checklist

## Quick wins (biggest impact first)

```bash
# Check current size
docker images myapp --format "{{.Size}}"
docker history --no-trunc myapp:latest | head -20  # find big layers
dive myapp:latest                                   # interactive layer explorer
```

## Checklist

### 1. Multi-stage build (saves 50-90%)
- [ ] Build stage: full SDK/compiler
- [ ] Runtime stage: minimal base (distroless, alpine, slim)
- [ ] COPY --from=builder only the binary/artifact

### 2. Base image selection
| Need | Image | Size |
|------|-------|------|
| Static Go binary | `gcr.io/distroless/static` | ~2MB |
| Go with glibc | `gcr.io/distroless/base` | ~20MB |
| .NET | `mcr.microsoft.com/dotnet/aspnet:8.0-alpine` | ~100MB |
| Python | `python:3.11-slim` | ~120MB |
| Node | `node:20-slim` | ~180MB |
| Minimal shell | `alpine:3.20` | ~7MB |
| No shell (most secure) | `gcr.io/distroless/static` | ~2MB |

### 3. Dependency layer optimization
- [ ] Copy lock files BEFORE source code
- [ ] Use `--no-cache-dir` (pip), `--omit=dev` (npm), `--no-install-recommends` (apt)
- [ ] Delete package manager caches in SAME RUN layer

```dockerfile
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*    # <-- same layer!
```

### 4. .dockerignore (prevents COPY bloat)
```
.git
node_modules
__pycache__
*.pyc
.env*
tests/
docs/
*.md
.vscode/
```

### 5. Reduce layer count
- [ ] Combine RUN commands with `&&`
- [ ] Use `--mount=type=cache` for package managers (BuildKit)
```dockerfile
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
```

### 6. Static compilation (Go)
```dockerfile
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /app .
# -s: strip symbol table, -w: strip DWARF — saves ~30%
```

### 7. UPX compression (optional, adds startup latency)
```dockerfile
RUN upx --best /app  # 50-70% smaller binary, slower cold start
```

## Verification commands
```bash
# Compare before/after
docker images | grep myapp

# Check what's inside
docker run --rm -it myapp:latest ls -la /
docker run --rm myapp:latest du -sh / 2>/dev/null

# Scan for unnecessary files
docker run --rm -it myapp:latest find / -name "*.pyc" -o -name "__pycache__" | wc -l
```

## Anti-patterns
- ❌ `apt-get update` and `rm -rf /var/lib/apt/lists/*` in separate RUN layers
- ❌ COPY . . before installing dependencies
- ❌ Using :latest tag for base images (unpredictable size)
- ❌ Installing build tools in runtime stage
- ❌ Leaving test files, docs, .git in image
