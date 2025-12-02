"""FastAPI router exposing POST /v1/chat."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.deps import (
    get_auth_context,
    get_cache_observability,
    get_chat_runner,
    get_metrics_registry_dep,
    get_rate_limiter,
    get_request_context,
    get_settings,
    get_stream_settings,
    maybe_get_db_session,
)
from agent_api.http.rate_limit import RateLimiterProtocol
from agent_api.http.schemas import ChatRequestBody, ResponseMode
from agent_api.http.streaming import (
    ChatRunnerProtocol,
    StreamSettings,
    build_streaming_response,
    run_blocking_chat,
)
from agent_api.reduced_scope import ReducedScopeSettings, reduced_scope_demo_metadata
from agent_api.settings import Settings
from models.retrieval import ChatRequestContext
from telemetry import CacheObservability, MetricsRegistry

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat", summary="Invoke the LangGraph chat agent")
async def post_chat(
    payload: ChatRequestBody,
    chat_runner: Annotated[ChatRunnerProtocol, Depends(get_chat_runner)],
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    stream_settings: Annotated[StreamSettings, Depends(get_stream_settings)],
    metrics_registry: Annotated[MetricsRegistry, Depends(get_metrics_registry_dep)],
    cache_observability: Annotated[CacheObservability, Depends(get_cache_observability)],
    db_session: Annotated[AsyncSession | None, Depends(maybe_get_db_session)],
    rate_limiter: Annotated[RateLimiterProtocol, Depends(get_rate_limiter)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    thread_id = payload.thread_id or _generate_thread_id()
    chat_request = _build_request_context(
        payload,
        thread_id,
        auth_context,
        reduced_scope=settings.reduced_scope,
    )
    hints = dict(payload.hints or {})
    prompt_overrides = dict(payload.prompt_overrides or {})
    mode = payload.resolved_response_mode()
    demo_metadata = (
        reduced_scope_demo_metadata(settings.reduced_scope)
        if settings.reduced_scope.is_enabled()
        else None
    )

    if mode is ResponseMode.STREAM:
        return await build_streaming_response(
            runner=chat_runner,
            chat_request=chat_request,
            auth=auth_context,
            request_context=request_context,
            hints=hints,
            prompt_overrides=prompt_overrides,
            stream_settings=stream_settings,
            metrics=metrics_registry,
            cache_observability=cache_observability,
            db_session=db_session,
            rate_limiter=rate_limiter,
            reduced_scope=settings.reduced_scope,
            demo_metadata=demo_metadata,
        )

    return await run_blocking_chat(
        runner=chat_runner,
        chat_request=chat_request,
        auth=auth_context,
        request_context=request_context,
        hints=hints,
        prompt_overrides=prompt_overrides,
        stream_settings=stream_settings,
        metrics=metrics_registry,
        cache_observability=cache_observability,
        db_session=db_session,
        rate_limiter=rate_limiter,
        reduced_scope=settings.reduced_scope,
        demo_metadata=demo_metadata,
    )


def _build_request_context(
    payload: ChatRequestBody,
    thread_id: str,
    auth_context: AuthContext,
    *,
    reduced_scope: ReducedScopeSettings | None = None,
) -> ChatRequestContext:
    allowed_chunk_types = None
    reduced_scope_flags = None
    if reduced_scope is not None and reduced_scope.is_enabled():
        if reduced_scope.text_only_mode():
            allowed_chunk_types = list(reduced_scope.allowed_chunk_types)
        reduced_scope_flags = reduced_scope.to_flags()
    return payload.to_request_context(
        conversation_id=thread_id,
        owner_user_id=auth_context.user_id,
        allowed_chunk_types=allowed_chunk_types,
        reduced_scope_flags=reduced_scope_flags,
    )


def _generate_thread_id() -> str:
    return f"thr_{uuid4().hex}"


__all__ = ["router"]
