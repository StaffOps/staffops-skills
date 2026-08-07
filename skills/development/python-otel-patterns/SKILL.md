---
name: python-otel-patterns
description: "Instrument Python traces, metrics and logs."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, otel, patterns, development]
    category: development
    related_skills: [python-grpc-aio, python-apm-metrics, istio-ambient-otel, dotnet-otel-patterns]
---
# Python OpenTelemetry Patterns

Python-specific patterns for `otel_helper` library at <org>.

## When to Use

Python OpenTelemetry patterns. Use when integrating telemetry into FastAPI, gRPC aio, or asyncio workers. Covers GrpcAioInstrumentor monkey-patching, FastAPIInstrumentor.instrument_app, Python 3.11 vs 3.12 pkg_resources issue, manual context propagation in async code, start_root_span pattern.

## Critical: Python 3.11, NOT 3.12

OTel instrumentation libraries depend on `pkg_resources` (from setuptools), which is broken/removed in Python 3.12.

```dockerfile
FROM python:3.11-slim   # ✅ Use this
# FROM python:3.12-slim  # ❌ Breaks OTel instrumentations
```

## Setup must be in `main()`, not module level

```python
# ❌ WRONG — silent failure if env not configured
from otel_helper import setup_telemetry
setup_telemetry()  # at module level

class App:
    pass
```

```python
# ✅ CORRECT
from otel_helper import setup_telemetry

def main():
    setup_telemetry()  # raises ValueError if config invalid
    # ... start app

if __name__ == "__main__":
    main()
```

`setup_telemetry()` raises `ValueError` with prefix `[<org> Telemetry]` for config errors. Module-level call swallows the error during import.

## FastAPI instrumentation

### Use `instrument_app(app)`, not `instrument()`

```python
# ❌ WRONG — only works for apps created AFTER this call
FastAPIInstrumentor().instrument()
app = FastAPI()  # not instrumented!

# ✅ CORRECT — instruments existing app
app = FastAPI()
FastAPIInstrumentor.instrument_app(app)
```

The `otel_helper` lib doesn't auto-instrument FastAPI (would require knowing about your `app` instance). Call `instrument_app(app)` after creating it.

## gRPC — use Aio variants (<org> standard)

The `GrpcInstrumentorClient/Server` only patches sync `grpc.insecure_channel`. For modern asyncio gRPC, use:

```python
from opentelemetry.instrumentation.grpc import (
    GrpcAioInstrumentorClient,
    GrpcAioInstrumentorServer,
)

GrpcAioInstrumentorClient().instrument()  # patches grpc.aio.insecure_channel
GrpcAioInstrumentorServer().instrument()  # patches grpc.aio.server
```

The `otel_helper` lib calls these automatically in `setup_telemetry()`. After setup, consumers don't need manual interceptors.

### Verified context propagation

```
process → api: via inject(headers) + FastAPIInstrumentor extracts traceparent
api → backend: via GrpcAioInstrumentorClient (auto injects metadata)
backend receives: via GrpcAioInstrumentorServer (auto extracts metadata)
```

3-service distributed traces work end-to-end in Tempo with this setup.

## Manual context propagation for HTTP clients (workers)

For workers calling APIs directly (no auto-instrumented framework):

```python
from opentelemetry import context, propagate
from opentelemetry.trace import get_current_span

async def call_api(url: str, payload: dict):
    headers = {}
    propagate.inject(headers, context=context.get_current())  # CRITICAL: explicit context
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
    return response
```

`propagate.inject(headers)` injects `traceparent` and `tracestate` into the dict.

**Why explicit context**: in async code, the implicit context can be lost if `inject(headers)` is called outside the active span's `start_as_current_span` block.

## start_root_span — independent traces in workers

```python
from otel_helper import start_root_span

async def queue_consumer():
    while True:
        with start_root_span("queue.consume") as span:
            span.set_attribute("queue.name", "notifications")
            await process_message()
        await asyncio.sleep(30)
```

Each iteration is an independent trace (new traceId, no parent). Same purpose as .NET's `StartRootActivity` — prevents trace pollution between worker cycles.

## DebugProcessor — span attribute (no tracestate)

Python's OpenTelemetry SDK can't modify `tracestate` after span creation. So `otel_helper` only sets:
- Span attribute `debug=true` on root spans

The Collector needs a matching policy:
```yaml
- name: debug-forced-attribute
  type: string_attribute
  string_attribute:
    key: debug
    values: ["true"]
```

