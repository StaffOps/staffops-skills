---
name: grpc-distributed-tracing
description: "Propagate trace context across gRPC languages."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [grpc, distributed, tracing, development]
    category: development
    related_skills: [python-grpc-aio]
---
# gRPC Distributed Tracing

How to make gRPC traces work end-to-end across .NET, Python, Go services in the <org> stack.

## When to Use

Cross-language gRPC distributed tracing patterns. Use when designing gRPC services that need end-to-end traces across .NET, Python, Go. Covers context propagation via metadata, instrumentation by language, Istio Ambient gotchas, debugging missing spans.

## How gRPC propagation works

OpenTelemetry uses W3C Trace Context propagation:

```
Client                              Server
------                              ------
Build span                          Receive metadata
Inject traceparent into             Extract traceparent
  gRPC metadata                     Create child span with parent
Send RPC ────────────────────────►  Process RPC
                                    Reply
Receive reply                       ◄─────────────────────────
End span                            End span
```

The key piece is the gRPC metadata (HTTP/2 headers):
```
traceparent: 00-<trace_id>-<span_id>-<flags>
tracestate: <state>
```

## Instrumentation by language

### .NET — automatic via lib

```csharp
services.AddOtelHelper();  // Includes OpenTelemetry.Instrumentation.GrpcNetClient 1.15.1-beta.1
```

For client (gRPC.Net.Client): traces injected automatically.
For server: gRPC over ASP.NET Core, so `OpenTelemetry.Instrumentation.AspNetCore` handles it.

```csharp
// Client
var channel = GrpcChannel.ForAddress("http://backend:5100");
var client = new OrderService.OrderServiceClient(channel);
var reply = await client.ProcessOrderAsync(request);  // traceparent injected automatically

// Server (ASP.NET Core hosting gRPC)
app.MapGrpcService<OrderGrpcService>();
```

Span attributes set automatically:
- `rpc.system=grpc`
- `rpc.service=order.OrderService`
- `rpc.method=ProcessOrder`
- `rpc.grpc.status_code=0`

### Python — must use Aio variants

```python
from opentelemetry.instrumentation.grpc import (
    GrpcAioInstrumentorClient,
    GrpcAioInstrumentorServer,
)

# In setup_telemetry() (otel_helper does this):
GrpcAioInstrumentorClient().instrument()  # patches grpc.aio.insecure_channel
GrpcAioInstrumentorServer().instrument()  # patches grpc.aio.server
```

After this, no manual interceptors needed. ALL grpc.aio channels and servers are instrumented.

**Wrong**: `GrpcInstrumentorClient` (sync — only patches `grpc.insecure_channel`).

### Go — via otelgrpc

```go
import (
    "go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
    "google.golang.org/grpc"
)

// Server
s := grpc.NewServer(
    grpc.StatsHandler(otelgrpc.NewServerHandler()),
)

// Client
conn, err := grpc.NewClient(
    target,
    grpc.WithStatsHandler(otelgrpc.NewClientHandler()),
)
```

`StatsHandler` is the modern API (replaces deprecated `UnaryInterceptor` + `StreamInterceptor`).

## Verified end-to-end pattern (<org> sample apps)

```
python-process (Worker)
  HTTP :8000 with traceparent header (via inject)
  ↓
python-api (FastAPI) — extracts traceparent via FastAPIInstrumentor
  gRPC :50051 with traceparent in metadata (via GrpcAioInstrumentorClient)
  ↓
python-backend — extracts via GrpcAioInstrumentorServer
```

In Tempo, this shows as ONE trace spanning 3 services with proper parent-child relationships.

## Istio Ambient mesh impact

### Service port name MUST be `grpc`

```yaml
# ✅ CORRECT
apiVersion: v1
kind: Service
spec:
  ports:
    - name: grpc      # Istio waypoint handles HTTP/2 correctly
      port: 50051
      targetPort: 50051
```

```yaml
# ❌ WRONG — waypoint treats as HTTP/1.1
apiVersion: v1
kind: Service
spec:
  ports:
    - name: http
      port: 50051
```

With `name: http`, waypoint returns `400 Bad Request` to gRPC frames.

### Alternative: appProtocol

```yaml
spec:
  ports:
    - name: my-port
      port: 50051
      appProtocol: grpc
```

### .NET Kestrel — AllowAlternateSchemes

When gRPC backend runs behind Istio (waypoint terminates TLS):

```csharp
builder.WebHost.ConfigureKestrel(options =>
{
    options.AllowAlternateSchemes = true;
});
```

Without this, Kestrel rejects the `:scheme` mismatch on HTTP/2 (returns 400).

## Spanmetrics — RED metrics from gRPC traces

The OTel Collector with `spanmetrics` connector generates metrics from spans:

```
spanmetrics_apm_calls_total{rpc_system="grpc", rpc_service="order.OrderService", rpc_method="ProcessOrder"}
spanmetrics_apm_duration_milliseconds_bucket{...}
```

