---
name: python-packaging
description: "Use when creating a new Python project with pyproject.toml, managing dependencies, configuring virtual environments, or publishing packages. Covers the complete pyproject.toml, src layout, dependency pinning strategy, and Docker build patterns."
version: 1.1.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, packaging, pyproject-toml, venv, pip, dependencies]
    category: development
    related_skills: [python-scripting, python-cli-tools, python-testing]
---

# Python Packaging

Modern Python packaging with `pyproject.toml`. One file to rule them all: metadata, dependencies, tool config.

## When to Use

- Starting a new Python project
- Converting old `setup.py` / `setup.cfg` to modern tooling
- Deciding how to pin dependencies (app vs library)
- Packaging a CLI tool for `pip install`
- Setting up the `src/` layout correctly

## When NOT to Use

- Single throwaway script → just use `python-scripting` skeleton
- Notebook exploration → Jupyter + `requirements.txt` is fine
- Go/Rust/C# projects → language-native packaging

---

## Project Layout (src layout — recommended)

```
myproject/
├── src/
│   └── mypackage/
│       ├── __init__.py
│       ├── core.py
│       └── cli.py
├── tests/
│   ├── conftest.py
│   └── test_core.py
├── pyproject.toml
├── README.md
└── .gitignore
```

**Why src layout?** Prevents accidentally importing uninstalled code from the working directory. Tests always run against the *installed* package.

---

## Complete pyproject.toml (copy-paste ready)

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mypackage"
version = "0.1.0"
description = "What this package does"
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
authors = [
    {name = "Your Name", email = "you@example.com"},
]

dependencies = [
    "httpx>=0.27,<1",
    "pydantic>=2.0,<3",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.5",
    "mypy>=1.10",
]

[project.scripts]
mycommand = "mypackage.cli:main"

[project.urls]
Repository = "https://gitlab.example.com/team/mypackage"

# --- Tool configs (all in one file) ---

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "--cov=src --cov-report=term-missing --cov-fail-under=90"

[tool.coverage.run]
source = ["src"]
branch = true

[tool.coverage.report]
fail_under = 90
show_missing = true

[tool.ruff]
target-version = "py311"
line-length = 100
src = ["src"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.11"
strict = true
```

---

## Dependency Strategy: Apps vs Libraries

| | Application (deployed) | Library (pip-installable) |
|--|--|--|
| Pin style | **Exact** (`==`) in lockfile | **Range** (`>=x,<y`) in pyproject.toml |
| File | `requirements.txt` (generated) | `pyproject.toml` `[project.dependencies]` |
| Why | Reproducible deploys | Flexible for consumers |
| Generate lock | `pip freeze > requirements.txt` | Not applicable |

### For applications (deploy to K8s):

```bash
# Generate lockfile
pip install -e . && pip freeze > requirements.txt

# Dockerfile uses the lockfile
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

### For libraries:

```toml
# Flexible ranges — let consumers resolve
dependencies = [
    "requests>=2.28,<3",
    "click>=8.0",
]
```

---

## Virtual Environment Commands

```bash
# Create
python -m venv .venv

# Activate
source .venv/bin/activate      # Linux/macOS
.venv\Scripts\activate         # Windows

# Install in editable mode (for development)
pip install -e ".[dev]"

# Deactivate
deactivate
```

### Docker-based (no local venv needed)

```bash
# Install + run tests
docker run --rm -v "$(pwd):/app" -w /app python:3.11-slim sh -c \
  "pip install -e '.[dev]' -q && pytest"

# Build wheel
docker run --rm -v "$(pwd):/app" -w /app python:3.11-slim sh -c \
  "pip install build -q && python -m build"
```

---

## Entry Points (CLI commands)

```toml
# In pyproject.toml
[project.scripts]
mycommand = "mypackage.cli:main"
```

```python
# src/mypackage/cli.py
def main():
    """Entry point for `mycommand`."""
    print("Hello from mycommand!")
```

After `pip install -e .`, the command `mycommand` is available in PATH.

---

## Publishing (to private PyPI or Harbor)

```bash
# Build
python -m build  # creates dist/mypackage-0.1.0.tar.gz + .whl

# Upload to private index
twine upload --repository-url https://pypi.example.com/simple/ dist/*

# Install from private index
pip install mypackage --index-url https://pypi.example.com/simple/
```

---

## Pitfalls

| Mistake | Fix |
|---------|-----|
| No `src/` layout | Tests import uninstalled code → works locally, fails in CI |
| `setup.py` still | Migrate to `pyproject.toml` (it's the standard since 2023) |
| `pip install .` without `-e` in dev | Changes require reinstall each time |
| Forgetting `[dev]` extras | Tests can't run: pytest/ruff not installed |
| `requirements.txt` as source of truth for a lib | Use pyproject.toml ranges instead |
| Version only in `pyproject.toml` but code reads `__version__` | Use `importlib.metadata.version("pkg")` |

---

## Related Skills

- `python-scripting` — single-file scripts before they need packaging
- `python-cli-tools` — Click/Typer on top of packaged entry points
- `python-testing` — test config lives in pyproject.toml too
