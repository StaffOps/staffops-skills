---
name: python-performance
description: "Profile and speed up Python: cProfile, GIL, async."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, performance, profiling, gil, asyncio, multiprocessing]
    category: development
    related_skills: [python-scripting, python-otel-patterns]
---
# Python Performance

Profiling before optimizing, understanding what the GIL actually does and
doesn't constrain, and choosing correctly between threading,
multiprocessing, and asyncio for a given bottleneck — the wrong choice
among these three is a common source of "I parallelized it and it didn't
get faster."

## When to Use

Use when a Python program is slower than expected, before reaching for any
specific optimization technique, when deciding how to parallelize CPU-bound
versus I/O-bound work, or explaining why adding threads didn't speed up a
computation.

## Profile before optimizing — always

```bash
python -m cProfile -s cumulative myscript.py
python -m cProfile -o profile.stats myscript.py
```

```python
import pstats
p = pstats.Stats("profile.stats")
p.sort_stats("cumulative").print_stats(20)   # top 20 by cumulative time
p.sort_stats("tottime").print_stats(20)       # top 20 by time in the function ITSELF
```

`cumulative` time includes time spent in functions it calls;
`tottime` (total time) is time spent in that function's own code,
excluding its callees. `tottime` is usually the more actionable sort order
— it directly identifies which specific function's own logic is expensive,
rather than a high-level function that's merely "slow" because it happens
to call something else that's actually the bottleneck.

**Guessing at the bottleneck without profiling first is the single most
common performance-tuning mistake.** Intuition about what's slow in Python
is frequently wrong — a "probably fine" string operation or a taken-for-
granted library call is very often where the actual time goes, and
optimizing the wrong thing wastes effort while leaving the real bottleneck
untouched.

## line_profiler: per-line detail

```bash
pip install line_profiler
kernprof -l -v myscript.py
```

```python
@profile        # kernprof injects this decorator; no import needed when run via kernprof
def process(data):
    result = []
    for item in data:
        result.append(transform(item))    # this line's actual cost is now visible
    return result
```

`cProfile` shows cost **per function**; `line_profiler` shows cost **per
line** within a function marked with `@profile` — useful once `cProfile`
has already identified which function is the bottleneck, to pinpoint
exactly which line inside it is responsible.

## py-spy: profiling a running process without modifying it

```bash
py-spy top --pid 12345               # live, top-like view of what's hot right now
py-spy dump --pid 12345               # a snapshot of every thread's current stack
py-spy record -o profile.svg --pid 12345   # a flame graph
```

