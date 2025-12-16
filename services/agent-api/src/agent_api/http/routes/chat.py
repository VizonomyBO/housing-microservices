"""FastAPI router exposing POST /v1/chat."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

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
from agent_api.http.errors import GatewayError
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
from services import ConversationService
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
    user_id = _require_user(auth_context)
    conversation_id, stateless = await _resolve_conversation_id(payload, user_id, db_session)
    chat_request = _build_request_context(
        payload,
        conversation_id,
        auth_context,
        reduced_scope=settings.reduced_scope,
        allow_stateless=stateless,
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
    conversation_id: str,
    auth_context: AuthContext,
    *,
    reduced_scope: ReducedScopeSettings | None = None,
    allow_stateless: bool = False,
) -> ChatRequestContext:
    allowed_chunk_types = None
    reduced_scope_flags = None
    if reduced_scope is not None and reduced_scope.is_enabled():
        if reduced_scope.text_only_mode():
            allowed_chunk_types = list(reduced_scope.allowed_chunk_types)
        reduced_scope_flags = reduced_scope.to_flags()
    return payload.to_request_context(
        conversation_id=conversation_id,
        owner_user_id=auth_context.user_id,
        allowed_chunk_types=allowed_chunk_types,
        reduced_scope_flags=reduced_scope_flags,
        allow_stateless=allow_stateless,
    )


def _generate_thread_id() -> str:
    return str(uuid4())


async def _resolve_conversation_id(
    payload: ChatRequestBody,
    user_id: str,
    db_session: AsyncSession | None,
) -> tuple[str, bool]:
    """Determine the conversation id and whether the run should be stateless."""

    allow_stateless = bool(payload.allow_stateless)
    thread_id = payload.thread_id

    if db_session is None:
        if allow_stateless:
            return thread_id or _generate_thread_id(), True
        raise GatewayError(
            code="DATABASE_UNAVAILABLE",
            message="Database session is required",
            status_code=503,
        )

    if thread_id:
        if not _looks_like_uuid(thread_id):
            if not allow_stateless:
                raise GatewayError(
                    code="VALIDATION_ERROR",
                    message="thread_id must be a valid UUID",
                    status_code=400,
                )
            return thread_id, True
        service = ConversationService(db_session)
        try:
            record = await service.fetch_conversation(
                thread_id,
                owner_user_id=user_id,
            )
        except ValueError as exc:
            raise GatewayError(
                code="VALIDATION_ERROR",
                message="thread_id must be a valid UUID",
                status_code=400,
            ) from exc
        except PermissionError as exc:
            raise GatewayError(
                code="NOT_FOUND",
                message="Conversation not found",
                status_code=404,
            ) from exc
        except LookupError as exc:
            raise GatewayError(
                code="NOT_FOUND",
                message="Conversation not found",
                status_code=404,
            ) from exc
        return record.conversation_id, False

    if allow_stateless:
        return _generate_thread_id(), True

    service = ConversationService(db_session)
    result = await service.ensure_conversation(
        owner_user_id=user_id,
        country_code=payload.constraints.country_code,
        title=payload.message.content[:80] or None,
        namespace="adhoc-chat",
    )
    return result.conversation.conversation_id, False


def _require_user(auth_context: AuthContext) -> str:
    if auth_context.user_id:
        return auth_context.user_id
    raise GatewayError(
        code="UNAUTHORIZED",
        message="Authentication required",
        status_code=401,
    )


def _looks_like_uuid(value: str) -> bool:
    try:
        UUID(str(value))
        return True
    except (TypeError, ValueError):
        return False


__all__ = ["router"]
