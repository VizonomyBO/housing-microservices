"""Dependency functions shared by FastAPI routes."""

from __future__ import annotations

from uuid import uuid4

from fastapi import Request

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.streaming import ChatRunnerProtocol, StreamSettings, UnconfiguredChatRunner

_RUNNER_STATE: dict[str, ChatRunnerProtocol] = {"runner": UnconfiguredChatRunner()}
_STREAM_SETTINGS = StreamSettings()


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


__all__ = [
    "get_auth_context",
    "get_chat_runner",
    "get_request_context",
    "get_stream_settings",
    "set_chat_runner",
]
