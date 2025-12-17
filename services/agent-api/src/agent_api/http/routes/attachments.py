"""FastAPI router for conversation attachment management."""

from __future__ import annotations

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.deps import get_auth_context, get_db_session, get_request_context
from agent_api.http.errors import GatewayError
from agent_api.http.schemas import (
    AttachmentBulkRequest,
    AttachmentBulkResponse,
    AttachmentBulkSkipped,
    AttachmentDeleteResponse,
    AttachmentListResponse,
    AttachmentMutationResponse,
    AttachmentRecord,
    AttachmentRequest,
)
from agent_api.services.attachments import (
    AttachmentResult,
    AttachmentService,
    AttachmentStatus,
    DocumentNotReadyError,
)
from agent_api.services.retrieval_scope import ConversationDocumentRecord

router = APIRouter(prefix="/v1/conversations", tags=["attachments"])


@router.get("/{conversation_id}/attachments", summary="List attachments for a conversation")
async def list_attachments(
    conversation_id: str,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    service = AttachmentService(db_session)
    records = await service.list_attachments(conversation_id)
    payload = AttachmentListResponse(
        conversation_id=conversation_id,
        attachments=[_record_to_schema(record) for record in records],
        request_id=request_context.request_id,
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=payload.model_dump())


@router.post("/{conversation_id}/attachments", summary="Attach a document to a conversation")
async def attach_document(
    conversation_id: str,
    payload: AttachmentRequest,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    _ensure_authenticated(auth_context)
    service = AttachmentService(db_session)
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
    except DocumentNotReadyError as exc:
        await db_session.rollback()
        raise GatewayError(
            code="DOCUMENT_NOT_READY",
            message="Document not ready",
            status_code=status.HTTP_409_CONFLICT,
            details={
                "document_id": str(exc.document_id),
                "status": exc.status,
                "ingestion_stage": exc.stage,
            },
        ) from exc
    except ValueError as exc:
        await db_session.rollback()
        raise GatewayError(
            code="VALIDATION_ERROR",
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    await db_session.commit()
    response = AttachmentMutationResponse(
        conversation_id=conversation_id,
        document_id=result.attachment.document_id if result.attachment else None,
        status=_attach_status_literal(result.status),
        attachment=_record_to_schema(result.attachment) if result.attachment else None,
        auto_attached=result.auto_attached or [],
        message=result.message or _default_attachment_message(result),
        request_id=request_context.request_id,
    )
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=response.model_dump())


@router.delete("/{conversation_id}/attachments/{document_id}", summary="Detach a document")
async def detach_document(
    conversation_id: str,
    document_id: str,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    service = AttachmentService(db_session)
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

    if status_value is AttachmentStatus.DETACHED:
        await db_session.commit()
    else:
        await db_session.rollback()
    response = AttachmentDeleteResponse(
        conversation_id=conversation_id,
        document_id=document_id,
        status=_detach_status_literal(status_value),
        request_id=request_context.request_id,
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=response.model_dump())


@router.post(
    "/{conversation_id}/attachments/bulk",
    summary="Attach a set of documents to a conversation",
)
async def bulk_attach_documents(
    conversation_id: str,
    payload: AttachmentBulkRequest,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    _ensure_authenticated(auth_context)
    service = AttachmentService(db_session)

    attached: list[str] = []
    skipped: list[AttachmentBulkSkipped] = []
    unique_ids = list(dict.fromkeys(payload.document_ids))
    for doc_id in unique_ids:
        try:
            result = await service.attach_document(
                conversation_id=conversation_id,
                document_id=doc_id,
                attach_source="bulk",
                visibility=payload.visibility,
                role=payload.role,
                attached_by_user_id=auth_context.user_id,
                auto_attach_base_docs=False,
            )
        except DocumentNotReadyError as exc:
            skipped.append(
                AttachmentBulkSkipped(
                    document_id=str(exc.document_id),
                    reason=f"Document not ready (status={exc.status}, stage={exc.stage})",
                )
            )
            continue
        except LookupError as exc:
            skipped.append(AttachmentBulkSkipped(document_id=doc_id, reason=str(exc)))
            continue

        if result.status == AttachmentStatus.ATTACHED and result.attachment:
            attached.append(result.attachment.document_id)
        else:
            skipped.append(
                AttachmentBulkSkipped(
                    document_id=doc_id,
                    reason=result.message or result.status,
                )
            )

    await db_session.commit()
    response = AttachmentBulkResponse(
        conversation_id=conversation_id,
        attached=attached,
        skipped=skipped,
        request_id=request_context.request_id,
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=response.model_dump())


def _ensure_authenticated(auth_context: AuthContext) -> None:
    if not auth_context.user_id:
        raise GatewayError(
            code="UNAUTHORIZED",
            message="Authentication required",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


def _record_to_schema(record: ConversationDocumentRecord | AttachmentRecord | None):
    if record is None:
        return None
    if isinstance(record, AttachmentRecord):
        return record
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
    if result.status == AttachmentStatus.ATTACHED:
        return "Attachment linked successfully."
    if result.status == AttachmentStatus.FEATURE_DISABLED:
        return "Attachment skipped because only text chunks are allowed."
    if result.status == AttachmentStatus.NOT_FOUND:
        return "Attachment not found."
    return ""


def _attach_status_literal(value: str) -> Literal["ATTACHED", "FEATURE_DISABLED", "NOT_FOUND"]:
    if value in ("ATTACHED", "FEATURE_DISABLED", "NOT_FOUND"):
        return cast(Literal["ATTACHED", "FEATURE_DISABLED", "NOT_FOUND"], value)
    return "NOT_FOUND"


def _detach_status_literal(value: str) -> Literal["DETACHED", "NOT_FOUND", "FORBIDDEN"]:
    if value in ("DETACHED", "NOT_FOUND", "FORBIDDEN"):
        return cast(Literal["DETACHED", "NOT_FOUND", "FORBIDDEN"], value)
    return "NOT_FOUND"


__all__ = ["router"]
