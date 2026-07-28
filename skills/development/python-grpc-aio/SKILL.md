---
name: python-grpc-aio
description: "Build async Python gRPC servers and clients."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, grpc, aio, development]
    category: development
    related_skills: [python-apm-metrics, python-otel-patterns, python-fastapi-patterns, grpc-distributed-tracing]
---
# Python gRPC aio Patterns

Asyncio-native gRPC patterns for <org> Python services. Reference implementation: `otel-telemetry-helper/python/example/python-backend/`.

## When to Use

Use when building asyncio-native gRPC services in Python. Covers grpc.aio server/client, protobuf compilation, streaming RPCs, interceptors, health checking, reflection, and <org> python-backend integration with OTel GrpcAioInstrumentor.

## Critical: grpc.aio vs grpc (sync)

Always use `grpc.aio` for async Python services. The sync `grpc` module spawns threads and does NOT integrate with asyncio:

```python
# ❌ WRONG — sync gRPC, blocks event loop if mixed with async code
import grpc
server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

# ✅ CORRECT — asyncio-native
import grpc.aio
server = grpc.aio.server()
```

## Protobuf compilation

### Proto file

```protobuf
// protos/notification.proto
syntax = "proto3";
package notification;

service NotificationService {
    rpc SendNotification (NotificationRequest) returns (NotificationResponse);
    rpc StreamNotifications (StreamRequest) returns (stream NotificationEvent);
}

message NotificationRequest {
    string recipient = 1;
    string message = 2;
    string channel = 3;  // "email", "sms", "push"
}

message NotificationResponse {
    string notification_id = 1;
    bool success = 2;
}
```

### Compilation

```bash
docker run --rm -v $(pwd)/python:/app -w /app python:3.11-slim sh -c "
  pip install grpcio-tools -q &&
  python -m grpc_tools.protoc \
    -I protos/ \
    --python_out=generated/ \
    --grpc_python_out=generated/ \
    --pyi_out=generated/ \
    protos/notification.proto
"
```

### Import path fix

Generated code uses relative imports that break. Fix with `sys.path` or `__init__.py`:

```python
# generated/__init__.py (empty file — makes it a package)

# In your service code:
from generated import notification_pb2, notification_pb2_grpc
```

Or use the `grpc_tools.protoc` `--pyi_out` for type stubs alongside generated code.

## Server implementation

### Basic server

```python
import grpc.aio
from generated import notification_pb2, notification_pb2_grpc

class NotificationServicer(notification_pb2_grpc.NotificationServiceServicer):
    async def SendNotification(self, request, context):
        # All methods are async
        result = await self._send(request.recipient, request.message)
        return notification_pb2.NotificationResponse(
            notification_id=result.id,
            success=True
        )

    async def StreamNotifications(self, request, context):
        # Server streaming — yield responses
        async for event in self._watch_events(request.filter):
            yield notification_pb2.NotificationEvent(
                event_id=event.id,
                payload=event.data
            )

async def serve():
    server = grpc.aio.server()
    notification_pb2_grpc.add_NotificationServiceServicer_to_server(
        NotificationServicer(), server
    )
    server.add_insecure_port("[::]:50051")
    await server.start()
    await server.wait_for_termination()
```

### Graceful shutdown

```python
import asyncio
import signal

async def serve():
    server = grpc.aio.server()
    # ... add servicers ...
    server.add_insecure_port("[::]:50051")
    await server.start()

    async def shutdown(sig):
        await server.stop(grace=5)  # 5s grace period

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))

    await server.wait_for_termination()
```

## Client implementation

### Unary-unary call

```python
import grpc.aio
from generated import notification_pb2, notification_pb2_grpc

async def send_notification(recipient: str, message: str) -> str:
    async with grpc.aio.insecure_channel("localhost:50051") as channel:
        stub = notification_pb2_grpc.NotificationServiceStub(channel)
        response = await stub.SendNotification(
            notification_pb2.NotificationRequest(
                recipient=recipient,
                message=message,
                channel="email"
            )
        )
        return response.notification_id
```

### Server streaming (client reads stream)

