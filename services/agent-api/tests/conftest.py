"""Pytest configuration for the agent-api service."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("METRICS_AUTH_TOKEN", "test-metrics-token")
os.environ.setdefault("ALLOW_IN_MEMORY_VALKEY", "1")
os.environ.setdefault("ALLOW_STUB_LANGUAGE_DETECTOR", "1")
os.environ.setdefault("ALLOW_RATE_LIMITER_BYPASS", "1")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

pytest_plugins = ["shared_data_layer.testing.conftest"]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


__all__ = []
