"""Integration tests for the production Valkey client wrapper."""

from __future__ import annotations

import asyncio
import os
import socket
import time
from typing import cast

import pytest
from docker.errors import DockerException
from testcontainers.core.container import DockerContainer

from cache.valkey_async_client import ValkeyAsyncClient
from config import ValkeySettings
from telemetry import CacheObservability

pytestmark = pytest.mark.asyncio(loop_scope="session")


class _StubMetrics:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, str]] = []

    def record_cache_event(
        self,
        *,
        event: str,
        namespace: str,
        route: str | None,
        latency_seconds: float | None = None,
        ttl_seconds: float | None = None,
    ) -> None:
        self.events.append((event, namespace, route or "none"))


class _StubObservability:
    def __init__(self) -> None:
        self.metrics = _StubMetrics()


def _wait_for_port(host: str, port: int, timeout: float = 15.0) -> None:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError(f"Valkey container on {host}:{port} failed to start")


@pytest.fixture(scope="module")
def _redis_image() -> str:
    return os.getenv("VALKEY_TEST_IMAGE", "valkey/valkey:8.0")


@pytest.fixture(scope="module")
def valkey_container(_redis_image):
    if os.getenv("SKIP_VALKEY_TESTS") == "1":
        pytest.skip("Valkey integration tests disabled via env")

    last_error: Exception | None = None
    candidates = [_redis_image]
    if _redis_image != "redis:7.2":
        candidates.append("redis:7.2")

    for image in candidates:
        try:
            with DockerContainer(image).with_exposed_ports(6379) as container:
                host = container.get_container_host_ip()
                port = int(container.get_exposed_port(6379))
                _wait_for_port(host, port)
                yield f"redis://{host}:{port}/0"
                return
        except (DockerException, FileNotFoundError) as exc:  # pragma: no cover - env specific
            last_error = exc
            continue

    pytest.skip(f"Docker not available for Valkey tests: {last_error}")


@pytest.fixture(scope="module")
def valkey_settings(valkey_container: str) -> ValkeySettings:
    return ValkeySettings(url=valkey_container, default_ttl_seconds=2, max_connections=8)


@pytest.fixture
async def valkey_client(valkey_settings: ValkeySettings):
    client = ValkeyAsyncClient.from_settings(valkey_settings)
    try:
        yield client
    finally:
        await client.close()


async def test_valkey_client_roundtrip(valkey_client: ValkeyAsyncClient):
    await valkey_client.set("agent:test", "payload", ttl_seconds=5)
    result = await valkey_client.get("agent:test")
    assert result == b"payload"


async def test_valkey_ttl_expires(valkey_client: ValkeyAsyncClient):
    await valkey_client.set("agent:ttl", b"1", ttl_seconds=1)
    await asyncio.sleep(1.2)
    assert await valkey_client.get("agent:ttl") is None


async def test_tag_events_emit_metrics(valkey_settings: ValkeySettings):
    observer_stub = _StubObservability()
    observer = cast(CacheObservability, observer_stub)
    client = ValkeyAsyncClient.from_settings(valkey_settings, observability=observer)
    try:
        await client.tag_hit("agent:key")
        await client.tag_miss("agent:key", reason="not_found")
    finally:
        await client.close()
    assert observer_stub.metrics.events[0][0] == "hit"
    assert observer_stub.metrics.events[1][0] == "miss"
