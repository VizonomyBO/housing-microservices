"""FastAPI dependency providers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import HTTPException, Request, status
from shared_data_layer.db.session import DatabaseSessionManager
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.agent.runner import ChatRunnerProtocol, UnconfiguredRunner
from agent_api.auth.validator import AuthContext, AuthTokenValidator, AuthValidationError
from agent_api.http.context import RequestContext
from agent_api.settings import Settings, load_settings
from streaming.sse_emitter import StreamSettings

_RUNNER: ChatRunnerProtocol = UnconfiguredRunner()
_STREAM_SETTINGS = StreamSettings()
_AUTH_VALIDATOR: AuthTokenValidator | None = None


def get_runner() -> ChatRunnerProtocol:
    return _RUNNER


def set_chat_runner(runner: ChatRunnerProtocol) -> None:
    global _RUNNER  # noqa: PLW0603
    _RUNNER = runner


def get_stream_settings() -> StreamSettings:
    return _STREAM_SETTINGS


def get_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        settings = load_settings()
        request.app.state.settings = settings
    return settings


async def get_request_context(request: Request) -> RequestContext:
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


def _resolve_auth_validator(request: Request) -> AuthTokenValidator:
    global _AUTH_VALIDATOR  # noqa: PLW0603
    if _AUTH_VALIDATOR:
        return _AUTH_VALIDATOR
    settings = get_settings(request)
    _AUTH_VALIDATOR = AuthTokenValidator(settings.auth)
    return _AUTH_VALIDATOR


__all__ = [
    "get_auth_context",
    "get_db_session",
    "get_request_context",
    "get_runner",
    "get_settings",
    "get_stream_settings",
    "maybe_get_db_session",
    "set_chat_runner",
]
