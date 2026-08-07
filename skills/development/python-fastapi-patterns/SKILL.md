---
name: python-fastapi-patterns
description: "Build FastAPI services, deps and validation."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, fastapi, patterns, development]
    category: development
    related_skills: [python-grpc-aio, python-apm-metrics, python-otel-patterns]
---
# Python FastAPI Patterns

FastAPI patterns for <org> Python services. Reference implementation: `otel-telemetry-helper/python/example/python-api/`.

## When to Use

Use when building FastAPI services, configuring middleware, async DB access, or testing API endpoints. Covers routers, dependencies, lifespan, Pydantic v2, background tasks, auth patterns, and <org> python-api integration with OTel.

## Critical: Python 3.11, NOT 3.12

```dockerfile
FROM python:3.11-slim   # ✅
# FROM python:3.12-slim  # ❌ Breaks OTel instrumentations (pkg_resources)
```

## Application structure

### Lifespan (startup/shutdown)

Use the `lifespan` context manager (FastAPI 0.93+) instead of deprecated `on_event`:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from otel_helper import setup_telemetry

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_telemetry()  # OTel MUST be configured before requests
    await init_db_pool()
    yield
    # Shutdown
    await close_db_pool()

app = FastAPI(lifespan=lifespan)
```

### Router organization

```python
# app/routers/orders.py
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/orders", tags=["orders"])

@router.get("/{order_id}")
async def get_order(order_id: int, db=Depends(get_db)):
    return await db.fetch_order(order_id)

# app/main.py
from app.routers import orders, health

app = FastAPI(lifespan=lifespan)
app.include_router(orders.router)
app.include_router(health.router)
```

## Pydantic v2 models

### Request/Response models

```python
from pydantic import BaseModel, Field, ConfigDict

class OrderCreate(BaseModel):
    model_config = ConfigDict(strict=True)

    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=1000)
    notes: str | None = None

class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    status: str
    created_at: datetime
```

### Validation with custom errors

```python
from pydantic import field_validator

class ProcessRequest(BaseModel):
    service_name: str

    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, v: str) -> str:
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("service_name must be alphanumeric with - or _")
        return v.lower()
```

## Dependencies (Depends)

### Database session

```python
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
```

### Auth dependency

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    payload = decode_jwt(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return await fetch_user(payload["sub"])

# Usage
@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return user
```

### Nested dependencies

```python
async def get_order_service(db: AsyncSession = Depends(get_db)) -> OrderService:
    return OrderService(db)

@router.post("/")
async def create_order(
    req: OrderCreate,
    svc: OrderService = Depends(get_order_service)
):
    return await svc.create(req)
```

## Background tasks

### FastAPI BackgroundTasks (simple, in-process)

```python
from fastapi import BackgroundTasks

async def send_notification(order_id: int):
    # Runs after response is sent
    await notify_service.send(order_id)

@router.post("/", status_code=201)
async def create_order(
    req: OrderCreate,
    background_tasks: BackgroundTasks,
    svc: OrderService = Depends(get_order_service)
):
    order = await svc.create(req)
    background_tasks.add_task(send_notification, order.id)
    return order
```

### asyncio.create_task (fire-and-forget with caution)

```python
import asyncio

@router.post("/batch")
async def start_batch(req: BatchRequest):
    task = asyncio.create_task(process_batch(req))
    task.add_done_callback(lambda t: log_if_failed(t))
    return {"status": "accepted"}

def log_if_failed(task: asyncio.Task):
    if task.exception():
        logger.error("Batch failed", exc_info=task.exception())
```

### When to use what

| Pattern | Use case |
|---------|----------|
| `BackgroundTasks` | Simple post-response work (notifications, logging) |
| `asyncio.create_task` | Long-running in-process work (with error callback) |
| Argo CronWorkflow | Scheduled/batch jobs (<org> standard for K8s) |
| Channel/Queue | High-volume producer-consumer (use `asyncio.Queue`) |

## Middleware

### Order matters — outermost runs first

```python
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# Applied bottom-to-top: GZip wraps CORS wraps app
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Custom middleware

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

app.add_middleware(RequestIdMiddleware)
```

## Async database access

### SQLAlchemy async

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine(
    "postgresql+asyncpg://user:pass@host/db",
    pool_size=20,
    max_overflow=10,
)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
```

### asyncpg direct (when ORM overhead is unnecessary)

```python
import asyncpg

pool: asyncpg.Pool | None = None

async def init_db_pool():
    global pool
    pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=5, max_size=20)

async def fetch_order(order_id: int) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)
        return dict(row) if row else None
```

## <org>: python-api integration

### OTel instrumentation (from otel-telemetry-helper)

```python
# otel-telemetry-helper/python/example/python-api/main.py
from otel_helper import setup_telemetry
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

