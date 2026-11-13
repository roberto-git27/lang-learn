"""
Shared pytest setup.

`app.config.Settings` is instantiated at import time (`app/config.py`) and
requires `ANTHROPIC_API_KEY` with no default — importing any `app.*` module
without it set would crash test collection before a single test runs. These
env vars must be set before the first `app` import, so this file has no
other imports above them and relies on conftest.py being loaded by pytest
before test modules.
"""
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
