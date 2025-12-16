"""Dependency functions shared by FastAPI routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, HTTPException, Request, status
from shared_data_layer.db.session import DatabaseSessionManager
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.auth import AuthTokenValidator, AuthValidationError
from agent_api.aws.factory import AWSClientFactory
from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.rate_limit import RateLimiterProtocol
from agent_api.http.streaming import ChatRunnerProtocol, StreamSettings, UnconfiguredChatRunner
from agent_api.settings import Settings, load_settings
from cache import ValkeyCacheClientProtocol
from services import (
    PillarService,
    ReducedScopeIngestionJobService,
    ReducedScopeWorkerRuntime,
)
from services.ingestion_pipeline import VoyageIngestionPipeline
from telemetry import CacheObservability, MetricsRegistry, get_metrics_registry

_RUNNER_STATE: dict[str, ChatRunnerProtocol] = {"runner": UnconfiguredChatRunner()}
_STREAM_SETTINGS = StreamSettings()
_CACHE_CLIENT_STATE: dict[str, ValkeyCacheClientProtocol | None] = {"client": None}
_RATE_LIMITER_STATE: dict[str, RateLimiterProtocol | None] = {"limiter": None}
_AUTH_VALIDATOR_STATE: dict[str, AuthTokenValidator | None] = {"validator": None}
_AWS_FACTORY_STATE: dict[str, AWSClientFactory | None] = {"factory": None}


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
    """Validate the Authorization header and return the authenticated user context."""

    header = request.headers.get("Authorization")
    if not header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header"
        )
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header"
        )
    validator = _resolve_auth_validator(request)
    try:
        context = await validator.validate(token.strip())
    except AuthValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    request.state.auth_context = context
    return context


def get_chat_runner() -> ChatRunnerProtocol:
    return _RUNNER_STATE["runner"]


def set_chat_runner(runner: ChatRunnerProtocol) -> None:
    _RUNNER_STATE["runner"] = runner


def get_stream_settings() -> StreamSettings:
    return _STREAM_SETTINGS


def get_cache_client(request: Request) -> ValkeyCacheClientProtocol:
    if hasattr(request, "app"):
        client = getattr(request.app.state, "valkey_client", None)
        if client is not None:
            return client
    if _CACHE_CLIENT_STATE["client"] is not None:
        return _CACHE_CLIENT_STATE["client"]
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Cache client is not configured; set VALKEY_URL or explicitly enable "
        "ALLOW_IN_MEMORY_VALKEY=1 for tests/dev.",
    )


def set_cache_client(client: ValkeyCacheClientProtocol) -> None:
    _CACHE_CLIENT_STATE["client"] = client


def get_rate_limiter(request: Request) -> RateLimiterProtocol:
    if hasattr(request, "app"):
        limiter = getattr(request.app.state, "rate_limiter", None)
        if limiter is not None:
            return limiter
    if _RATE_LIMITER_STATE["limiter"] is not None:
        return _RATE_LIMITER_STATE["limiter"]
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Rate limiter is not configured; set ALLOW_RATE_LIMITER_BYPASS=1 for tests/dev "
        "or configure a real limiter backend.",
    )


def set_rate_limiter(limiter: RateLimiterProtocol) -> None:
    _RATE_LIMITER_STATE["limiter"] = limiter


def get_settings(request: Request) -> Settings:
    """Return the cached Settings instance stored on the app state."""

    if not hasattr(request, "app"):
        raise RuntimeError("FastAPI request context is required for get_settings")
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


async def get_reduced_scope_runtime(
    settings: Annotated[Settings, Depends(get_settings)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReducedScopeWorkerRuntime:
    if not settings.reduced_scope.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reduced scope runtime is disabled; enable REDUCED_SCOPE_ENABLED=1 only for "
            "demo/testing or use the production ingestion/export pipeline.",
        )
    ingestion_service = ReducedScopeIngestionJobService(
        db_session,
        allowed_chunk_types=settings.reduced_scope.allowed_chunk_types,
    )
    pillar_service = PillarService(
        db_session,
        allowed_chunk_types=settings.reduced_scope.allowed_chunk_types,
    )
    return ReducedScopeWorkerRuntime(
        session=db_session,
        ingestion_service=ingestion_service,
        pillar_service=pillar_service,
        allowed_chunk_types=settings.reduced_scope.allowed_chunk_types,
    )


def get_document_ingestion_pipeline(request: Request) -> VoyageIngestionPipeline | None:
    if not hasattr(request, "app"):
        return None
    return getattr(request.app.state, "ingestion_pipeline", None)


def get_aws_client_factory(request: Request) -> AWSClientFactory:
    if hasattr(request, "app"):
        factory = getattr(request.app.state, "aws_factory", None)
        if factory is None:
            settings = get_settings(request)
            factory = AWSClientFactory(settings=settings)
            request.app.state.aws_factory = factory
        return factory
    if _AWS_FACTORY_STATE["factory"] is None:
        _AWS_FACTORY_STATE["factory"] = AWSClientFactory(settings=load_settings())
    return _AWS_FACTORY_STATE["factory"]


__all__ = [
    "get_auth_context",
    "get_aws_client_factory",
    "get_cache_client",
    "get_cache_observability",
    "get_chat_runner",
    "get_db_session",
    "get_document_ingestion_pipeline",
    "get_metrics_registry_dep",
    "get_rate_limiter",
    "get_reduced_scope_runtime",
    "get_request_context",
    "get_settings",
    "get_stream_settings",
    "maybe_get_db_session",
    "set_cache_client",
    "set_chat_runner",
    "set_rate_limiter",
]


def _resolve_auth_validator(request: Request) -> AuthTokenValidator:
    if hasattr(request, "app"):
        validator = getattr(request.app.state, "auth_validator", None)
        if validator is not None:
            return validator
        settings = get_settings(request)
        metrics = get_metrics_registry_dep(request)
        validator = AuthTokenValidator(settings.auth, metrics=metrics)
        request.app.state.auth_validator = validator
        return validator
    if _AUTH_VALIDATOR_STATE["validator"] is None:
        settings = load_settings()
        _AUTH_VALIDATOR_STATE["validator"] = AuthTokenValidator(settings.auth)
    return _AUTH_VALIDATOR_STATE["validator"]
