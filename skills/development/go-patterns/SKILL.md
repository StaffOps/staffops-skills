---
name: go-patterns
description: "Write idiomatic Go services, context and gRPC."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [go, patterns, development]
    category: development
    related_skills: [go-apm-metrics]
---
# Go Patterns

Idioms and conventions for Go development at <org>.

## When to Use

Go idioms and patterns for <org> projects. Use when developing Go services (anomaly-detection-controller, future projects). Covers context propagation, error handling, gRPC patterns, testing, Docker builds, dependency management. Currently a baseline — will be expanded with project-specific patterns.

## Standard project layout

```
project-name/
├── cmd/
│   ├── server/main.go        # Main binary entry point
│   └── worker/main.go        # Worker binary
├── internal/                  # Private packages (not importable externally)
│   ├── config/
│   ├── handlers/
│   ├── repository/
│   └── service/
├── pkg/                       # Public packages (if shipping a lib)
├── proto/                     # gRPC proto definitions + generated code
│   ├── service.proto
│   ├── service.pb.go
│   └── service_grpc.pb.go
├── deploy/                    # K8s manifests, Helm values
├── Dockerfile
├── go.mod
├── go.sum
├── Makefile
└── README.md
```

Reference: `<workspace>/06-STAFFOPS/anomaly-detection-controller/`

## Build via Docker (no local Go SDK)

```bash
# Static binary (linux, no CGO — runs in alpine without libc issues)
docker run --rm -v $(pwd):/src -w /src golang:1.25-alpine sh -c \
  "CGO_ENABLED=0 go build -o bin/server ./cmd/server/"

# Tests
docker run --rm -v $(pwd):/src -w /src golang:1.25-alpine go test ./...

# With race detector (slower but catches data races)
docker run --rm -v $(pwd):/src -w /src golang:1.25-alpine go test -race ./...

# Coverage
docker run --rm -v $(pwd):/src -w /src golang:1.25-alpine sh -c \
  "go test -coverprofile=coverage.out ./... && go tool cover -func=coverage.out"
```

## Context propagation — ALWAYS first parameter

```go
// ✅ CORRECT
func (s *Service) ProcessOrder(ctx context.Context, id int) error {
    span := trace.SpanFromContext(ctx)
    span.SetAttributes(attribute.Int("order.id", id))

    rows, err := s.db.QueryContext(ctx, "SELECT ...", id)  // pass ctx
    if err != nil {
        return fmt.Errorf("query order %d: %w", id, err)
    }
    defer rows.Close()
    return nil
}

// ❌ WRONG — ctx not passed, cancellation/tracing broken
func (s *Service) ProcessOrder(id int) error {
    rows, err := s.db.Query("SELECT ...", id)  // no ctx
    // ...
}
```

## Error handling — wrap with context

```go
// ✅ CORRECT — caller can unwrap to get original error
if err != nil {
    return fmt.Errorf("processing order %d: %w", id, err)
}

// ❌ WRONG — loses error type, can't errors.Is/As
if err != nil {
    return fmt.Errorf("processing order %d: %s", id, err)  // %s not %w
}
```

### Sentinel errors

```go
var (
    ErrNotFound = errors.New("not found")
    ErrConflict = errors.New("conflict")
)

// Caller
if errors.Is(err, ErrNotFound) {
    return c.NoContent(http.StatusNotFound)
}
```

## gRPC server — standard setup

```go
import (
    "google.golang.org/grpc"
    "google.golang.org/grpc/health"
    "google.golang.org/grpc/health/grpc_health_v1"
    "go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
)

func NewServer() *grpc.Server {
    s := grpc.NewServer(
        grpc.StatsHandler(otelgrpc.NewServerHandler()),  // OTel instrumentation
    )
    pb.RegisterMyServiceServer(s, &myServiceImpl{})

    // Health check
    healthSrv := health.NewServer()
    grpc_health_v1.RegisterHealthServer(s, healthSrv)
    healthSrv.SetServingStatus("", grpc_health_v1.HealthCheckResponse_SERVING)

    return s
}
```

## gRPC client — standard setup

```go
import (
    "google.golang.org/grpc"
    "google.golang.org/grpc/credentials/insecure"
    "go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
)

conn, err := grpc.NewClient(
    target,
    grpc.WithTransportCredentials(insecure.NewCredentials()),
    grpc.WithStatsHandler(otelgrpc.NewClientHandler()),
)
```

**Note**: `grpc.NewClient` is preferred over `grpc.Dial` (deprecated). However, <org>'s anomaly-detection still uses `grpc.Dial` (v1.62.1) — needs migration.

## Proto regeneration

```bash
docker run --rm -v $(pwd):/src -w /src golang:1.25-alpine sh -c "
apk add --no-cache protobuf &&
go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.33.0 &&
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.3.0 &&
export PATH=\$PATH:\$(go env GOPATH)/bin &&
protoc --go_out=. --go_opt=paths=source_relative \
       --go-grpc_out=. --go-grpc_opt=paths=source_relative \
       proto/service.proto"
```

## Testing patterns

### Table-driven tests

```go
func TestParseConfig(t *testing.T) {
    tests := []struct {
        name    string
        input   string
        want    *Config
        wantErr bool
    }{
        {"valid", `{"port": 8080}`, &Config{Port: 8080}, false},
        {"empty", ``, nil, true},
        {"invalid", `not json`, nil, true},
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got, err := ParseConfig(tt.input)
            if (err != nil) != tt.wantErr {
                t.Fatalf("err = %v, wantErr %v", err, tt.wantErr)
            }
            if !reflect.DeepEqual(got, tt.want) {
                t.Errorf("got %+v, want %+v", got, tt.want)
            }
        })
    }
}
```

