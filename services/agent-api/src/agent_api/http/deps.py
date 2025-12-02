"""Dependency functions shared by FastAPI routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import HTTPException, Request, status
from shared_data_layer.db.session import DatabaseSessionManager
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.streaming import ChatRunnerProtocol, StreamSettings, UnconfiguredChatRunner
from agent_api.settings import Settings, load_settings
from cache import InMemoryValkeyClient, ValkeyCacheClientProtocol
from telemetry import CacheObservability, MetricsRegistry, get_metrics_registry

_RUNNER_STATE: dict[str, ChatRunnerProtocol] = {"runner": UnconfiguredChatRunner()}
_STREAM_SETTINGS = StreamSettings()
_CACHE_CLIENT_STATE: dict[str, ValkeyCacheClientProtocol | None] = {"client": None}


async def get_request_context(request: Request) -> RequestContext:
    """Extract correlation headers and memoize them on the request state."""

    request_id = (
        getattr(request.state, "request_id", None)
        or request.headers.get("Viz-Request-Id")
        or f"viz-{uuid4().hex}"
    )
    traceparent = request.headers.get("Traceparent")
    idempotency_key = request.headers.get("Idempotency-Key")
    headers = dict(request.headers.items())
    context = RequestContext(
        request_id=request_id,
        traceparent=traceparent,
        idempotency_key=idempotency_key,
        headers=headers,
    )
    request.state.request_id = context.request_id
    return context


async def get_auth_context(request: Request) -> AuthContext:
    """Stubbed auth dependency that extracts the bearer subject when available."""

    header = request.headers.get("Authorization")
    if header and header.startswith("Bearer "):
        token = header.split(" ", 1)[1]
        return AuthContext(user_id=f"user:{token[:8]}")
    return AuthContext(user_id=None)


def get_chat_runner() -> ChatRunnerProtocol:
    return _RUNNER_STATE["runner"]


def set_chat_runner(runner: ChatRunnerProtocol) -> None:
    _RUNNER_STATE["runner"] = runner


def get_stream_settings() -> StreamSettings:
    return _STREAM_SETTINGS


def get_cache_client(request: Request | None = None) -> ValkeyCacheClientProtocol:
    if request is not None and hasattr(request, "app"):
        client = getattr(request.app.state, "valkey_client", None)
        if client is not None:
            return client
    if _CACHE_CLIENT_STATE["client"] is None:
        _CACHE_CLIENT_STATE["client"] = InMemoryValkeyClient()
    return _CACHE_CLIENT_STATE["client"]


def set_cache_client(client: ValkeyCacheClientProtocol) -> None:
    _CACHE_CLIENT_STATE["client"] = client


def get_settings(request: Request | None = None) -> Settings:
    """Return the cached Settings instance stored on the app state."""

    if request is None or not hasattr(request, "app"):
        # Fallback primarily used in tests that bypass FastAPI state.
        return load_settings()
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        settings = load_settings()
        request.app.state.settings = settings
    return settings


def get_metrics_registry_dep(request: Request) -> MetricsRegistry:
    registry = getattr(request.app.state, "metrics_registry", None)
    if registry is None:
        registry = get_metrics_registry()
        request.app.state.metrics_registry = registry
    return registry


def get_cache_observability(request: Request) -> CacheObservability:
    observability = getattr(request.app.state, "cache_observability", None)
    if observability is None:
        observability = CacheObservability(metrics=get_metrics_registry_dep(request))
        request.app.state.cache_observability = observability
    return observability


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    if not getattr(request.app.state, "db_initialized", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database session manager is not configured",
        )
    async with DatabaseSessionManager.session() as session:
        yield session


async def maybe_get_db_session(request: Request) -> AsyncIterator[AsyncSession | None]:
    if not getattr(request.app.state, "db_initialized", False):
        yield None
        return
    async with DatabaseSessionManager.session() as session:
        yield session


__all__ = [
    "get_auth_context",
    "get_cache_client",
    "get_cache_observability",
    "get_chat_runner",
    "get_db_session",
    "get_metrics_registry_dep",
    "get_request_context",
    "get_settings",
    "get_stream_settings",
    "maybe_get_db_session",
    "set_cache_client",
    "set_chat_runner",
]
