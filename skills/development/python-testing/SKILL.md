---
name: python-testing
description: "Use when writing pytest test suites, designing fixtures, mocking external dependencies, parametrizing test cases, or measuring coverage. Covers conftest patterns, factory fixtures, async testing, Docker-based coverage commands, and the ≥90% gate."
version: 1.1.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, pytest, testing, fixtures, mocking, coverage, tdd]
    category: development
    related_skills: [python-scripting, python-packaging, python-performance]
---

# Python Testing

Effective `pytest` usage: fixtures, parametrize, mocking, async tests, and the ≥90% coverage gate.

## When to Use

- Writing tests for new code or existing untested code
- Designing shared setup/teardown via fixtures
- Mocking external services (HTTP, DB, queues)
- Reducing test duplication with parametrize
- Measuring and enforcing coverage thresholds

## When NOT to Use

- Shell scripts or Makefiles → use `bats` or `shunit2`
- Go/C#/.NET → use language-native test frameworks
- Integration/E2E that requires a running cluster → use dedicated CI stage, not this pattern

---

## Quick Start (Docker — no local Python)

```bash
# Run tests with coverage (fail under 90%)
docker run --rm -v "$(pwd):/app" -w /app python:3.11-slim sh -c \
  "pip install -e '.[dev]' -q && pytest --cov=src --cov-fail-under=90 --cov-report=term-missing"

# Run only unit tests
docker run --rm -v "$(pwd):/app" -w /app python:3.11-slim sh -c \
  "pip install -e '.[dev]' -q && pytest tests/unit -v"

# Generate HTML coverage report
docker run --rm -v "$(pwd):/app" -w /app python:3.11-slim sh -c \
  "pip install -e '.[dev]' -q && pytest --cov=src --cov-report=html && echo 'Open htmlcov/index.html'"
```

---

## Project Layout

```
myproject/
├── src/mypackage/
│   ├── __init__.py
│   └── core.py
├── tests/
│   ├── conftest.py          # shared fixtures
│   ├── unit/
│   │   └── test_core.py
│   └── integration/
│       └── test_api.py
└── pyproject.toml
```

---

## Fixtures — The 5 Patterns You Need

### 1. Simple value fixture

```python
# tests/conftest.py
import pytest

@pytest.fixture
def sample_user():
    return {"name": "Alice", "email": "alice@example.com"}
```

### 2. Factory fixture (create N items with variations)

```python
@pytest.fixture
def make_user():
    def _make(name="Alice", role="viewer"):
        return {"name": name, "role": role, "active": True}
    return _make

def test_admin_access(make_user):
    admin = make_user(name="Bob", role="admin")
    assert admin["role"] == "admin"
```

### 3. Setup + teardown (yield fixture)

```python
@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    yield conn
    conn.close()
```

### 4. Scoped fixture (expensive setup, shared across module)

```python
@pytest.fixture(scope="module")
def redis_client():
    """One Redis connection per test module."""
    client = redis.Redis(host="localhost", port=6379, db=15)
    yield client
    client.flushdb()
    client.close()
```

### 5. Autouse fixture (applies to all tests in scope)

```python
@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
```

---

## Parametrize — Avoid Duplicating Tests

```python
@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("world", "WORLD"),
    ("", ""),
    ("123", "123"),
])
def test_uppercase(input, expected):
    assert input.upper() == expected
```

### Parametrize with IDs (readable output)

```python
@pytest.mark.parametrize("status,expected_ok", [
    pytest.param(200, True, id="success"),
    pytest.param(404, False, id="not-found"),
    pytest.param(500, False, id="server-error"),
])
def test_is_ok(status, expected_ok):
    assert is_ok_status(status) == expected_ok
```

---

## Mocking — Patch Where It's LOOKED UP

```python
# src/mypackage/service.py
from mypackage.client import fetch_data  # ← this is where it's looked up

def process():
    data = fetch_data()
    return transform(data)
```

```python
# tests/unit/test_service.py
from unittest.mock import patch, MagicMock

# ✅ CORRECT — patch where it's imported
@patch("mypackage.service.fetch_data")
def test_process(mock_fetch):
    mock_fetch.return_value = {"key": "value"}
    result = process()
    assert result == expected_output
    mock_fetch.assert_called_once()

# ❌ WRONG — patching the definition site
@patch("mypackage.client.fetch_data")  # won't affect service.py's import
def test_process_wrong(mock_fetch):
    ...
```

### Mock with side_effect (simulate errors)

```python
@patch("mypackage.service.fetch_data")
def test_process_retries_on_error(mock_fetch):
    mock_fetch.side_effect = [ConnectionError("timeout"), {"key": "value"}]
    result = process_with_retry()
    assert mock_fetch.call_count == 2
```

---

## Async Tests (pytest-asyncio)

```python
import pytest

@pytest.mark.asyncio
async def test_async_fetch(httpx_mock):
    httpx_mock.add_response(json={"status": "ok"})
    result = await my_async_function()
    assert result["status"] == "ok"
```

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"  # all async tests auto-detected
```

---

## Coverage Commands Cheat Sheet

| Command | Purpose |
|---------|---------|
| `pytest --cov=src` | Basic coverage |
| `pytest --cov=src --cov-fail-under=90` | **Fail if <90%** |
| `pytest --cov=src --cov-report=term-missing` | Show uncovered lines |
| `pytest --cov=src --cov-report=html` | HTML report |
| `pytest --cov=src --cov-branch` | Branch coverage (stricter) |
| `pytest --cov=src --cov-report=xml` | For CI (Cobertura format) |

### pyproject.toml coverage config

```toml
[tool.coverage.run]
source = ["src"]
branch = true
omit = ["*/tests/*", "*/__main__.py"]

[tool.coverage.report]
fail_under = 90
show_missing = true
skip_covered = true
```

---

## Markers — Organize Test Runs

```python
# pytest.ini or pyproject.toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (deselect with '-m not slow')",
    "integration: requires external services",
]
```

```bash
pytest -m "not slow"           # skip slow tests
pytest -m integration          # only integration
pytest --co -q                 # list tests without running (dry run)
```

---

## Pitfalls

| Mistake | Fix |
|---------|-----|
| Patching where defined, not where looked up | Patch the import site |
| Only asserting "no crash" | Assert specific expected values |
| Loop inside test function | Use `@pytest.mark.parametrize` |
| Only happy-path tests | Test error paths and edge cases |
| Mutable shared fixture | Use `scope="function"` (default) or deep-copy |
| 100% coverage = correct | Coverage measures execution, not correctness |

---

## Related Skills

- `python-scripting` — the code being tested
- `python-packaging` — `src/` layout and `[project.optional-dependencies] dev`
- `python-performance` — profiling to find what to optimize, then test the optimization
