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
from agent_api.http.schemas import ChatRequestBody, ResponseMode, BlockingChatResponse
from agent_api.http.streaming import build_streaming_response, run_blocking_chat
from agent_api.models.chat import ChatRequestContext
from agent_api.services.cache import ChatCacheService
from agent_api.services.conversations import ConversationService
from fastapi.responses import JSONResponse

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

    # Check cache if explicitly requested with use_cache=true
    print(f"DEBUG: use_cache={payload.use_cache}, mode={mode}, country_code={payload.constraints.country_code if payload.constraints else None}")
    if (payload.use_cache and 
        mode is ResponseMode.BLOCKING and 
        payload.constraints and 
        payload.constraints.country_code):
        print(f"DEBUG: Checking cache for {payload.constraints.country_code}: {payload.message.content[:60]}...")
        cache_service = ChatCacheService(db_session)
        cached_response = await cache_service.get_cached_response(
            country_code=payload.constraints.country_code,
            question=payload.message.content
        )
        print(f"DEBUG: cached_response = {cached_response is not None}")
        if cached_response:
            print(f"CACHE HIT for {payload.constraints.country_code}: {payload.message.content[:60]}...")
            # Return cached response directly
            response_data = BlockingChatResponse(
                thread_id=chat_request.thread_id,
                request_id=request_context.request_id,
                done=cached_response.get("done", {}),
                messages=cached_response.get("messages", []),
            )
            return JSONResponse(
                status_code=200,
                content=response_data.model_dump(mode="json"),
            )
        else:
            print(f"CACHE MISS for {payload.constraints.country_code}: {payload.message.content[:60]}...")

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

    response = await run_blocking_chat(
        runner=chat_runner,
        chat_request=chat_request,
        auth=auth_context,
        request_context=request_context,
        hints=hints,
        prompt_overrides=prompt_overrides,
        stream_settings=stream_settings,
        db_session=db_session,
    )

    # Store response in cache if use_cache was requested
    if (payload.use_cache and 
        payload.constraints and 
        payload.constraints.country_code and
        response.status_code == 200):
        try:
            # Access response body properly - response.body is bytes
            response_body = response.body
            if isinstance(response_body, bytes):
                import json
                response_data = json.loads(response_body.decode('utf-8'))
                cache_service = ChatCacheService(db_session)
                await cache_service.store_cached_response(
                    country_code=payload.constraints.country_code,
                    question=payload.message.content,
                    response=response_data
                )
                print(f"CACHE STORED for {payload.constraints.country_code}: {payload.message.content[:60]}...")
        except Exception as e:
            import traceback
            print(f"Failed to store cache (non-fatal): {e}")
            print(traceback.format_exc())
    
    return response


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
