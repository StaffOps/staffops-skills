---
name: python-testing
description: "Write pytest fixtures, mocks and parametrized tests."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, pytest, testing, fixtures, mocking, coverage, tdd]
    category: development
    related_skills: [python-scripting, python-packaging]
---
# Python Testing

Effective `pytest` usage: fixtures for setup/teardown, parametrization to
avoid duplicating near-identical test functions, mocking external
dependencies correctly, and what to actually assert to make a failing test
communicate the problem clearly.

## When to Use

Use when writing tests for a new function, deciding how to test code that
calls an external service, reducing duplication across similar test cases,
or diagnosing a flaky or unclear test failure.

## The basics

```python
def add(a: int, b: int) -> int:
    return a + b

def test_add():
    assert add(2, 3) == 5

def test_add_negative():
    assert add(-1, -1) == -2
```

```bash
pytest                        # run everything discovered under the current directory
pytest test_math.py            # one file
pytest test_math.py::test_add   # one specific test
pytest -k "add"                  # tests whose name matches a substring/expression
pytest -v                         # verbose: show each test's name and result
pytest -x                          # stop after the FIRST failure
pytest --lf                         # re-run only the tests that failed LAST time
```

`pytest` needs no test-class boilerplate — a bare function starting with
`test_` and a plain `assert` is a complete, valid test. This is a deliberate
simplification over `unittest`'s class-based, `self.assertEqual(...)` style,
which remains supported but is no longer the idiomatic starting point for
new code.

## Fixtures: setup and teardown

```python
import pytest

@pytest.fixture
def tmp_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("key: value\n")
    return config_file

def test_reads_config(tmp_config):
    content = tmp_config.read_text()
    assert "key: value" in content
```

`tmp_path` is a **built-in** pytest fixture providing a unique temporary
directory per test, automatically cleaned up afterward — the direct
equivalent of Bash's `mktemp -d` plus a `trap ... EXIT` cleanup, but without
needing to write the cleanup logic at all.

```python
@pytest.fixture
def db_connection():
    conn = create_connection()
    yield conn                 # the TEST runs at this point
    conn.close()                # this runs AFTER the test, success or failure
```

`yield` (instead of `return`) inside a fixture splits it into setup (before
`yield`) and teardown (after `yield`) — the teardown code runs even if the
test itself raises an exception, which is what makes this the reliable
place for cleanup rather than hoping the test remembers to clean up after
itself.

```python
@pytest.fixture(scope="session")   # created ONCE per test session, not per test
def expensive_resource():
    return set_up_expensive_thing()
```

Fixture `scope` (`function` — the default, `class`, `module`, `session`)
controls how often it's recreated. Use a broader scope for something
genuinely expensive to set up and safe to share across tests (a database
container, a compiled resource) — but be cautious: a shared fixture that
tests can mutate creates order-dependence between tests, one of the most
common sources of flaky test suites.

## Parametrization: one test, many cases

```python
import pytest

@pytest.mark.parametrize("a,b,expected", [
    (2, 3, 5),
    (-1, -1, -2),
    (0, 0, 0),
    (100, -50, 50),
])
def test_add(a, b, expected):
    assert add(a, b) == expected
```

This runs as **four independent test cases**, each individually reported
(pass/fail) — far better than a single test function looping over a list of
cases internally, where one failing case can obscure the others (the loop
stops at the first assertion failure) and the failure report doesn't
identify *which* case failed without extra work.

```python
@pytest.mark.parametrize("input_value,expected_error", [
    ("", ValueError),
    (None, TypeError),
    (-1, ValueError),
])
def test_validate_raises(input_value, expected_error):
    with pytest.raises(expected_error):
        validate(input_value)
```

## Mocking external dependencies

```python
from unittest.mock import patch, MagicMock

def fetch_user(user_id: int) -> dict:
    response = requests.get(f"https://api.example.com/users/{user_id}")
    response.raise_for_status()
    return response.json()

def test_fetch_user():
    with patch("mymodule.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"id": 1, "name": "Alice"}
        mock_get.return_value.raise_for_status.return_value = None

        result = fetch_user(1)

        assert result == {"id": 1, "name": "Alice"}
        mock_get.assert_called_once_with("https://api.example.com/users/1")
```

