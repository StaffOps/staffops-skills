---
name: dotnet-async-patterns
description: "Write async .NET workers, channels and pipelines."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [dotnet, async, patterns, development]
    category: development
    related_skills: [dotnet-apm-metrics, dotnet-otel-patterns, secrets-management-dotnet]
---
# .NET Async Patterns

Async/await patterns for .NET 8+ services at <org>. Applies to background workers, queue consumers, and API controllers.

## When to Use

Use when implementing async workers, producer-consumer pipelines, or concurrent processing in .NET. Covers Task vs ValueTask, Channels, Parallel.ForEachAsync, SemaphoreSlim, CancellationToken propagation, IAsyncEnumerable, and common deadlock/starvation pitfalls.

## Task vs ValueTask

### When to use ValueTask

Use `ValueTask<T>` when the method **frequently completes synchronously** (cache hits, buffered reads):

```csharp
public ValueTask<Order?> GetOrderAsync(int id)
{
    if (_cache.TryGetValue(id, out var order))
        return ValueTask.FromResult(order);  // No allocation

    return new ValueTask<Order?>(FetchFromDbAsync(id));
}
```

### When to use Task

Use `Task<T>` for everything else — especially when:
- Result is awaited multiple times
- Stored in a variable for later await
- Used with `Task.WhenAll` / `Task.WhenAny`

```csharp
// ❌ WRONG — ValueTask cannot be awaited twice
var vt = GetOrderAsync(1);
var a = await vt;
var b = await vt;  // UNDEFINED BEHAVIOR

// ✅ Use Task when you need to store/reuse
Task<Order?> task = GetOrderAsync(1).AsTask();
```

### ConfigureAwait(false)

In **library code** (like <org> OTel Helper), always use `ConfigureAwait(false)` to avoid capturing `SynchronizationContext`:

```csharp
// Library code — no UI context needed
public async Task<string> FetchDataAsync()
{
    var response = await _httpClient.GetAsync(url).ConfigureAwait(false);
    return await response.Content.ReadAsStringAsync().ConfigureAwait(false);
}
```

In **ASP.NET Core apps** (no SynchronizationContext), `ConfigureAwait(false)` is technically unnecessary but harmless. <org> convention: omit in app code, include in shared libs.

## Channels — producer-consumer

`System.Threading.Channels` is the preferred pattern for in-process producer-consumer queues.

### Bounded channel (backpressure)

```csharp
public class MessageProcessor : BackgroundService
{
    private readonly Channel<Message> _channel = Channel.CreateBounded<Message>(
        new BoundedChannelOptions(capacity: 100)
        {
            FullMode = BoundedChannelFullMode.Wait,
            SingleReader = true,
            SingleWriter = false
        });

    public async ValueTask EnqueueAsync(Message msg, CancellationToken ct)
    {
        await _channel.Writer.WriteAsync(msg, ct);
    }

    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        await foreach (var msg in _channel.Reader.ReadAllAsync(ct))
        {
            using var span = _activity.StartRootActivity("message.process");
            await ProcessAsync(msg, ct);
        }
    }
}
```

### Unbounded channel (when producer must never block)

```csharp
var channel = Channel.CreateUnbounded<LogEntry>(new UnboundedChannelOptions
{
    SingleReader = true,
    SingleWriter = false
});
```

Use unbounded only when you can guarantee the consumer keeps up, or accept memory growth.

## Parallel.ForEachAsync

.NET 6+ provides `Parallel.ForEachAsync` for concurrent iteration with controlled parallelism:

```csharp
public async Task ProcessBatchAsync(IEnumerable<Order> orders, CancellationToken ct)
{
    await Parallel.ForEachAsync(orders, new ParallelOptions
    {
        MaxDegreeOfParallelism = 10,
        CancellationToken = ct
    }, async (order, token) =>
    {
        await ProcessOrderAsync(order, token);
    });
}
```

### When to use vs Task.WhenAll

