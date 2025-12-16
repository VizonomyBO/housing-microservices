"""Pytest configuration for the agent-api service."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import opentelemetry.trace as ot_trace
import pytest

os.environ.setdefault("METRICS_AUTH_TOKEN", "test-metrics-token")
os.environ["ALLOW_IN_MEMORY_VALKEY"] = "1"
os.environ["ALLOW_STUB_LANGUAGE_DETECTOR"] = "1"
os.environ["ALLOW_RATE_LIMITER_BYPASS"] = "1"
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("AUTH_SHARED_SECRET", "test-auth-secret")
os.environ["REDUCED_SCOPE_ENABLED"] = "1"
os.environ["REDUCED_SCOPE_USE_REAL_TOOLS"] = "0"
os.environ["REDUCED_SCOPE_DISABLE_VALKEY"] = "1"
os.environ["REDUCED_SCOPE_DISABLE_RATE_LIMITING"] = "1"

pytest_plugins = ["shared_data_layer.testing.conftest"]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture(scope="session", autouse=True)
def _default_database_url(request: pytest.FixtureRequest) -> None:
    """Ensure DATABASE_URL is set for app startup in local/test runs."""

    if os.getenv("DATABASE_URL"):
        return
    database_url = request.getfixturevalue("database_url")
    async_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    os.environ.setdefault("DATABASE_URL", async_url)


@pytest.fixture(scope="session", autouse=True)
def _reset_tracer_provider() -> None:
    """Allow tests to override the global tracer provider."""

    try:
        # Clear any previously set provider so per-test overrides take effect.
        ot_trace._TRACER_PROVIDER = None  # type: ignore[attr-defined]
        if hasattr(ot_trace, "_TRACER_PROVIDER_SET_ONCE"):
            ot_trace._TRACER_PROVIDER_SET_ONCE._done = False  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive
        pass


__all__ = []