These power dashboards even WITHOUT direct metric instrumentation in the app.

## Debugging missing gRPC spans

### Issue: client span exists but server span missing

Causes:
1. **Server not instrumented** — verify `GrpcAioInstrumentorServer().instrument()` (Python) or `StatsHandler` (Go)
2. **Different OTel SDK versions** mismatch propagation format (rare)
3. **Istio waypoint rejecting** — check pod logs for 400 errors

### Issue: server span exists but no parent

Causes:
1. Client didn't inject traceparent (instrumentation broken)
2. Service mesh stripped headers (rare, but possible)
3. Custom interceptor removing metadata

Test:
```bash
# From client pod, manually inject traceparent
grpcurl -H "traceparent: 00-1234567890abcdef1234567890abcdef-1234567890abcdef-01" \
  backend:50051 service.Method
```

If this creates a span, propagation logic is OK; client lib not injecting.

### Issue: traces broken at .NET/Python boundary

Verify both sides use compatible OTel SDK versions. .NET's `OpenTelemetry.Instrumentation.GrpcNetClient` is currently `1.15.1-beta.1` (no stable yet). Python's `opentelemetry-instrumentation-grpc` is `0.63b1`.

Despite "beta" tags, propagation is W3C compliant — works across languages.

## Health check patterns

### gRPC standard health protocol

All <org> gRPC services should implement `grpc.health.v1.Health`:

| Language | Package | Usage |
|----------|---------|-------|
| .NET | `Grpc.HealthCheck` | `services.AddSingleton<HealthServiceImpl>()` |
| Python | `grpcio-health-checking` | `health_pb2_grpc.add_HealthServicer_to_server` |
| Go | built-in `grpc/health` | `grpc_health_v1.RegisterHealthServer` |

### Filtering health spans

Health checks generate noise. Filter at OTel Collector:

```yaml
filter/span-noise:
  traces:
    span:
      - resource.attributes["service.name"] == "<service>" and name == "/grpc.health.v1.Health/Check"
```

## .NET — separating traces by operation

In sample apps, EACH endpoint creates a uniquely named root span:

| HTTP endpoint | Span name | gRPC backend call |
|---------------|-----------|-------------------|
| GET /order/{id} | `api.get-order` | → grpc.client → backend.process-order |
| POST /order | `api.create-order` | → grpc.client → backend.process-order |
| GET /slow | `api.slow-operation` | → grpc.client → backend.slow-operation |

This makes Tempo searches more useful (`rootTraceName=api.get-order`).

## Proto file sharing

For monorepos with multiple services sharing a proto:

```
example/
├── Protos/
│   └── order.proto              # Single source of truth
├── OtelHelper.SampleApi/     # gRPC client
│   └── OtelHelper.SampleApi.csproj  # references ../Protos/order.proto
└── OtelHelper.SampleBackend/ # gRPC server
    └── OtelHelper.SampleBackend.csproj  # references ../Protos/order.proto
```

Both projects use MSBuild `<Protobuf>` items. No need for separate proto package.

For Python: similar pattern, generate code via `python -m grpc_tools.protoc` from each project (or generate to a shared dir).

## Common configuration

| Property | Recommended |
|----------|-------------|
| HTTP/2 | Required for gRPC (no HTTP/1.1 fallback) |
| Backend Kestrel | HTTP/2 only on the gRPC port |
| Client channel | Singleton (channels are expensive to create) |
| Client stub | Scoped per request (lightweight) |
| Health check | Mandatory in production |

## Reference

- OTel gRPC docs (.NET): https://opentelemetry.io/docs/languages/dotnet/instrumentation/#grpc
- OTel gRPC docs (Python): https://opentelemetry.io/docs/languages/python/instrumentation/#grpc
- otelgrpc (Go): https://pkg.go.dev/go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc
- Local docs: `<workspace>/01-DEVOPS/EXTERNAL-DOCS/opentelemetry.io/content/en/docs/languages/`
- Related skills: `dotnet-otel-patterns`, `python-otel-patterns`, `go-patterns`, `istio-ambient-otel`

## When NOT to use

- Language-specific async/concurrency patterns — use `dotnet-async-patterns`, `python-grpc-aio`, or `go-patterns`
- OTel Collector pipeline configuration — use `otel-collector-multi-cluster`
- Istio ambient mesh trace propagation — use `istio-ambient-debugging`

## Related skills

- `dotnet-otel-patterns` — .NET-specific span management and `StartRootActivity`
- `python-otel-patterns` — Python-specific `GrpcAioInstrumentor` patterns
- `go-patterns` — Go gRPC interceptors and context propagation
- `python-grpc-aio` — building the async Python gRPC server that carries traces
- `istio-ambient-otel` — mesh-level trace propagation through ztunnel
