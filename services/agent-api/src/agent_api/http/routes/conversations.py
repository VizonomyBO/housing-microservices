"""FastAPI router for conversation lifecycle endpoints."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.deps import (
    get_auth_context,
    get_db_session,
    get_rate_limiter,
    get_request_context,
    get_settings,
)
from agent_api.http.errors import GatewayError
from agent_api.http.rate_limit import RateLimiterProtocol
from agent_api.http.schemas import (
    ConversationCreateRequest,
    ConversationRecordResponse,
    ConversationResponse,
)
from agent_api.reduced_scope import reduced_scope_demo_metadata
from agent_api.settings import Settings
from services import ConversationRecord, ConversationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


@router.post("", summary="Create or reuse a conversation")
async def create_conversation(
    payload: ConversationCreateRequest,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
    rate_limiter: Annotated[RateLimiterProtocol, Depends(get_rate_limiter)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    user_id = _require_user(auth_context)
    await rate_limiter.acquire(
        bucket="conversations_create",
        tokens=1,
        route="conversations.create",
        metadata={"namespace": payload.namespace or "reduced-e2e"},
    )
    service = ConversationService(db_session)
    try:
        result = await service.ensure_conversation(
            owner_user_id=user_id,
            country_code=payload.country_code,
            title=payload.title,
            namespace=payload.namespace,
            tags=payload.tags,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        await db_session.rollback()
        raise GatewayError(
            code="VALIDATION_ERROR",
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    await db_session.commit()
    reduced_meta = _reduced_scope_metadata(settings)
    response = ConversationResponse(
        conversation=_to_schema(result.conversation),
        request_id=request_context.request_id,
        created=result.created,
        reduced_scope=reduced_meta,
    )
    status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    headers = _build_headers(rate_limiter, settings)
    logger.info(
        "conversation.ensure",
        extra={
            "conversation_id": result.conversation.conversation_id,
            "created": result.created,
            "owner_user_id": user_id,
            "namespace": result.conversation.namespace,
        },
    )
    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json"),
        headers=headers,
    )


@router.get("/{conversation_id}", summary="Fetch conversation metadata")
async def get_conversation(
    conversation_id: str,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
    rate_limiter: Annotated[RateLimiterProtocol, Depends(get_rate_limiter)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    user_id = _require_user(auth_context)
    await rate_limiter.acquire(
        bucket="conversations_get",
        tokens=1,
        route="conversations.get",
        metadata={"conversation_id": conversation_id},
    )
    service = ConversationService(db_session)
    try:
        record = await service.fetch_conversation(
            conversation_id,
            owner_user_id=user_id,
        )
    except PermissionError as exc:
        raise GatewayError(
            code="NOT_FOUND",
            message="Conversation not found",
            status_code=status.HTTP_404_NOT_FOUND,
        ) from exc
    except LookupError as exc:
        raise GatewayError(
            code="NOT_FOUND",
            message="Conversation not found",
            status_code=status.HTTP_404_NOT_FOUND,
        ) from exc

    reduced_meta = _reduced_scope_metadata(settings)
    response = ConversationResponse(
        conversation=_to_schema(record),
        request_id=request_context.request_id,
        reduced_scope=reduced_meta,
    )
    headers = _build_headers(rate_limiter, settings)
    logger.info(
        "conversation.fetch",
        extra={
            "conversation_id": record.conversation_id,
            "owner_user_id": user_id,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response.model_dump(mode="json"),
        headers=headers,
    )


def _require_user(auth_context: AuthContext) -> str:
    if not auth_context.user_id:
        raise GatewayError(
            code="UNAUTHORIZED",
            message="Authentication required",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return auth_context.user_id


def _to_schema(record: ConversationRecord) -> ConversationRecordResponse:
    return ConversationRecordResponse(
        conversation_id=record.conversation_id,
        owner_user_id=record.owner_user_id,
        namespace=record.namespace,
        title=record.title,
        country_code=record.country_code,
        status=record.status,
        tags=record.tags,
        metadata=record.metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _reduced_scope_metadata(settings: Settings) -> dict[str, Any] | None:
    if settings.reduced_scope.is_enabled():
        return reduced_scope_demo_metadata(settings.reduced_scope)
    return None


def _build_headers(
    rate_limiter: RateLimiterProtocol,
    settings: Settings,
) -> dict[str, str]:
    headers = dict(rate_limiter.response_headers())
    if settings.reduced_scope.text_only_mode():
        headers.setdefault("X-Cache-Mode", "text-only")
        headers.setdefault("Viz-Demo-Mode", "text-only")
    return headers