def main():
    setup_telemetry()  # MUST be called first

    app = FastAPI(title="python-api")

    # Instrument AFTER app creation, BEFORE uvicorn.run
    FastAPIInstrumentor.instrument_app(app)

    # Include routers
    app.include_router(health_router)
    app.include_router(api_router)

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
```

### Health endpoints

```python
# <org> standard: /healthz (liveness) + /ready (readiness)
health_router = APIRouter(tags=["health"])

@health_router.get("/healthz")
async def healthz():
    return {"status": "ok"}

@health_router.get("/ready")
async def ready():
    # Check backing services
    if not await check_db():
        raise HTTPException(status_code=503, detail="DB unavailable")
    return {"status": "ready"}
```

### Environment variables (<org> standard)

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    service_name: str = "my-service"
    environment: str = "LOCAL"
    otel_exporter_otlp_endpoint: str = "http://otel-agent-collector.monitoring"

    class Config:
        env_file = ".env"  # Local dev only

settings = Settings()
```

## Testing

### TestClient (sync tests)

```python
from fastapi.testclient import TestClient

def test_get_order():
    client = TestClient(app)
    response = client.get("/orders/1")
    assert response.status_code == 200
    assert response.json()["id"] == 1
```

### Override dependencies

```python
from app.main import app
from app.deps import get_db

async def mock_db():
    yield FakeDB()

app.dependency_overrides[get_db] = mock_db

def test_create_order():
    client = TestClient(app)
    response = client.post("/orders/", json={"product_id": 1, "quantity": 2})
    assert response.status_code == 201

# Cleanup
app.dependency_overrides.clear()
```

### Async fixtures (pytest-asyncio)

```python
import pytest
from httpx import AsyncClient, ASGITransport

@pytest.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

@pytest.mark.asyncio
async def test_async_endpoint(async_client: AsyncClient):
    response = await async_client.get("/orders/1")
    assert response.status_code == 200
```

### Running tests

```bash
docker run --rm -v $(pwd)/python:/app -w /app python:3.11-slim sh -c \
  "pip install -e '.[dev]' -q && pytest tests/ -v"
```

## When NOT to use

- Building a gRPC service (not REST) — use `python-grpc-aio`
- Adding OTel tracing to an existing FastAPI app — use `python-otel-patterns`
- Building CLI tools (not web services) — use `python-cli-tools`

## Related skills

- `python-grpc-aio` — when the service contract is gRPC, not HTTP
- `python-otel-patterns` — OTel `FastAPIInstrumentor` and trace integration
- `mcp-server-development` — when the endpoint should be an MCP server
- `docker-compose-patterns` — local dev stack for FastAPI services
- `secrets-management-dotnet` — equivalent secrets patterns for .NET (if comparing stacks)

## Anti-patterns

### ❌ Blocking calls in async routes

```python
# ❌ Blocks the event loop — all other requests stall
@router.get("/data")
async def get_data():
    result = requests.get("http://external-api/data")  # SYNC!
    return result.json()

# ✅ Use httpx (async) or run_in_executor
import httpx

@router.get("/data")
async def get_data():
    async with httpx.AsyncClient() as client:
        response = await client.get("http://external-api/data")
    return response.json()
```

### ❌ Global mutable state

```python
# ❌ Race conditions, no request isolation
results = []

@router.post("/process")
async def process(req: Request):
    results.append(await compute(req))  # Shared state!
    return {"count": len(results)}
```

### ❌ Heavy computation in async route without executor

```python
# ❌ CPU-bound work blocks event loop
@router.get("/report")
async def generate_report():
    return compute_heavy_report()  # Blocks!

# ✅ Offload to thread pool
import asyncio

@router.get("/report")
async def generate_report():
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, compute_heavy_report)
```

### ❌ Complex dependency chains in path operations

```python
# ❌ 5 nested Depends — hard to test, slow to resolve
@router.get("/x")
async def get_x(
    a=Depends(get_a),
    b=Depends(get_b),
    c=Depends(get_c(get_a, get_b)),
    d=Depends(get_d(get_c)),
    e=Depends(get_e(get_d))
):
    ...

# ✅ Compose into a service class
@router.get("/x")
async def get_x(svc: XService = Depends(get_x_service)):
    return await svc.execute()
```

### ❌ setup_telemetry() at module level

```python
# ❌ Silent failure during import
from otel_helper import setup_telemetry
setup_telemetry()  # Module level — swallows ValueError

# ✅ Inside main() or lifespan
def main():
    setup_telemetry()
```

### ❌ FastAPIInstrumentor().instrument() instead of instrument_app()

```python
# ❌ Only instruments apps created AFTER this call
FastAPIInstrumentor().instrument()
app = FastAPI()  # NOT instrumented

# ✅ Instrument the specific app instance
app = FastAPI()
FastAPIInstrumentor.instrument_app(app)
```

## Reference

- <org> sample: `otel-telemetry-helper/python/example/python-api/`
- Related skill: `python-otel-patterns` (OTel integration details)
- Related skill: `python-grpc-aio` (gRPC backend)
- All builds run via Docker (Python 3.11, no local interpreter dependency)
