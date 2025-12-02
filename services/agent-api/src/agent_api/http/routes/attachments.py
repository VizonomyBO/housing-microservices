"""FastAPI router for conversation attachment management."""

from __future__ import annotations

from typing import Annotated

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
    AttachmentDeleteResponse,
    AttachmentListResponse,
    AttachmentMutationResponse,
    AttachmentRecord,
    AttachmentRequest,
)
from agent_api.reduced_scope import reduced_scope_demo_metadata
from agent_api.settings import Settings
from repositories.conversation_scope_repository import ConversationDocumentRecord
from services import AttachmentResult, AttachmentService, AttachmentStatus

router = APIRouter(prefix="/v1/conversations", tags=["attachments"])


@router.get("/{conversation_id}/attachments", summary="List attachments for a conversation")
async def list_attachments(
    conversation_id: str,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    settings: Annotated[Settings, Depends(get_settings)],
    rate_limiter: Annotated[RateLimiterProtocol, Depends(get_rate_limiter)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:  # pragma: no cover - exercised via HTTP tests
    service = AttachmentService(
        db_session,
        allowed_chunk_types=settings.reduced_scope.allowed_chunk_types,
    )
    records = await service.list_attachments(conversation_id)
    payload = AttachmentListResponse(
        conversation_id=conversation_id,
        attachments=[_record_to_schema(record) for record in records],
        request_id=request_context.request_id,
    )
    headers = _build_headers(rate_limiter, settings)
    return JSONResponse(
        status_code=status.HTTP_200_OK, content=payload.model_dump(), headers=headers
    )


@router.post("/{conversation_id}/attachments", summary="Attach a document to a conversation")
async def attach_document(  # pragma: no cover - exercised via HTTP tests
    conversation_id: str,
    payload: AttachmentRequest,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
    rate_limiter: Annotated[RateLimiterProtocol, Depends(get_rate_limiter)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    service = AttachmentService(
        db_session,
        allowed_chunk_types=settings.reduced_scope.allowed_chunk_types,
    )
    try:
        result = await service.attach_document(
            conversation_id=conversation_id,
            document_id=payload.document_id,
            attach_source="user_request",
            visibility=payload.visibility,
            role=payload.role,
            attached_by_user_id=auth_context.user_id,
            auto_attach_base_docs=payload.auto_attach_base_docs,
        )
    except LookupError as exc:
        await db_session.rollback()
        raise GatewayError(
            code="NOT_FOUND",
            message=str(exc),
            status_code=status.HTTP_404_NOT_FOUND,
        ) from exc
    except ValueError as exc:
        await db_session.rollback()
        raise GatewayError(
            code="VALIDATION_ERROR",
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    headers = _build_headers(rate_limiter, settings)
    reduced_scope_meta = (
        reduced_scope_demo_metadata(settings.reduced_scope)
        if settings.reduced_scope.is_enabled()
        else None
    )
    status_code = status.HTTP_201_CREATED
    if result.status == AttachmentStatus.FEATURE_DISABLED:
        await db_session.commit()
        headers.setdefault("Retry-After", "86400")
        status_code = status.HTTP_202_ACCEPTED
    else:
        await db_session.commit()
        status_code = status.HTTP_201_CREATED

    response = AttachmentMutationResponse(
        conversation_id=conversation_id,
        document_id=result.attachment.document_id if result.attachment else None,
        status=result.status.value,
        attachment=_record_to_schema(result.attachment) if result.attachment else None,
        auto_attached=result.auto_attached,
        message=result.message or _default_attachment_message(result),
        request_id=request_context.request_id,
        reduced_scope=reduced_scope_meta,
    )
    return JSONResponse(status_code=status_code, content=response.model_dump(), headers=headers)


@router.delete("/{conversation_id}/attachments/{document_id}", summary="Detach a document")
async def detach_document(  # pragma: no cover - exercised via HTTP tests
    conversation_id: str,
    document_id: str,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    settings: Annotated[Settings, Depends(get_settings)],
    rate_limiter: Annotated[RateLimiterProtocol, Depends(get_rate_limiter)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    service = AttachmentService(
        db_session,
        allowed_chunk_types=settings.reduced_scope.allowed_chunk_types,
    )
    try:
        status_value = await service.detach_document(
            conversation_id=conversation_id,
            document_id=document_id,
        )
    except LookupError as exc:
        await db_session.rollback()
        raise GatewayError(
            code="NOT_FOUND",
            message=str(exc),
            status_code=status.HTTP_404_NOT_FOUND,
        ) from exc
    except ValueError:
        await db_session.rollback()
        response = AttachmentDeleteResponse(
            conversation_id=conversation_id,
            document_id=document_id,
            status="FORBIDDEN",
            request_id=request_context.request_id,
        )
        headers = _build_headers(rate_limiter, settings)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT, content=response.model_dump(), headers=headers
        )

    if status_value is AttachmentStatus.DETACHED:
        await db_session.commit()
    else:
        await db_session.rollback()
    headers = _build_headers(rate_limiter, settings)
    response = AttachmentDeleteResponse(
        conversation_id=conversation_id,
        document_id=document_id,
        status=status_value.value,
        request_id=request_context.request_id,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK, content=response.model_dump(), headers=headers
    )


def _record_to_schema(record: ConversationDocumentRecord) -> AttachmentRecord:
    return AttachmentRecord(
        document_id=record.document_id,
        attach_source=record.attach_source,
        role=record.role,
        visibility=record.visibility,
        canonical_name=record.canonical_name,
        access_scope=record.access_scope,
        country_code=record.country_code,
        metadata=record.metadata,
    )


def _default_attachment_message(result: AttachmentResult) -> str:
    if result.status is AttachmentStatus.ATTACHED:
        return "Attachment linked successfully."
    if result.status is AttachmentStatus.FEATURE_DISABLED:
        return "Attachment skipped because only text chunks are allowed."
    if result.status is AttachmentStatus.NOT_FOUND:
        return "Attachment not found."
    return ""


def _build_headers(
    rate_limiter: RateLimiterProtocol,
    settings: Settings,
) -> dict[str, str]:
    headers = dict(rate_limiter.response_headers())
    if settings.reduced_scope.text_only_mode():
        headers.setdefault("X-Cache-Mode", "text-only")
        headers.setdefault("Viz-Demo-Mode", "text-only")
    return headers


__all__ = ["router"]
