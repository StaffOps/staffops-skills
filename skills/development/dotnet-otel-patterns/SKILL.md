---
name: dotnet-otel-patterns
description: "Instrument .NET workers, spans and debug tracing."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [dotnet, otel, patterns, development]
    category: development
    related_skills: [istio-ambient-otel, dotnet-apm-metrics, python-otel-patterns, dotnet-async-patterns]
---
# .NET OpenTelemetry Patterns

Advanced patterns for .NET applications using <org> OTel Helper.

## When to Use

Advanced .NET OpenTelemetry patterns. Use when implementing background workers, debug mode, custom span processors, or distributed tracing with gRPC. Covers StartRootActivity (independent traces in workers), DebugTraceStateProcessor, baggage, retry/cache/parallel patterns, and Istio Ambient + Kestrel gotchas.

## StartRootActivity — independent traces in workers

### Problem

In background workers, `Activity.Current` persists between loop iterations. Without clearing, new spans become children of the previous iteration's span — creating one massive trace per worker instead of one per cycle.

### Solution

```csharp
public static class ActivitySourceExtensions
{
    public static Activity? StartRootActivity(this ActivitySource source, string name)
    {
        Activity.Current = null;
        return source.StartActivity(name);
    }
}
```

### Usage

```csharp
public class QueueConsumerWorker(ActivitySource activity) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            using var span = activity.StartRootActivity("queue.consume");
            // Each iteration is a NEW trace (new traceId, no parent)
            await ProcessMessage();
            await Task.Delay(TimeSpan.FromSeconds(30), ct);
        }
    }
}
```

### Why not `new ActivityContext(CreateRandom(), CreateRandom(), Recorded)`?

This creates a **phantom parent** — the span has a `parentSpanId` pointing to a span that doesn't exist. In Tempo:
```
rootServiceName: <root span not yet received>
```

The correct approach is `Activity.Current = null` before `StartActivity()` — produces a true root with no `parentSpanId`.

## DebugTraceStateProcessor — force 100% sampling

When `OTEL_HELPER_DEBUG_LEVEL=true`, the lib injects:
- `tracestate: debug=true` on root spans
- Span attribute `debug=true` on root spans

The Collector tail_sampling has matching policies:
```yaml
- name: debug-forced
  type: trace_state
  trace_state:
    key: debug
    values: ["true"]
- name: debug-forced-attribute  # for Python (which can't modify tracestate)
  type: string_attribute
  string_attribute:
    key: debug
    values: ["true"]
```

### Anti-abuse: strip debug from external clients

```yaml
transform/strip-external-debug:
  trace_statements:
    - context: span
      conditions:
        - resource.attributes["eks_cluster"] == nil
      statements:
        - replace_pattern(trace_state["debug"], "true", "")
```

External clients can't force 100% sampling — only spans with `eks_cluster` resource attr keep the debug flag.

### Implementation in lib

```csharp
public class DebugTraceStateProcessor : BaseProcessor<Activity>
{
    public override void OnStart(Activity data)
    {
        if (data.Parent != null) return;  // Only root spans

        // Add to tracestate
        var existing = data.TraceStateString ?? string.Empty;
        if (!existing.Contains("debug="))
        {
            data.TraceStateString = string.IsNullOrEmpty(existing)
                ? "debug=true"
                : $"{existing},debug=true";
        }

        // Add as attribute (for Python compatibility & dashboards)
        data.SetTag("debug", true);
    }
}
```

## Health endpoint filtering

### ASP.NET Core inbound (already in <org> lib)
```csharp
.AddAspNetCoreInstrumentation(options =>
{
    options.Filter = ctx =>
        !ctx.Request.Path.StartsWithSegments("/health");
})
```

### HttpClient outbound
```csharp
.AddHttpClientInstrumentation(options =>
{
    options.FilterHttpRequestMessage = req =>
        !req.RequestUri?.AbsolutePath.StartsWith("/health") ?? true;
})
```

## RecordException

Enable on all instrumentations to capture exceptions as span events:

```csharp
.AddAspNetCoreInstrumentation(o => o.RecordException = true)
.AddHttpClientInstrumentation(o => o.RecordException = true)
.AddSqlClientInstrumentation(o => o.RecordException = true)
```

In Tempo, exceptions appear as span events with stack trace + exception type.

## ParseStateValues for structured logs

```csharp
builder.Logging.AddOpenTelemetry(logging =>
{
    logging.ParseStateValues = true;
});
```

Enables structured log placeholders to become attributes:
```csharp
_logger.LogInformation("Order {OrderId} processed in {DurationMs}ms", orderId, duration);
// → Log record attributes: OrderId="123", DurationMs="42"
```

Without `ParseStateValues = true`, only the formatted message is sent.

## Filter noisy frameworks in non-debug

```csharp
.AddFilter("Microsoft.*", LogLevel.Error)
.AddFilter("System.Net.Http.*", LogLevel.Error)
```

In non-debug mode, frameworks' INFO/WARN logs flood Loki without value. Already in <org> lib.

## DI registration of ActivitySource and Meter

The lib registers as singletons (consumers inject directly):