| Scenario | Use |
|----------|-----|
| Fixed small set of tasks | `Task.WhenAll(t1, t2, t3)` |
| Large/unbounded collection | `Parallel.ForEachAsync` |
| Need backpressure | `Parallel.ForEachAsync` with `MaxDegreeOfParallelism` |
| Different task types | `Task.WhenAll` |

## SemaphoreSlim — concurrency limiting

For fine-grained concurrency control (e.g., limiting external API calls):

```csharp
public class RateLimitedClient
{
    private readonly SemaphoreSlim _semaphore = new(maxCount: 5);
    private readonly HttpClient _http;

    public async Task<Response> CallApiAsync(Request req, CancellationToken ct)
    {
        await _semaphore.WaitAsync(ct);
        try
        {
            return await _http.PostAsJsonAsync("/api/process", req, ct);
        }
        finally
        {
            _semaphore.Release();
        }
    }
}
```

### SemaphoreSlim vs Parallel.ForEachAsync

- `Parallel.ForEachAsync`: controls parallelism over a **collection**
- `SemaphoreSlim`: controls parallelism across **arbitrary call sites** (DI-injected, shared across methods)

## CancellationToken propagation

### Rule: pass CancellationToken to EVERY async method

```csharp
// ✅ Propagate token through the entire call chain
public async Task ProcessAsync(CancellationToken ct)
{
    var data = await _repo.GetDataAsync(ct);
    await _processor.TransformAsync(data, ct);
    await _publisher.PublishAsync(data, ct);
}
```

### Linked tokens (combine timeouts with shutdown)

```csharp
protected override async Task ExecuteAsync(CancellationToken stoppingToken)
{
    while (!stoppingToken.IsCancellationRequested)
    {
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
        cts.CancelAfter(TimeSpan.FromSeconds(30));  // Per-iteration timeout

        try
        {
            await ProcessNextAsync(cts.Token);
        }
        catch (OperationCanceledException) when (!stoppingToken.IsCancellationRequested)
        {
            _logger.LogWarning("Iteration timed out, retrying");
        }
    }
}
```

### Graceful shutdown with token

```csharp
app.Lifetime.ApplicationStopping.Register(() =>
{
    // Flush OTel, drain channels
    _channel.Writer.Complete();
});
```

## IAsyncEnumerable + await foreach

For streaming data without buffering entire collections:

```csharp
public async IAsyncEnumerable<Order> GetOrdersStreamAsync(
    [EnumeratorCancellation] CancellationToken ct = default)
{
    await foreach (var batch in _db.QueryBatchesAsync(ct))
    {
        foreach (var order in batch)
        {
            yield return order;
        }
    }
}

// Consumer
await foreach (var order in GetOrdersStreamAsync(ct))
{
    await ProcessAsync(order, ct);
}
```

### With Channel reader

```csharp
// Channel.Reader.ReadAllAsync returns IAsyncEnumerable<T>
await foreach (var item in channel.Reader.ReadAllAsync(ct))
{
    await HandleAsync(item, ct);
}
```

## <org>: dotnet-process workers

The `otel-telemetry-helper` sample app `dotnet-process` demonstrates these patterns:

### Queue consumer worker

```csharp
// otel-telemetry-helper/dotnet/example/dotnet-process/Workers/QueueConsumerWorker.cs
public class QueueConsumerWorker(ActivitySource activity) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            using var span = activity.StartRootActivity("queue.consume");
            // Each iteration = independent trace
            await SimulateQueueRead(ct);
            await Task.Delay(TimeSpan.FromSeconds(30), ct);
        }
    }
}
```

### Scheduled job worker

```csharp
// otel-telemetry-helper/dotnet/example/dotnet-process/Workers/ScheduledWorker.cs
public class ScheduledWorker(ActivitySource activity) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromMinutes(5));
        while (await timer.WaitForNextTickAsync(ct))
        {
            using var span = activity.StartRootActivity("scheduled.job");
            await RunJobAsync(ct);
        }
    }
}
```

