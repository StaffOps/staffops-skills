---
name: python-packaging
description: "Package Python projects with pyproject.toml and venvs."
version: 1.0.0
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

Modern Python packaging centered on `pyproject.toml`: dependency
declaration, virtual environments, and the difference between an
application's pinned lockfile and a library's flexible version ranges —
getting this backward is the most common packaging mistake.

## When to Use

Use when starting a new Python project, converting an old `setup.py`-based
project to modern tooling, deciding how to pin dependencies, or debugging a
"works on my machine" dependency issue.

## pyproject.toml: the modern standard

```toml
[project]
name = "myproject"
version = "1.0.0"
description = "What this project does"
requires-python = ">=3.11"
dependencies = [
    "requests>=2.31,<3",
    "click>=8.1",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.4", "mypy>=1.10"]

[project.scripts]
mytool = "myproject.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

`pyproject.toml` (PEP 621) replaced the older combination of `setup.py` +
`setup.cfg` as the single source of project metadata — a new project should
start here directly rather than with the legacy files. `[build-system]`
names which tool actually builds the package (Hatchling, setuptools,
Poetry's own backend, PDM); the choice mostly doesn't matter for a simple
project, but must be consistent with whichever tool manages the project day
to day.

## Virtual environments

```bash
python3 -m venv .venv                  # create
source .venv/bin/activate               # activate (POSIX)
.venv\Scripts\activate                   # activate (Windows)
deactivate                                # leave it

pip install -e ".[dev]"                  # editable install of the current project + dev extras
```

**Every project needs an isolated environment** — installing dependencies
into the system Python risks version conflicts between unrelated projects
sharing the same interpreter, and on many modern Linux distributions is
outright blocked (`externally-managed-environment`) specifically to prevent
this. `.venv` as the directory name is a strong, widely-recognized
convention — add it to `.gitignore` immediately, since it should never be
committed.

`pip install -e .` (editable/development mode) installs the project such
that changes to the source take effect immediately without reinstalling —
essential during active development, since the alternative (a normal,
non-editable install) requires reinstalling after every code change to see
its effect.

## Applications vs libraries: pin differently, deliberately

This distinction is the single most consequential decision in dependency
management, and getting it backward causes real problems in both
directions.

**An application** (something deployed and run, not imported by other
code) should pin **exact** versions, via a lockfile, for reproducibility —
the same deployment artifact should behave identically today and in six
months:

```
# requirements.txt (generated, not hand-written)
requests==2.31.0
click==8.1.7
urllib3==2.2.1
```

```bash
pip freeze > requirements.txt        # capture exact versions from a working environment
pip install -r requirements.txt      # reproduce it exactly, elsewhere
```

**A library** (published for other projects to depend on) should declare
**flexible ranges** in `pyproject.toml`, not exact pins — pinning exactly in
a library forces every consumer of that library into the same exact
version, which becomes an unsatisfiable conflict the moment two libraries a
project depends on pin *different* exact versions of a shared dependency:

```toml
dependencies = [
    "requests>=2.31,<3",   # a range: compatible with anything in this window
]
```

The rule of thumb: **pin exactly at the point of deployment; range flexibly
at the point of declaration.** A library's `pyproject.toml` declares ranges;
an application's separately-generated lockfile pins exact versions for its
own deployment.

## Modern dependency managers

```bash
# uv -- fast, increasingly the default recommendation
uv venv
uv pip install -e ".[dev]"
uv lock                          # generates uv.lock, a full reproducible lockfile
uv sync                          # installs exactly what the lockfile specifies

# Poetry -- an alternative, all-in-one tool
poetry init
poetry add requests
poetry install
```

`uv` (from Astral, the Ruff authors) has become a common recommendation
specifically for its speed — dependency resolution and installs that take
`pip` tens of seconds often complete in a fraction of a second with `uv`,
which matters meaningfully in CI where this happens on every run. Both `uv`
and Poetry produce a full lockfile (`uv.lock` / `poetry.lock`) covering
*every* transitive dependency with an exact, hash-verified version — a
stronger reproducibility guarantee than a hand-maintained
`requirements.txt`.

## Version specifiers

| Specifier | Meaning |
| --- | --- |
| `==2.31.0` | Exactly this version |
| `>=2.31` | This version or newer, unbounded |
| `>=2.31,<3` | A range — the conventional way to allow minor/patch updates but block a breaking major version |
| `~=2.31` | "Compatible release" — equivalent to `>=2.31,<2.32` (locks the minor version) |
| `!=2.31.5` | Exclude a specific known-bad version |

`>=2.31,<3` is the generally preferred form for a library dependency: it
follows the common (though not universal) convention that a major version
bump signals a breaking change, so allowing anything up to the next major
version captures compatible improvements while blocking a version likely to
break the dependent code.

## Reproducibility: the actual goal

```bash
pip install pip-audit
pip-audit                          # check installed packages against known vulnerability databases

pip list --outdated                # what has newer versions available
```

A lockfile's purpose is that **the same input produces the same
environment, every time, on every machine** — a `requirements.txt`
generated with `pip freeze` achieves this for direct dependencies but
doesn't capture the guarantee as strongly as a hash-verified lockfile
(`uv.lock`, `poetry.lock`), which also pins every *transitive* dependency
and can verify package integrity against a known hash, protecting against a
compromised or altered package showing up under the same version number.

## Building and publishing

```bash
python -m build              # produces dist/*.whl and dist/*.tar.gz
python -m twine upload dist/*   # publish to PyPI (or an internal index)

uv build                      # equivalent, if using uv
```

A wheel (`.whl`) is a pre-built, platform-specific (or pure-Python
platform-independent) distribution format — installing from a wheel is
faster than from a source distribution (`.tar.gz`) because it skips any
build step at install time. Publish both when the project has no compiled
extensions; a pure-Python wheel is universal across platforms.

## Namespace/import structure

```
myproject/
├── pyproject.toml
├── src/
│   └── myproject/
│       ├── __init__.py
│       ├── cli.py
│       └── core.py
└── tests/
    └── test_core.py
```

The `src/` layout (package code under `src/myproject/` rather than a bare
`myproject/` at the repo root) is the modern recommendation — it prevents a
specific, confusing class of bug where the *local, uninstalled* source gets
imported accidentally during testing instead of the actually-installed
package, because a bare top-level package directory is importable directly
from the repo root without an install at all.

## Pitfalls

- **Pinning exact versions in a library's `pyproject.toml`** — forces every
  consumer into that exact version, causing unsatisfiable conflicts for
  anyone depending on two libraries with different exact pins of a shared
  dependency.
- **Not pinning exactly for an application's deployment** — "works on my
  machine" but not reproducibly elsewhere, because a range allowed a newer,
  behaviorally different version to be installed.
- **Installing dependencies into the system Python** — version conflicts
  across unrelated projects, and blocked outright on many modern
  distributions.
- **Committing `.venv/` to version control** — large, platform-specific,
  and unnecessary; it's fully reproducible from the lockfile/dependency
  declarations.
- **A bare top-level package directory instead of `src/` layout** — risks
  accidentally testing against uninstalled local source rather than the
  actual installed package.
- **Hand-editing a generated lockfile** — the next regeneration silently
  overwrites the manual edit; change the source declaration and regenerate
  instead.

## Reference

- `python-scripting` — the code being packaged
- `python-cli-tools` — the `[project.scripts]` entry point pattern in depth
- `python-testing` — testing an installed/editable package correctly