```python
async def watch_notifications():
    async with grpc.aio.insecure_channel("localhost:50051") as channel:
        stub = notification_pb2_grpc.NotificationServiceStub(channel)
        async for event in stub.StreamNotifications(
            notification_pb2.StreamRequest(filter="all")
        ):
            print(f"Event: {event.event_id}")
```

### Client streaming

```python
async def upload_batch(items: list[Item]):
    async with grpc.aio.insecure_channel("localhost:50051") as channel:
        stub = service_pb2_grpc.BatchServiceStub(channel)

        async def request_iterator():
            for item in items:
                yield service_pb2.BatchItem(data=item.serialize())

        response = await stub.UploadBatch(request_iterator())
        return response.count
```

### Bidirectional streaming

```python
async def chat():
    async with grpc.aio.insecure_channel("localhost:50051") as channel:
        stub = chat_pb2_grpc.ChatServiceStub(channel)

        async def outgoing():
            while True:
                msg = await get_user_input()
                yield chat_pb2.ChatMessage(text=msg)

        async for reply in stub.Chat(outgoing()):
            print(f"Server: {reply.text}")
```

## Streaming RPC types summary

| Type | Client sends | Server sends | Use case |
|------|-------------|-------------|----------|
| Unary-Unary | 1 message | 1 message | Standard request/response |
| Server streaming | 1 message | N messages | Watch/subscribe, large result sets |
| Client streaming | N messages | 1 message | File upload, batch ingestion |
| Bidirectional | N messages | N messages | Chat, real-time sync |

## Interceptors

### Server interceptor (logging, auth)

```python
class AuthInterceptor(grpc.aio.ServerInterceptor):
    async def intercept_service(self, continuation, handler_call_details):
        metadata = dict(handler_call_details.invocation_metadata)
        token = metadata.get("authorization", "")

        if not await validate_token(token):
            # Return an error handler
            async def abort(request, context):
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid token")
            return grpc.unary_unary_rpc_method_handler(abort)

        return await continuation(handler_call_details)

# Usage
server = grpc.aio.server(interceptors=[AuthInterceptor()])
```

### Client interceptor (retry, metadata injection)

```python
class RetryInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    async def intercept_unary_unary(self, continuation, client_call_details, request):
        for attempt in range(3):
            try:
                return await continuation(client_call_details, request)
            except grpc.aio.AioRpcError as e:
                if e.code() not in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
                    raise
                if attempt == 2:
                    raise
                await asyncio.sleep(0.5 * (2 ** attempt))

# Usage
channel = grpc.aio.insecure_channel(
    "localhost:50051",
    interceptors=[RetryInterceptor()]
)
```

## Health checking

```python
from grpc_health.v1 import health_pb2, health_pb2_grpc
from grpc_health.v1.health import HealthServicer

async def serve():
    server = grpc.aio.server()

    # Add health service
    health_servicer = HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Set service status
    health_servicer.set("notification.NotificationService", health_pb2.HealthCheckResponse.SERVING)

    # Add your services
    notification_pb2_grpc.add_NotificationServiceServicer_to_server(
        NotificationServicer(), server
    )

    server.add_insecure_port("[::]:50051")
    await server.start()
    await server.wait_for_termination()
```

K8s gRPC probe:
```yaml
livenessProbe:
  grpc:
    port: 50051
```

## Reflection (for grpcurl/grpcui debugging)

```python
from grpc_reflection.v1alpha import reflection

async def serve():
    server = grpc.aio.server()
    # ... add servicers ...

    # Enable reflection (list available services)
    service_names = (
        notification_pb2.DESCRIPTOR.services_by_name["NotificationService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    server.add_insecure_port("[::]:50051")
    await server.start()
```

Test with grpcurl:
```bash
grpcurl -plaintext localhost:50051 list
grpcurl -plaintext localhost:50051 notification.NotificationService/SendNotification
```

## <org>: python-backend integration

### OTel instrumentation (CRITICAL order)