Key patterns from <org> sample apps:
- `StartRootActivity` for independent traces per iteration (see `dotnet-otel-patterns` skill)
- `CancellationToken` propagated from `BackgroundService.ExecuteAsync`
- `PeriodicTimer` (.NET 6+) instead of `Task.Delay` loops for scheduled work

### Running tests

```bash
docker run --rm -v $(pwd)/dotnet:/src -w /src \
  mcr.microsoft.com/dotnet/sdk:8.0 dotnet test
```

## Anti-patterns

### ❌ async void (exception black hole)

```csharp
// ❌ NEVER — exceptions crash the process or vanish
async void HandleMessage(Message msg) { ... }

// ✅ Return Task
async Task HandleMessageAsync(Message msg) { ... }
```

Only valid use of `async void`: event handlers in UI frameworks (not applicable at <org>).

### ❌ Task.Result / .Wait() (deadlock risk)

```csharp
// ❌ Blocks thread, risks deadlock
var result = GetDataAsync().Result;
GetDataAsync().Wait();

// ✅ Await properly
var result = await GetDataAsync();
```

### ❌ Sync-over-async (ThreadPool starvation)

```csharp
// ❌ Blocks a ThreadPool thread waiting for async work
public string GetData()
{
    return GetDataAsync().GetAwaiter().GetResult();
}

// ✅ Make the caller async
public async Task<string> GetDataAsync() { ... }
```

In ASP.NET Core, sync-over-async under load causes **ThreadPool starvation** — requests queue up, latency spikes, health checks fail.

### ❌ Fire-and-forget without error handling

```csharp
// ❌ Exception silently lost
_ = ProcessAsync(data);

// ✅ If truly fire-and-forget, at least log errors
_ = Task.Run(async () =>
{
    try { await ProcessAsync(data); }
    catch (Exception ex) { _logger.LogError(ex, "Background task failed"); }
});

// ✅✅ Better: use a Channel to queue work for a dedicated consumer
await _channel.Writer.WriteAsync(data, ct);
```

### ❌ Unbounded Task.WhenAll on large collections

```csharp
// ❌ Spawns 10,000 concurrent HTTP calls — OOM, socket exhaustion
var tasks = orders.Select(o => ProcessAsync(o));
await Task.WhenAll(tasks);

// ✅ Use Parallel.ForEachAsync with bounded parallelism
await Parallel.ForEachAsync(orders, new ParallelOptions
{
    MaxDegreeOfParallelism = 10
}, async (o, ct) => await ProcessAsync(o, ct));
```

### ❌ Missing CancellationToken

```csharp
// ❌ Cannot be cancelled — blocks shutdown
await Task.Delay(TimeSpan.FromMinutes(5));

// ✅ Respects graceful shutdown
await Task.Delay(TimeSpan.FromMinutes(5), ct);
```

### ❌ Capturing loop variable in async lambda

```csharp
// ❌ Classic closure bug (all tasks see final value of i)
for (int i = 0; i < 10; i++)
{
    _ = Task.Run(async () => await Process(i));
}

// ✅ Capture in local
for (int i = 0; i < 10; i++)
{
    var local = i;
    _ = Task.Run(async () => await Process(local));
}
```

## Summary table

| Pattern | When to use |
|---------|-------------|
| `Channel<T>` | In-process producer-consumer with backpressure |
| `Parallel.ForEachAsync` | Bounded parallel iteration over collections |
| `SemaphoreSlim` | Cross-method concurrency limiting |
| `IAsyncEnumerable` | Streaming without buffering |
| `PeriodicTimer` | Scheduled background work |
| `CancellationTokenSource.CreateLinkedTokenSource` | Per-operation timeouts |
| `ValueTask` | Hot-path methods that often complete synchronously |

## Reference

- <org> sample: `otel-telemetry-helper/dotnet/example/dotnet-process/`
- Related skill: `dotnet-otel-patterns` (StartRootActivity for workers)
- All builds run via Docker (no local .NET SDK dependency)
