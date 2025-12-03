"""Demo-only reset endpoints for reduced profile smoke workflows."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.deps import (
    get_auth_context,
    get_db_session,
    get_request_context,
    get_settings,
)
from agent_api.http.errors import GatewayError
from agent_api.http.schemas import (
    DemoPurgeDocumentsRequest,
    DemoPurgeDocumentsResponse,
    DemoResetConversationRequest,
    DemoResetConversationResponse,
)
from agent_api.reduced_scope import reduced_scope_demo_metadata
from agent_api.settings import Settings
from services import DemoResetService, deterministic_conversation_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/demo", tags=["demo"])


@router.post("/reset-conversation", summary="Detach documents and messages for a demo conversation")
async def reset_demo_conversation(
    payload: DemoResetConversationRequest,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    _require_demo_guard(settings)
    user_id = _require_user(auth_context)
    conversation_id = payload.conversation_id
    if not conversation_id:
        conversation_id = deterministic_conversation_id(
            user_id,
            namespace=payload.namespace,
        )
    service = DemoResetService(db_session)
    try:
        result = await service.reset_conversation(
            conversation_id=conversation_id,
            owner_user_id=user_id,
        )
    except ValueError as exc:
        await db_session.rollback()
        raise GatewayError(
            code="VALIDATION_ERROR",
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    except LookupError as exc:
        await db_session.rollback()
        raise GatewayError(
            code="NOT_FOUND",
            message="Conversation not found",
            status_code=status.HTTP_404_NOT_FOUND,
        ) from exc
    except PermissionError as exc:
        await db_session.rollback()
        raise GatewayError(
            code="NOT_FOUND",
            message="Conversation not found",
            status_code=status.HTTP_404_NOT_FOUND,
        ) from exc

    await db_session.commit()
    reduced_scope_meta = _reduced_scope_meta(settings)
    logger.info(
        "demo.reset_conversation",
        extra={
            "conversation_id": result.conversation_id,
            "detached": result.detached_documents,
            "messages": result.deleted_messages,
            "checkpoints": result.deleted_checkpoints,
            "agent_runs": result.deleted_agent_runs,
        },
    )
    response = DemoResetConversationResponse(
        conversation_id=result.conversation_id,
        detached_documents=result.detached_documents,
        deleted_messages=result.deleted_messages,
        deleted_checkpoints=result.deleted_checkpoints,
        deleted_agent_runs=result.deleted_agent_runs,
        request_id=request_context.request_id,
        reduced_scope=reduced_scope_meta,
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=response.model_dump())


@router.post("/purge-documents", summary="Delete uploaded demo documents for the caller")
async def purge_demo_documents(
    payload: DemoPurgeDocumentsRequest,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    _require_demo_guard(settings)
    user_id = _require_user(auth_context)
    service = DemoResetService(db_session)
    try:
        result = await service.purge_documents(
            owner_user_id=user_id,
            document_aliases=payload.document_aliases,
            content_hashes=payload.content_hashes,
        )
    except ValueError as exc:
        await db_session.rollback()
        raise GatewayError(
            code="VALIDATION_ERROR",
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    await db_session.commit()
    reduced_scope_meta = _reduced_scope_meta(settings)
    logger.info(
        "demo.purge_documents",
        extra={
            "purged_documents": result.purged_documents,
            "document_ids": result.document_ids,
        },
    )
    response = DemoPurgeDocumentsResponse(
        purged_documents=result.purged_documents,
        document_ids=result.document_ids,
        content_hashes=result.content_hashes,
        request_id=request_context.request_id,
        reduced_scope=reduced_scope_meta,
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=response.model_dump())


def _require_user(auth_context: AuthContext) -> str:
    if not auth_context.user_id:
        raise GatewayError(
            code="UNAUTHORIZED",
            message="Authentication required",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return auth_context.user_id


def _require_demo_guard(settings: Settings) -> None:
    if settings.service_mode != "reduced" or not settings.reduced_scope.is_enabled():
        logger.warning(
            "demo endpoint accessed outside reduced scope",
            extra={
                "service_mode": settings.service_mode,
                "reduced_scope_enabled": settings.reduced_scope.is_enabled(),
            },
        )
        raise GatewayError(
            code="NOT_FOUND",
            message="Endpoint not available",
            status_code=status.HTTP_404_NOT_FOUND,
        )


def _reduced_scope_meta(settings: Settings) -> dict[str, bool | list[str]] | None:
    if settings.reduced_scope.is_enabled():
        return reduced_scope_demo_metadata(settings.reduced_scope)
    return None


__all__ = [
    "router",
]