```python
# otel-telemetry-helper/python/example/python-backend/main.py
from otel_helper import setup_telemetry
from opentelemetry.instrumentation.grpc import (
    GrpcAioInstrumentorServer,
    GrpcAioInstrumentorClient,
)

async def main():
    # 1. Setup telemetry FIRST
    setup_telemetry()

    # 2. Instrument BEFORE creating channels/servers
    GrpcAioInstrumentorServer().instrument()
    GrpcAioInstrumentorClient().instrument()

    # 3. NOW create server — it's automatically instrumented
    server = grpc.aio.server()
    # ... add servicers ...
    server.add_insecure_port("[::]:50051")
    await server.start()
    await server.wait_for_termination()
```

**Why order matters**: `GrpcAioInstrumentorServer().instrument()` monkey-patches `grpc.aio.server()`. If you create the server BEFORE instrumenting, traces won't be captured.

### <org> python-backend structure

```
python-backend/
├── main.py              # Entry point: setup_telemetry → instrument → serve
├── servicers/           # gRPC service implementations
│   └── notification.py
├── generated/           # Proto-generated code
│   ├── __init__.py
│   ├── notification_pb2.py
│   └── notification_pb2_grpc.py
└── Dockerfile
```

### Running tests

```bash
docker run --rm -v $(pwd)/python:/app -w /app python:3.11-slim sh -c "
  pip install -e '.[dev]' grpcio grpcio-tools -q &&
  pytest tests/ -v -k grpc
"
```

## Anti-patterns

### ❌ Missing await on RPC calls

```python
# ❌ Returns a coroutine object, not the response!
response = stub.SendNotification(request)
print(response.notification_id)  # AttributeError!

# ✅ Await the call
response = await stub.SendNotification(request)
```

### ❌ Sync code inside async servicer

```python
# ❌ Blocks the event loop
class MyServicer(service_pb2_grpc.MyServiceServicer):
    async def Process(self, request, context):
        result = requests.get("http://api/data")  # SYNC HTTP!
        time.sleep(1)  # BLOCKS!
        return service_pb2.Response(data=result.text)

# ✅ Use async libraries
class MyServicer(service_pb2_grpc.MyServiceServicer):
    async def Process(self, request, context):
        async with httpx.AsyncClient() as client:
            result = await client.get("http://api/data")
        await asyncio.sleep(1)
        return service_pb2.Response(data=result.text)
```

### ❌ Using sync grpc.insecure_channel in async code

```python
# ❌ Sync channel — blocks on calls
channel = grpc.insecure_channel("localhost:50051")

# ✅ Async channel
channel = grpc.aio.insecure_channel("localhost:50051")
```

### ❌ Instrumenting AFTER server/channel creation

```python
# ❌ Server already created — monkey-patch has no effect
server = grpc.aio.server()
GrpcAioInstrumentorServer().instrument()  # TOO LATE

# ✅ Instrument first
GrpcAioInstrumentorServer().instrument()
server = grpc.aio.server()  # Now instrumented
```

### ❌ Not handling context cancellation

```python
# ❌ Ignores client disconnect
class MyServicer(service_pb2_grpc.MyServiceServicer):
    async def LongProcess(self, request, context):
        for i in range(1000):
            await heavy_work(i)  # Continues even if client cancelled
        return response

# ✅ Check context
class MyServicer(service_pb2_grpc.MyServiceServicer):
    async def LongProcess(self, request, context):
        for i in range(1000):
            if context.cancelled():
                return service_pb2.Response()
            await heavy_work(i)
        return response
```

### ❌ Forgetting to close channels

```python
# ❌ Channel leak
async def call_service():
    channel = grpc.aio.insecure_channel("localhost:50051")
    stub = service_pb2_grpc.MyServiceStub(channel)
    return await stub.DoWork(request)
    # Channel never closed!

# ✅ Use async context manager
async def call_service():
    async with grpc.aio.insecure_channel("localhost:50051") as channel:
        stub = service_pb2_grpc.MyServiceStub(channel)
        return await stub.DoWork(request)
```

## Reference

- <org> sample: `otel-telemetry-helper/python/example/python-backend/`
- Related skill: `python-otel-patterns` (GrpcAioInstrumentor details)
- Related skill: `grpc-distributed-tracing` (cross-language propagation)
- Related skill: `python-fastapi-patterns` (API layer calling gRPC backend)
- Steering: `dev-environment.md` (all builds via Docker, Python 3.11)