```csharp
// In lib's AddOtelHelper:
services.AddSingleton(_ => new ActivitySource(serviceName));
services.AddSingleton(_ => new Meter(serviceName));

// In your code:
public class OrderService(ActivitySource activity, Meter meter)
{
    private readonly Counter<long> _orderCount = meter.CreateCounter<long>("orders.received");

    public async Task ProcessOrder(int id)
    {
        using var span = activity.StartActivity("order.process");
        span?.SetTag("order.id", id);
        _orderCount.Add(1);
        // ...
    }
}
```

## gRPC + Istio Ambient — Kestrel `AllowAlternateSchemes`

When gRPC services run behind Istio Ambient mesh, the waypoint terminates TLS and forwards HTTP. Kestrel rejects the resulting `:scheme` mismatch for HTTP/2 (gRPC).

Fix:
```csharp
builder.WebHost.ConfigureKestrel(options =>
{
    options.AllowAlternateSchemes = true;
});
```

Without this, gRPC calls return `400 Bad Request` from the backend behind Istio.

## Service port name for gRPC

In Kubernetes Service for gRPC backends, the port `name` MUST be `grpc`:

```yaml
apiVersion: v1
kind: Service
spec:
  ports:
    - name: grpc        # ✅ Istio waypoint handles HTTP/2 correctly
      port: 5100
      targetPort: 5100
```

With `name: http`, waypoint treats traffic as HTTP/1.1 → returns 400 for gRPC frames.

## Advanced patterns demonstrated in sample apps

| Endpoint | Pattern | Span names |
|----------|---------|------------|
| GET /order/{id}/trace | Baggage propagation | `api.trace-with-baggage` |
| GET /order/{id}/events | Span events (4 lifecycle events) | `api.order-with-events` |
| GET /parallel/{count} | Parallel fan-out (Task.WhenAll) | `api.parallel-fan-out` |
| GET /retry/{id} | Retry with span per attempt | `api.retry-operation` |
| GET /cache/{id} | Cache hit/miss with metrics | `api.cache-lookup` |
| GET /batch | Sequential fan-out | `api.batch-orders` + `api.batch-item` |

## Spanmetrics naming (OTel → Prometheus)

OTel SDK uses dots: `orders.received_total`
Prometheus/VictoriaMetrics converts: `orders_received_total`

`resource_metrics_key_attributes: [service.name]` makes `service_name` available as label in derived spanmetrics.

## Common issues

### Issue: `rootServiceName: <root span not yet received>` in Tempo
Cause: phantom parent (using `new ActivityContext(...)` instead of clearing Activity.Current).
Fix: use `StartRootActivity()` extension method.

### Issue: gRPC backend returns 400 from Istio
Cause: `AllowAlternateSchemes = false` (default) + waypoint scheme mismatch.
Fix: enable `AllowAlternateSchemes = true` in Kestrel config.

### Issue: structured log fields missing in Loki
Cause: `ParseStateValues = false` (default).
Fix: enable in `AddOpenTelemetry(logging => logging.ParseStateValues = true)`.

### Issue: traces from worker have one massive trace per pod
Cause: not clearing `Activity.Current` between iterations.
Fix: use `StartRootActivity()` per cycle.

## Testing

The lib has 61 tests with 90% line coverage. Standard test pattern:

```bash
docker run --rm -v $(pwd):/src -w /src mcr.microsoft.com/dotnet/sdk:8.0 dotnet test
```

## Reference

- <org> OTel Helper monorepo: `<workspace>/01-DEVOPS/LABS/otel-telemetry-helper/`
- Sample apps with all patterns: `otel-telemetry-helper/dotnet/example/`
- OTel .NET docs: `<workspace>/01-DEVOPS/EXTERNAL-DOCS/opentelemetry.io/content/en/docs/languages/dotnet/`
- Related skills: `telemetry-standard`, `grpc-distributed-tracing`, `python-otel-patterns`


## Decision tree

```
Which telemetry signal?
├── Traces
│   ├── Background worker / cron? → StartRootActivity (independent trace)
│   ├── Need to force-sample one request? → DebugTraceStateProcessor
│   ├── Pass business context across services? → Baggage
│   ├── Catch & record exception in span? → RecordException + SetStatus
│   └── Retry / parallel / cache spans? → child Activity under current
├── Metrics
│   ├── Counter (monotonic)? → Meter.CreateCounter<T>
│   ├── Gauge (current value)? → Meter.CreateObservableGauge
│   ├── Distribution (latency)? → Meter.CreateHistogram + Exemplars
│   └── Metric→Trace link? → .SetExemplarFilter(TraceBased)
└── Logs
    ├── Structured log with trace context? → ILogger (OTel bridges auto)
    └── Filter noisy health-check logs? → AddFilter / endpoint filter
```

## When NOT to use

- Python OTel instrumentation — use `python-otel-patterns`
- Collector pipeline configuration (not SDK) — use `otel-collector-multi-cluster`
- Cross-language gRPC trace propagation design — use `grpc-distributed-tracing`

## Related skills

- `python-otel-patterns` — equivalent OTel patterns for Python services
- `grpc-distributed-tracing` — cross-language trace context propagation
- `dotnet-async-patterns` — async code that the OTel spans wrap
- `telemetry-standard` — corporate OTel helper library that applies these patterns