`py-spy` attaches to an **already-running** process from the outside — no
code changes, no restart required. This is the tool of choice for
diagnosing a production process that's currently slow or appears hung,
where adding `cProfile` instrumentation would require a restart (losing the
exact state that's causing the problem) or isn't practical at all.

## The GIL: what it actually constrains

The Global Interpreter Lock ensures only one thread executes Python
bytecode at a time within a single process — this has a specific, often
misunderstood consequence:

- **CPU-bound work does NOT speed up with threading** — multiple threads
  computing in pure Python still take turns on the single GIL; adding
  threads to a CPU-bound loop typically doesn't reduce wall-clock time, and
  can make it slightly worse due to thread-switching overhead.
- **I/O-bound work DOES benefit from threading** — while one thread is
  blocked waiting on a network call, disk read, or similar, the GIL is
  released and another thread can run. This is the actual, well-suited use
  case for Python threading.
- **C extensions frequently release the GIL** during their own
  computation — this is *why* NumPy, for instance, can genuinely use
  multiple cores for array operations even though it's called from Python:
  the actual number-crunching happens in C code that has released the GIL
  for its duration.

```python
# CPU-bound: threading does NOT help meaningfully.
import threading

def cpu_heavy(n):
    return sum(i * i for i in range(n))

threads = [threading.Thread(target=cpu_heavy, args=(10_000_000,)) for _ in range(4)]
# Still roughly as slow as running them sequentially -- the GIL serializes
# the actual bytecode execution regardless of thread count.
```

```python
# I/O-bound: threading DOES help, genuinely.
import threading
import requests

def fetch(url):
    return requests.get(url)     # blocks on network I/O; GIL is released during the wait

threads = [threading.Thread(target=fetch, args=(url,)) for url in urls]
# These genuinely run concurrently -- while one waits on the network,
# another can proceed.
```

## Choosing the right concurrency model

| Workload | Tool | Why |
| --- | --- | --- |
| CPU-bound (heavy computation) | `multiprocessing` | Separate processes, separate GILs — genuine parallelism across cores |
| I/O-bound, moderate scale | `threading` | The GIL releases during I/O waits; simple, works well up to hundreds of connections |
| I/O-bound, high concurrency | `asyncio` | Single thread, cooperative scheduling — scales to thousands of concurrent operations with far less overhead than a thread per connection |

```python
# CPU-bound: multiprocessing gets REAL parallelism, at the cost of
# process-spawn overhead and needing to pass data between processes
# (which must be picklable).
from multiprocessing import Pool

def cpu_heavy(n):
    return sum(i * i for i in range(n))

with Pool(processes=4) as pool:
    results = pool.map(cpu_heavy, [10_000_000] * 4)
    # This DOES run on 4 separate cores -- each process has its own GIL.
```

```python
# I/O-bound, high concurrency: asyncio.
import asyncio
import aiohttp

async def fetch(session, url):
    async with session.get(url) as response:
        return await response.text()

async def fetch_all(urls):
    async with aiohttp.ClientSession() as session:
        return await asyncio.gather(*(fetch(session, url) for url in urls))

results = asyncio.run(fetch_all(urls))
```

`asyncio` requires an async-compatible library for each I/O operation
(`aiohttp` rather than `requests`, `asyncpg` rather than a synchronous
database driver) — mixing a blocking synchronous call into async code
blocks the *entire* event loop, not just that one coroutine, defeating the
purpose and stalling every other concurrent operation until it completes.

## Common performance mistakes

```python
# Slow: string concatenation in a loop is O(n²) -- each += creates a new string.
result = ""
for item in items:
    result += str(item)

# Fast: O(n) -- build a list, join once.
result = "".join(str(item) for item in items)
```

```python
# Slow: repeated membership checks against a list are O(n) EACH.
allowed = ["a", "b", "c", ..., "z"]   # a long list
if x in allowed:      # O(n) scan every time

# Fast: a set's membership check is O(1).
allowed = {"a", "b", "c", ..., "z"}
if x in allowed:      # O(1)
```

```python
# Slow: repeated attribute/dict lookups inside a hot loop.
for item in items:
    process(config.settings.threshold, item)

# Faster: hoist the invariant lookup OUT of the loop.
threshold = config.settings.threshold
for item in items:
    process(threshold, item)
```

None of these matter for a loop that runs a handful of times — they matter
specifically in a **hot path**, something executed a very large number of
times, which is exactly what profiling (not guessing) identifies.

## Caching

```python
from functools import lru_cache

@lru_cache(maxsize=1024)
def expensive_computation(x: int) -> int:
    # ... genuinely expensive, and pure (same input always -> same output) ...
    return result
```

`lru_cache` memoizes a **pure** function's results automatically — the
single highest-leverage, lowest-effort optimization for a function that's
called repeatedly with a limited set of distinct arguments and has no side
effects. It is specifically inappropriate for an impure function (one whose
result depends on external state or has side effects), since the cache
would silently return a stale or simply wrong result on a later call.

## When Python itself is the wrong tool

```python
# NumPy: vectorized operations run in C, not the Python interpreter loop.
import numpy as np
arr = np.array(data)
result = arr * 2 + 1          # far faster than a Python-level loop over the same data
```

For genuinely performance-critical numerical code, delegating the actual
computation to NumPy (or, for the narrowest hot spots, a compiled extension
via Cython or a Rust extension module) sidesteps the interpreter loop and
the GIL entirely for that operation — this is usually a far larger win than
any amount of pure-Python micro-optimization, and is the right conclusion
to reach *once profiling has confirmed* that a specific numerical
computation is genuinely the bottleneck.

## Memory profiling

```bash
pip install memory_profiler
python -m memory_profiler myscript.py
```

```python
from memory_profiler import profile

@profile
def process_large_dataset():
    data = load_everything()      # per-line memory delta becomes visible
    ...
```

Useful for the same reason `line_profiler` is for CPU time — pinpointing
exactly which line causes a memory spike, distinct from simply knowing the
process's overall memory usage is high.

## Pitfalls

- **Optimizing before profiling** — intuition about what's slow in Python
  is frequently wrong; profile first, every time.
- **Adding threads to CPU-bound work expecting a speedup** — the GIL
  prevents it; use `multiprocessing` instead.
- **Mixing a blocking synchronous call into `asyncio` code** — stalls the
  entire event loop, not just that one coroutine.
- **String concatenation with `+=` in a loop** — quadratic; use
  `"".join(...)`.
- **List membership checks (`in`) in a hot loop** where a `set` would be
  O(1) instead of O(n).
- **`@lru_cache` on an impure function** — silently returns stale or wrong
  results.
- **Reaching for a compiled extension before confirming, via profiling,
  that the specific code path is actually the bottleneck** — premature and
  often unnecessary complexity.

## Reference

- `python-scripting` — the code typically being profiled and optimized
- `python-otel-patterns` — production-grade tracing/metrics, complementary
  to ad-hoc local profiling for understanding real-world performance
