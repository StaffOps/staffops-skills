# Python Profiling Cheat Sheet

Quick-reference commands for profiling Python code.

## CPU Profiling

```bash
# cProfile — function-level (built-in)
python -m cProfile -s cumulative script.py
python -m cProfile -s tottime script.py        # time in function itself
python -m cProfile -o profile.stats script.py  # save for analysis

# Analyze saved profile
python -c "import pstats; pstats.Stats('profile.stats').sort_stats('cumulative').print_stats(20)"

# line_profiler — line-by-line (pip install line-profiler)
# Add @profile decorator to suspect function, then:
kernprof -l -v script.py

# py-spy — sampling profiler (no code changes, pip install py-spy)
py-spy record -o profile.svg -- python script.py   # flamegraph
py-spy top -- python script.py                      # live top-like view
py-spy dump --pid <PID>                             # attach to running process
```

## Memory Profiling

```bash
# memory_profiler — line-by-line (pip install memory-profiler)
# Add @profile decorator, then:
python -m memory_profiler script.py

# tracemalloc — stdlib, shows allocations
python -c "
import tracemalloc
tracemalloc.start()
# ... your code ...
snapshot = tracemalloc.take_snapshot()
for stat in snapshot.statistics('lineno')[:10]:
    print(stat)
"

# objgraph — find reference leaks (pip install objgraph)
python -c "
import objgraph
objgraph.show_most_common_types(limit=10)
objgraph.show_growth()
"
```

## Micro-benchmarks

```bash
# timeit from CLI
python -m timeit -n 10000 "'-'.join(str(i) for i in range(100))"
python -m timeit -n 10000 "'-'.join(map(str, range(100)))"

# Compare two implementations
python -c "
import timeit
t1 = timeit.timeit('list(range(1000))', number=100000)
t2 = timeit.timeit('[i for i in range(1000)]', number=100000)
print(f'range: {t1:.3f}s, comprehension: {t2:.3f}s, ratio: {t1/t2:.2f}x')
"
```

## Docker-based (no local install)

```bash
# cProfile via Docker
docker run --rm -v "$(pwd):/app" -w /app python:3.11-slim \
  python -m cProfile -s cumulative app/main.py

# line_profiler via Docker
docker run --rm -v "$(pwd):/app" -w /app python:3.11-slim sh -c \
  "pip install -q line-profiler && kernprof -l -v app/main.py"

# memory_profiler via Docker
docker run --rm -v "$(pwd):/app" -w /app python:3.11-slim sh -c \
  "pip install -q memory-profiler && python -m memory_profiler app/main.py"
```

## GIL Decision Quick-Reference

| Bottleneck | Solution | Why |
|-----------|----------|-----|
| Network I/O (many connections) | `asyncio` | Non-blocking, single thread, high concurrency |
| Network I/O (few connections) | `ThreadPoolExecutor` | Simple, GIL released during I/O |
| Disk I/O | `ThreadPoolExecutor` | GIL released during read/write syscalls |
| CPU computation | `ProcessPoolExecutor` | Bypasses GIL entirely (separate processes) |
| NumPy/pandas math | Already parallel | C extensions release GIL internally |
| Single hot loop | Rewrite in C/Cython/Rust | Or vectorize with NumPy |