**Patch where the name is looked up, not where it's defined** — `patch(
"mymodule.requests.get")`, referencing the module *under test*'s import of
`requests`, not `patch("requests.get")` referencing the original library
directly. Python resolves `requests.get` inside `mymodule` through
`mymodule`'s own namespace at call time, so patching the original library
object doesn't affect what `mymodule` actually calls — this is the single
most common mocking mistake, and it produces a mock that's silently never
actually used, with the test still passing for the wrong reason (the real
network call happens, or fails, uncontrolled) or failing confusingly.

`mock_get.assert_called_once_with(...)` verifies not just that the mocked
function produced the expected downstream result, but that it was called
correctly in the first place — asserting only on the *outcome* can miss a
bug where the function was called with wrong arguments but coincidentally
still produced a passing result.

## pytest-mock: a cleaner fixture-based alternative

```python
def test_fetch_user(mocker):
    mock_get = mocker.patch("mymodule.requests.get")
    mock_get.return_value.json.return_value = {"id": 1, "name": "Alice"}

    result = fetch_user(1)

    assert result == {"id": 1, "name": "Alice"}
```

The `mocker` fixture (from the `pytest-mock` plugin) wraps `unittest.mock`
with automatic cleanup after each test — avoids needing the `with patch(...)
as ...:` context manager block explicitly, and is idiomatic in a codebase
already using pytest fixtures elsewhere.

## What to actually assert

```python
# Weak: only confirms it didn't crash.
def test_process():
    result = process(data)
    assert result is not None

# Strong: confirms the SPECIFIC expected behavior.
def test_process():
    result = process(data)
    assert result.status == "success"
    assert len(result.items) == 3
    assert result.items[0].id == "abc"
```

A test that only checks "didn't crash" or "returned something" passes even
when the actual logic is wrong — assert on the *specific* expected values, not
just their presence. When a test's assertions are precise, a failure message
communicates exactly what went wrong without needing to add a debugger or
extra print statements to investigate further.

## Testing exceptions and edge cases

```python
def test_raises_on_invalid_input():
    with pytest.raises(ValueError, match="must be positive"):
        validate(-1)

def test_empty_input():
    assert process([]) == []

def test_single_item():
    assert process([1]) == [1]
```

The failure paths and edge cases (empty input, a single item where the code
might assume multiple, exactly the boundary of a range check) are where
real bugs concentrate — a test suite that only covers the straightforward
success path misses most of what's actually worth testing. `match=` on
`pytest.raises` additionally verifies the exception's *message*, not just
its type, catching a case where the right exception type is raised for the
wrong underlying reason.

## Coverage

```bash
pip install pytest-cov
pytest --cov=mypackage --cov-report=term-missing
```

```
Name                 Stmts   Miss  Cover   Missing
--------------------------------------------------
mypackage/core.py       45      3    93%   67-69
```

Coverage percentage is a **floor indicator, not a quality metric** — 100%
line coverage means every line executed at least once during the test run,
not that every meaningful behavior or edge case was actually verified. It's
most useful for finding code that has *zero* test exposure (worth
investigating why) rather than as a target to optimize toward for its own
sake.

## Test organization

```
tests/
├── conftest.py          # fixtures shared across multiple test files
├── unit/
│   └── test_core.py       # fast, no external dependencies
└── integration/
    └── test_api.py         # slower, may hit a real (test) database/service
```

```python
# conftest.py
import pytest

@pytest.fixture
def sample_data():
    return {"key": "value"}
```

`conftest.py` fixtures are automatically available to every test file in
the same directory and below, without an explicit import — this is how
shared setup gets reused across a test suite without manual wiring.

```bash
pytest tests/unit                 # fast feedback loop during development
pytest tests/integration -v        # run separately, e.g. in a later CI stage
```

Separating fast unit tests from slower integration tests (by directory, or
via `@pytest.mark.slow` and `pytest -m "not slow"`) keeps the everyday
development feedback loop fast while still running the full suite in CI.

## Pitfalls

- **Patching where a name is defined instead of where it's looked up** — a
  mock that silently does nothing; the most common mocking mistake.
- **Asserting only that a function "didn't crash"** — misses actual logic
  bugs; assert on specific expected values.
- **A loop over test cases inside one test function** instead of
  `@pytest.mark.parametrize` — obscures which case failed and stops at the
  first failure.
- **Only testing the happy path** — the failure paths and edge cases are
  where bugs actually concentrate.
- **A shared, mutable fixture with broad scope** — creates order-dependence
  between tests and flaky failures depending on run order.
- **Treating 100% coverage as proof of correctness** — it measures
  execution, not verification; a line can execute with no meaningful
  assertion about its behavior.

## Reference

- `python-scripting` — the code typically being tested
- `python-packaging` — the `src/` layout that avoids a common
  uninstalled-vs-installed import confusion during testing
