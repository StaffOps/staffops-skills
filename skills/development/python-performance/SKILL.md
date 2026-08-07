---
name: python-performance
description: "Use when profiling slow Python code, choosing between threading/multiprocessing/asyncio, diagnosing GIL contention, or optimizing hot paths. Covers cProfile, line_profiler, memory_profiler, and concurrency decision tree."
version: 1.1.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, performance, profiling, gil, asyncio, multiprocessing]
    category: development
    related_skills: [python-scripting, python-otel-patterns, python-fastapi-patterns]
---

# Python Performance

Profile first. Optimize second. Choose the right concurrency model for the bottleneck type.

## When to Use

- Python program is slower than expected
- Need to find WHERE time is spent before optimizing
- Deciding between threading / multiprocessing / asyncio
- Memory usage growing unexpectedly
- Need to prove an optimization actually helped

## When NOT to Use

- Premature optimization ("I think this might be slow" without measurement)
- Algorithm-level issues → fix the algorithm first, then profile
- I/O-bound but already using asyncio correctly → look at the network/DB, not Python

---

## Step 1: Profile Before Optimizing — Always

### cProfile (function-level, built-in)

```bash
# Quick: sort by cumulative time
python -m cProfile -s cumulative myscript.py

# Save to file for analysis
python -m cProfile -o profile.stats myscript.py

# Analyze saved profile
python -c "
import pstats
p = pstats.Stats('profile.stats')
p.sort_stats('cumulative').print_stats(20)
"
```

### line_profiler (line-by-line — the one you actually want)

```bash
pip install line_profiler

# Decorate the suspect function
# @profile  ← add this decorator
kernprof -l -v myscript.py
```

```python
# Or programmatic:
from line_profiler import LineProfiler

lp = LineProfiler()
lp.add_function(my_suspect_function)
lp.enable_by_count()
result = my_suspect_function()
lp.disable_by_count()
lp.print_stats()
```

### memory_profiler (memory line-by-line)

```bash
pip install memory_profiler

# Decorate with @profile, then:
python -m memory_profiler myscript.py
```

### timeit (micro-benchmarks)

```python
import timeit

# Compare two approaches
t1 = timeit.timeit("'-'.join(str(i) for i in range(100))", number=10000)
t2 = timeit.timeit("'-'.join(map(str, range(100)))", number=10000)
print(f"Generator: {t1:.4f}s, map: {t2:.4f}s")
```

### Docker-based profiling (no local install)

```bash
docker run --rm -v "$(pwd):/app" -w /app python:3.11-slim sh -c "
  pip install -q line-profiler memory-profiler &&
  python -m cProfile -s cumulative app/main.py
"
```

---

## Step 2: The GIL Decision Tree

```
Is the bottleneck CPU-bound or I/O-bound?

I/O-bound (network, disk, DB):
  ├── Many concurrent connections → asyncio
  ├── Few connections, simple logic → threading
  └── Already in sync framework → threading + ThreadPoolExecutor

CPU-bound (computation, parsing, math):
  ├── Parallelizable work units → multiprocessing
  ├── NumPy/pandas operations → already bypasses GIL internally
  └── Single hot loop → rewrite in C/Cython/Rust, or use numpy vectorization
```

### Threading (I/O-bound only)

```python
from concurrent.futures import ThreadPoolExecutor
import requests

urls = ["https://api.example.com/1", "https://api.example.com/2", ...]

with ThreadPoolExecutor(max_workers=10) as pool:
    results = list(pool.map(requests.get, urls))
```

**GIL reality**: threads release GIL during I/O syscalls → concurrent I/O works. CPU-bound threads DON'T get parallelism.

### Multiprocessing (CPU-bound)

```python
from concurrent.futures import ProcessPoolExecutor

def heavy_computation(data_chunk):
    return sum(x**2 for x in data_chunk)

chunks = [data[i::4] for i in range(4)]  # split into 4 chunks

with ProcessPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(heavy_computation, chunks))
```

**Gotcha**: each process gets a COPY of data → serialization overhead. Keep payloads small.

### Asyncio (high-concurrency I/O)

```python
import asyncio
import httpx

async def fetch_all(urls: list[str]) -> list[dict]:
    async with httpx.AsyncClient() as client:
        tasks = [client.get(url) for url in urls]
        responses = await asyncio.gather(*tasks)
        return [r.json() for r in responses]

results = asyncio.run(fetch_all(urls))
```

---

## Step 3: Common Bottlenecks & Fixes

| Bottleneck | Symptom | Fix |
|-----------|---------|-----|
| String concatenation in loop | O(n²) memory | Use `"".join(parts)` or `io.StringIO` |
| List append in loop → filter | Slow + memory | Use generator or list comprehension |
| Repeated dict/set lookups | Profiler shows `__getitem__` | Cache in local variable |
| Global variable access in hot loop | ~20% slower than local | Assign to local before loop |
| Creating objects in hot loop | GC pressure | Pre-allocate or reuse |
| `json.dumps/loads` in loop | Serialization cost | Batch or use `orjson` |
| Pandas `.iterrows()` | 100-1000x slower than vectorized | Use vectorized ops or `.apply()` |
| SQLAlchemy N+1 queries | DB round-trips | Use `joinedload()` / `selectinload()` |

### Quick wins

```python
# ❌ Slow: string concat in loop
result = ""
for item in items:
    result += str(item) + ","

# ✅ Fast: join
result = ",".join(str(item) for item in items)

# ❌ Slow: checking membership in list
if item in large_list:  # O(n)

# ✅ Fast: set lookup
large_set = set(large_list)  # O(1) lookup
if item in large_set:

# ❌ Slow: repeated attribute access
for item in items:
    self.container.data.append(item)

# ✅ Fast: local reference
append = self.container.data.append
for item in items:
    append(item)
```

---

## Step 4: Validate the Optimization

```python
import timeit

# Before
baseline = timeit.timeit(original_function, number=1000)

# After
optimized = timeit.timeit(new_function, number=1000)

speedup = baseline / optimized
print(f"Speedup: {speedup:.1f}x ({baseline:.3f}s → {optimized:.3f}s)")
```

**Rule**: if speedup < 2x and code is harder to read → don't keep the optimization.

---

## Pitfalls

| Mistake | Reality |
|---------|---------|
| "Threading will speed up my computation" | GIL prevents CPU parallelism in threads |
| "asyncio is always faster" | Only for I/O-bound; adds complexity |
| "I'll optimize this later" | Profile NOW, then decide if it matters |
| Optimizing cold code | Profile first — 90% of time is in 10% of code |
| `multiprocessing` for tiny tasks | Serialization overhead > computation |
| Premature Cython/C extension | Usually algorithmic fix is 10-100x more impactful |

---

## Related Skills

- `python-scripting` — the scripts being profiled
- `python-otel-patterns` — distributed trace spans show where time is spent across services
- `python-fastapi-patterns` — async request handling for I/O-bound web services