(.NET sets BOTH tracestate AND attribute — Collector handles both.)

## System metrics

Auto-enabled via `SystemMetricsInstrumentor`:
- CPU usage, memory, network I/O
- Python GC stats (collections by generation)

Available via `process.runtime.cpython.*` and `system.*` metrics in VictoriaMetrics.

## OTel internal logs filtering

In non-debug mode, the lib filters OTel internal logger to WARNING:

```python
logging.getLogger("opentelemetry").setLevel(logging.WARNING)
```

Without this, OTel's own info logs flood stdout.

## Validation with `[<org> Telemetry]` prefix

```python
def setup_telemetry():
    if not service_name:
        raise ValueError("[<org> Telemetry] SERVICE_NAME env var required")
    # ... etc
```

Easy to grep in logs:
```bash
kubectl logs -n monitoring deploy/python-api | grep "<org> Telemetry"
```

## Health endpoint filter (HTTPX/requests)

The lib filters outbound HTTP calls to `/health` paths automatically (similar to .NET).

## Sample apps — Notification Service

Located at `<workspace>/01-DEVOPS/LABS/otel-telemetry-helper/python/example/`:

```
python-process (Worker)
  ├── QueueConsumer (30s interval)
  ├── RetryWorker (60s)
  ├── CleanupWorker (3min)
  └── HealthChecker (1min)
         │ HTTP :8000 (with traceparent header)
         ▼
python-api (FastAPI :8000)
  ├── POST /notify         → calls backend via gRPC
  ├── GET /notify/{id}     → status check
  ├── GET /templates       → list templates
  └── GET /health
         │ gRPC :50051
         ▼
python-backend (gRPC :50051)
  ├── SendNotification     → render + deliver (email/sms/push)
  ├── GetStatus
  └── RenderTemplate
```

## Health checks per service type

| Service | Type | Endpoint |
|---------|------|----------|
| python-api | HTTP | `GET /health` (port 8000) |
| python-backend | gRPC | `grpc.health.v1.Health/Check` (port 50051) |
| python-process | HTTP | `GET /healthz` (port 8080, via aiohttp) |

For gRPC health check:
```python
from grpc_health.v1 import health_pb2, health_pb2_grpc

# Server side
health_servicer = health.HealthServicer()
health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
```

## Versioning — PEP 440 (numeric only dev suffix)

```toml
# pyproject.toml
[project]
dynamic = ["version"]

[tool.hatch.version]
path = "otel_helper/__init__.py"
```

`__init__.py`:
```python
__version__ = "0.1.0"  # release
# or for CI dev: "0.1.0.dev<CI_PIPELINE_ID>"
```

**Critical**: PEP 440 dev suffix is numeric only. NO commit SHA. Use `CI_PIPELINE_ID`.

## Common issues

### Issue: traces from process worker not appearing in Tempo
Causes:
1. `setup_telemetry()` called at module level (silent fail)
2. Missing `inject(headers)` in HTTP calls
3. Wrong instrumentor (`GrpcInstrumentorClient` instead of `GrpcAioInstrumentorClient`)

### Issue: `pkg_resources` ModuleNotFoundError
Cause: Python 3.12 base image
Fix: use `python:3.11-slim`

### Issue: FastAPI requests not traced
Cause: `FastAPIInstrumentor().instrument()` called BEFORE app creation
Fix: use `FastAPIInstrumentor.instrument_app(app)` after `app = FastAPI()`

### Issue: traceparent header not propagated to backend
Cause: `inject(headers)` without `context=context.get_current()` — async context lost
Fix: pass explicit context

### Issue: gRPC server doesn't show traces
Cause: missing `GrpcAioInstrumentorServer().instrument()` (lib should call this in setup_telemetry)
Fix: verify `setup_telemetry()` called before `grpc.aio.server()`

## Testing

63 tests, 94% coverage. Run:
```bash
docker run --rm -v $(pwd):/app -w /app python:3.11-slim sh -c \
  "pip install -e '.[dev]' -q && pytest tests/ -v"
```

## Reference

- Lib source: `<workspace>/01-DEVOPS/LABS/otel-telemetry-helper/python/otel_helper/`
- Examples: `otel-telemetry-helper/python/example/`
- OTel Python docs: `<workspace>/01-DEVOPS/EXTERNAL-DOCS/opentelemetry.io/content/en/docs/languages/python/`
- Related skills: `telemetry-standard`, `grpc-distributed-tracing`, `dotnet-otel-patterns`
