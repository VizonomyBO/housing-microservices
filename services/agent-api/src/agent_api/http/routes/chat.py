"""FastAPI router exposing POST /v1/chat."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.deps import (
    get_auth_context,
    get_db_session,
    get_request_context,
    get_runner,
    get_stream_settings,
)
from agent_api.http.errors import GatewayError
from agent_api.http.schemas import ChatRequestBody, ResponseMode
from agent_api.http.streaming import build_streaming_response, run_blocking_chat
from agent_api.models.chat import ChatRequestContext
from agent_api.services.conversations import ConversationService

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat", summary="Invoke the ReAct chat agent")
async def post_chat(
    payload: ChatRequestBody,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    stream_settings: Annotated[Any, Depends(get_stream_settings)],
    chat_runner: Annotated[Any, Depends(get_runner)],
):
    user_id = _require_user(auth_context)
    conversation_id, stateless = await _resolve_conversation_id(payload, user_id, db_session)
    chat_request = _build_request_context(
        payload,
        conversation_id,
        auth_context,
        allow_stateless=stateless,
    )
    hints = dict(payload.hints or {})
    prompt_overrides = dict(payload.prompt_overrides or {})
    mode = payload.resolved_response_mode()

    if mode is ResponseMode.STREAM:
        return await build_streaming_response(
            runner=chat_runner,
            chat_request=chat_request,
            auth=auth_context,
            request_context=request_context,
            hints=hints,
            prompt_overrides=prompt_overrides,
            stream_settings=stream_settings,
            db_session=db_session,
        )

    return await run_blocking_chat(
        runner=chat_runner,
        chat_request=chat_request,
        auth=auth_context,
        request_context=request_context,
        hints=hints,
        prompt_overrides=prompt_overrides,
        stream_settings=stream_settings,
        db_session=db_session,
    )


def _build_request_context(
    payload: ChatRequestBody,
    conversation_id: str,
    auth_context: AuthContext,
    allow_stateless: bool = False,
) -> ChatRequestContext:
    message_payload = payload.message
    thread_id = payload.thread_id or conversation_id
    return ChatRequestContext(
        conversation_id=conversation_id,
        thread_id=thread_id,
        session_id=payload.session_id,
        allow_stateless=allow_stateless,
        message=message_payload,
        hints=dict(payload.hints or {}),
        constraints=payload.constraints,
        owner_user_id=auth_context.user_id,
        workspace_id=None,
        tenant_id=auth_context.tenant_id,
    )


def _generate_thread_id() -> str:
    return str(uuid4())


async def _resolve_conversation_id(
    payload: ChatRequestBody,
    user_id: str,
    db_session: AsyncSession,
) -> tuple[str, bool]:
    allow_stateless = bool(payload.allow_stateless)
    thread_id = payload.thread_id
    service = ConversationService(db_session)

    if thread_id:
        if not _looks_like_uuid(thread_id):
            if not allow_stateless:
                raise GatewayError(
                    code="VALIDATION_ERROR",
                    message="thread_id must be a valid UUID",
                    status_code=400,
                )
            return thread_id, True
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
        return str(record.id), False

    if allow_stateless:
        return _generate_thread_id(), True

    result = await service.ensure_conversation(
        owner_user_id=user_id,
        country_code=payload.constraints.country_code,
        title=payload.message.content[:80] or None,
        namespace=payload.message.attachments[0].attach_source
        if payload.message.attachments
        else "adhoc-chat",
        tags=[],
        metadata=None,
    )
    return str(result.id), False


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