### Test fixtures via testdata/

```
internal/parser/
├── parser.go
├── parser_test.go
└── testdata/
    ├── valid.json
    └── invalid.json
```

## Dependency management

```bash
# Add a dependency
docker run --rm -v $(pwd):/src -w /src golang:1.25-alpine go get github.com/foo/bar

# Update all
docker run --rm -v $(pwd):/src -w /src golang:1.25-alpine go get -u ./...

# Tidy go.mod / go.sum
docker run --rm -v $(pwd):/src -w /src golang:1.25-alpine go mod tidy
```

## Standard dependencies at <org> (Go 1.25)

| Module | Version | Purpose |
|--------|---------|---------|
| `google.golang.org/grpc` | v1.62.1 | gRPC |
| `github.com/prometheus/client_golang` | v1.19.0 | Prometheus metrics |
| `github.com/redis/go-redis/v9` | v9.5.1 | Redis client |
| `github.com/sony/gobreaker` | v1.0.0 | Circuit breaker |
| `github.com/google/uuid` | v1.6.0 | UUIDs |
| `k8s.io/client-go` | v0.29.4 | K8s API |
| `gopkg.in/yaml.v3` | v3.0.1 | YAML parsing |
| `google.golang.org/protobuf` | v1.33.0 | Proto serialization |

## Dockerfile pattern (multi-stage)

```dockerfile
# Build stage
FROM golang:1.25-alpine AS builder
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /out/server ./cmd/server/

# Runtime stage
FROM alpine:3.20
RUN apk add --no-cache ca-certificates
COPY --from=builder /out/server /usr/local/bin/server
ENTRYPOINT ["/usr/local/bin/server"]
```

## Concurrency patterns

### Worker pool with errgroup

```go
import "golang.org/x/sync/errgroup"

func processBatch(ctx context.Context, items []Item) error {
    g, ctx := errgroup.WithContext(ctx)
    g.SetLimit(10)  // Max 10 concurrent

    for _, item := range items {
        item := item  // capture for closure
        g.Go(func() error {
            return processItem(ctx, item)
        })
    }

    return g.Wait()
}
```

### Cancellation propagation

Always respect `ctx.Done()` in long-running operations:
```go
select {
case <-ctx.Done():
    return ctx.Err()
case result := <-resultCh:
    return result
}
```


## Decision tree

```
Go design choice
├── Error handling pattern?
│   ├── Caller can handle/retry → return error (don't panic)
│   ├── Unrecoverable (nil config at startup) → log.Fatal / panic in main only
│   ├── Need to add context → fmt.Errorf("doing X: %w", err) (wrap, don't shadow)
│   └── Multiple possible errors → use sentinel errors (errors.Is) or typed errors (errors.As)
├── Context propagation?
│   ├── HTTP handler → use r.Context(); pass down to every I/O call
│   ├── gRPC → ctx comes as first arg; propagate to sub-calls
│   ├── Background goroutine → derive new context or use context.WithoutCancel (Go 1.21+)
│   └── Timeout needed → context.WithTimeout; defer cancel() immediately
└── Concurrency pattern?
    ├── N independent tasks, wait for all → errgroup.Group
    ├── Producer/consumer pipeline → channels (buffered) + goroutines
    ├── Shared state, rare writes → sync.RWMutex
    └── One-time init → sync.Once
```

## When NOT to use

- Python service development — use `python-fastapi-patterns` or `python-grpc-aio`
- .NET service development — use `dotnet-async-patterns`
- Go-specific OTel integration — patterns are here, but for cross-language tracing use `grpc-distributed-tracing`

## Related skills

- `grpc-distributed-tracing` — cross-language gRPC tracing involving Go services
- `python-grpc-aio` — the Python counterpart for gRPC async servers
- `dotnet-async-patterns` — .NET equivalent for async workers and channels
- `mcp-server-development` — building MCP servers (Go or Python)

## Anti-patterns

- ❌ Goroutine leaks (no defer wg.Done(), no ctx cancellation)
- ❌ `panic()` for expected errors (use error returns)
- ❌ Global mutable state
- ❌ Public structs without tests
- ❌ `interface{}` everywhere (use generics in Go 1.18+ or specific types)
- ❌ `init()` for non-trivial setup (hard to test, hidden dependencies)
- ❌ Importing `internal/` packages from external module (compiler will complain anyway)

## Project examples at <org>

- `06-STAFFOPS/anomaly-detection-controller/` — Production-grade Go service (controller + worker, 13 internal packages, gRPC fan-out, Redis-backed baseline, K8s integration)

## Reference

- Effective Go: https://go.dev/doc/effective_go
- Local docs: (none cached yet for Go — search go.dev directly)
- Related skills: `grpc-distributed-tracing`, `telemetry-standard` (covers Go OTel via standard SDK, no <org> wrapper for Go yet)

## Roadmap for this skill

- [ ] Add <org> Go OTel helper if/when developed
- [ ] Add specific patterns from anomaly-detection-controller (circuit breaker, rate limiter, query cache)
- [ ] Add CI/CD patterns (versioning, image signing, multi-arch)
- [ ] Add metrics/profiling patterns (pprof endpoint, runtime metrics)
