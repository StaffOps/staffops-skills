"""Shared test fixtures — auto-discovered by pytest (no import needed)."""
from __future__ import annotations

import pytest


# --- Value fixtures ---

@pytest.fixture
def sample_config():
    """Minimal valid config for testing."""
    return {
        "host": "localhost",
        "port": 8080,
        "debug": False,
    }


# --- Factory fixtures ---

@pytest.fixture
def make_user():
    """Factory: create user dicts with optional overrides."""
    def _make(name="Alice", email="alice@test.com", role="viewer"):
        return {"name": name, "email": email, "role": role, "active": True}
    return _make


# --- Yield fixtures (setup + teardown) ---

@pytest.fixture
def temp_db(tmp_path):
    """SQLite DB that auto-closes after test."""
    import sqlite3
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO items (name) VALUES (?)", ("seed",))
    conn.commit()
    yield conn
    conn.close()


# --- Environment fixtures ---

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Ensure tests don't leak env vars."""
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


# --- Async fixtures (requires pytest-asyncio) ---

@pytest.fixture
async def async_client():
    """Example httpx async client fixture."""
    import httpx
    async with httpx.AsyncClient(base_url="http://test") as client:
        yield client
