---
name: telemetry-helper
description: "Use when working on the StaffOps otel-libs monorepo — releasing new versions, understanding the .NET/Python helper API, or referring to sample apps for OTel instrumentation patterns."
---
# OTel Helper Libraries — Project Overview

Quick reference for the `otel-libs` monorepo (shared OpenTelemetry libraries for .NET and Python).

## When to use

- Working on the otel-libs repo (releasing, testing, adding instrumentation)
- Understanding the helper library API (`AddOtelHelper()` / `setup_telemetry()`)
- Looking for OTel instrumentation examples (sample apps cover 30+ patterns)
- Debugging telemetry in apps that use these libraries

## When NOT to use

- **Manual OTel SDK configuration** — use the helper library; don't re-implement what it provides
- **Collector/pipeline configuration** — see `otel-collector-multi-cluster` or `otel-pipeline-troubleshooting`
- **Metric catalog questions** — see `dotnet-apm-metrics` or `python-apm-metrics`

## Repository

**GitHub**: https://github.com/StaffOps/otel-libs

## Structure

```
otel-libs/
├── dotnet/                        # .NET lib: OtelHelper
│   ├── OtelHelper/                # Lib source
│   ├── OtelHelper.Tests/          # 61 tests, 90% coverage
│   └── example/
│       ├── dotnet-api/            # Minimal API (13 endpoints, gRPC client)
│       ├── dotnet-backend/        # gRPC server (5 RPCs)
│       └── dotnet-process/        # Worker (4 background services)
├── python/                        # Python lib: otel_helper
│   ├── otel_helper/               # Lib source
│   ├── tests/                     # 63 tests, 94% coverage
│   └── example/
│       ├── python-api/            # FastAPI (notification service)
│       ├── python-backend/        # gRPC server
│       └── python-process/        # Workers (queue, retry, cleanup)
└── dashboards/                    # Shared Grafana dashboards
```

## API entry points

| Language | Setup call | Min version |
|----------|-----------|-------------|
| .NET | `services.AddOtelHelper()` | net8.0 / net10.0 |
| Python | `setup_telemetry()` | Python 3.11+ (NOT 3.12) |

## Environment variables (both libs)

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVICE_NAME` | `my-service` | Service identity (priority 1) |
| `OTEL_SERVICE_NAME` | `my-service` | Fallback service name |
| `ENVIRONMENT` | `LOCAL` | Enum: LOCAL/DEV/HML/PRD/BTC |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-agent-collector.monitoring` | Collector endpoint |
| `OTEL_HELPER_DEBUG_LEVEL` | `false` | Force 100% sampling + debug spans |
| `OTEL_HELPER_EXTRA_INSTRUMENTATION` | `SQL` | Conditional: SQL, AWS, REDIS |
| `OTEL_HELPER_SAMPLE_RATIO` | `1.0` | Head sampling ratio (0.0-1.0) |

## Behavior by environment

```
LOCAL → log DEBUG, 100% sampling
DEV   → log INFO,  100% sampling
HML   → log INFO,  100% sampling
PRD   → log WARN,  100% sampling (tail-sampled at Collector)
BTC   → log WARN,  100% sampling (batch workloads)
```

## Sample apps — key patterns demonstrated

### .NET (13 API endpoints)

| Pattern | Endpoint |
|---------|----------|
| Distributed trace (API→gRPC→Backend) | `GET /order/{id}` |
| High latency simulation | `GET /slow` |
| Parallel fan-out (Task.WhenAll) | `GET /parallel/{count}` |
| Retry with span per attempt | `GET /retry/{id}` |
| Cache hit/miss with metrics | `GET /cache/{id}` |
| Baggage propagation + scoped logging | `GET /order/{id}/trace` |
| Span events (lifecycle) | `GET /order/{id}/events` |
| Exception → ERROR span | `GET /error` |
| StartRootActivity (workers) | Background services |

### Python (notification service)

| Pattern | Location |
|---------|----------|
| FastAPI + gRPC cross-service | `POST /notify` → gRPC backend |
| Queue consumer (independent traces) | `python-process/QueueConsumer` |
| Retry worker | `python-process/RetryWorker` |
| Health checker (StartRootActivity) | `python-process/HealthChecker` |

## Build commands

```bash
# .NET — test
docker run --rm -v $(pwd)/dotnet:/src -w /src mcr.microsoft.com/dotnet/sdk:8.0 dotnet test

# Python — test
docker run --rm -v $(pwd)/python:/app -w /app python:3.11-slim sh -c \
  "pip install -e '.[dev]' -q && pytest tests/ -v"
```

## CI pipeline (4 stages)

```
unit-test → build-dev → demo → build (manual)
```

Demo stage: builds dual-arch images → runs → curls endpoints → queries Tempo for traces → cleanup.

## Profiling status

**Stand-by.** Pyroscope SDK packages removed (compatibility issues). Will re-enable when OTel native Profiles signal reaches Beta/GA.

## Related skills

- `telemetry-standard` — the observability standard these libs implement
- `dotnet-otel-patterns` — advanced .NET patterns (StartRootActivity, debug processor)
- `python-otel-patterns` — Python-specific patterns (gRPC aio, FastAPI)
- `grpc-distributed-tracing` — cross-language gRPC context propagation
