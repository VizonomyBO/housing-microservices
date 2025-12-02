"""FastAPI router for document upload operations."""

from __future__ import annotations

import hashlib
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
from agent_api.http.schemas import DocumentUploadRequest, DocumentUploadResponse
from agent_api.reduced_scope import reduced_scope_demo_metadata
from agent_api.settings import Settings
from services import (
    DocumentUploadData,
    DocumentUploadResult,
    DocumentUploadService,
    DocumentUploadStatus,
    ReducedScopeCapabilityError,
    ReducedScopeIngestionJobService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.post("/upload", summary="Register a markitdown text document")
async def upload_document(  # pragma: no cover - exercised via HTTP tests
    payload: DocumentUploadRequest,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
    rate_limiter: Annotated[RateLimiterProtocol, Depends(get_rate_limiter)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    await rate_limiter.acquire(
        bucket="documents_upload",
        tokens=1,
        route="documents.upload",
        metadata={"demo_mode": settings.reduced_scope.text_only_mode()},
    )
    ingestion_helper = ReducedScopeIngestionJobService(
        db_session,
        allowed_chunk_types=settings.reduced_scope.allowed_chunk_types,
    )
    upload_service = DocumentUploadService(
        session=db_session,
        ingestion_service=ingestion_helper,
        allowed_chunk_types=settings.reduced_scope.allowed_chunk_types,
    )
    owner_user_id = _resolve_owner_user_id(
        payload=payload,
        auth_context=auth_context,
    )
    upload_data = DocumentUploadData(
        document_name=payload.document_name,
        content=payload.content,
        content_type=payload.content_type,
        chunk_type=payload.chunk_type,
        access_scope=payload.access_scope,
        country_code=payload.country_code,
        language=payload.language,
        tags=payload.tags,
        metadata=payload.metadata,
        owner_user_id=owner_user_id,
    )

    try:
        result = await upload_service.upload_markdown(upload_data)
    except ValueError as exc:
        await db_session.rollback()
        raise GatewayError(
            code="VALIDATION_ERROR",
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    except ReducedScopeCapabilityError as exc:  # pragma: no cover - defensive path
        await db_session.rollback()
        result = DocumentUploadResult(
            status=DocumentUploadStatus.FEATURE_DISABLED,
            content_hash=hashlib.sha256(upload_data.content.encode("utf-8")).hexdigest(),
            message=str(exc),
        )

    headers = _build_demo_headers(rate_limiter, settings)
    reduced_scope_meta = (
        reduced_scope_demo_metadata(settings.reduced_scope)
        if settings.reduced_scope.is_enabled()
        else None
    )

    if result.status == DocumentUploadStatus.FEATURE_DISABLED:
        await db_session.rollback()
        headers.setdefault("Retry-After", "86400")
        response = _serialize_response(
            result,
            request_context=request_context,
            reduced_scope_meta=reduced_scope_meta,
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=response,
            headers=headers,
        )

    await db_session.commit()
    response = _serialize_response(
        result,
        request_context=request_context,
        reduced_scope_meta=reduced_scope_meta,
    )
    status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    return JSONResponse(status_code=status_code, content=response, headers=headers)


def _resolve_owner_user_id(
    *,
    payload: DocumentUploadRequest,
    auth_context: AuthContext,
) -> str | None:
    if payload.owner_user_id is not None:
        return payload.owner_user_id
    if payload.access_scope == "base":
        return None
    return auth_context.user_id


def _build_demo_headers(
    rate_limiter: RateLimiterProtocol,
    settings: Settings,
) -> dict[str, str]:
    headers = dict(rate_limiter.response_headers())
    if settings.reduced_scope.text_only_mode():
        headers.setdefault("X-Cache-Mode", "text-only")
        headers.setdefault("Viz-Demo-Mode", "text-only")
    return headers


def _serialize_response(
    result: DocumentUploadResult,
    *,
    request_context: RequestContext,
    reduced_scope_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    document_id = str(result.document.id) if result.document else None
    ingestion_payload = None
    ingestion_id = None
    if result.ingestion_job:
        ingestion_id = str(result.ingestion_job.id)
        ingestion_payload = {
            "stage": result.ingestion_job.stage,
            "status": result.ingestion_job.status,
            "started_at": result.ingestion_job.started_at.isoformat(),
            "completed_at": result.ingestion_job.completed_at.isoformat(),
        }
    message = result.message or _default_message(result.status)
    upload_state = {
        "mode": "text",
        "status": result.status.value.lower(),
    }
    response = DocumentUploadResponse(
        document_id=document_id,
        ingestion_id=ingestion_id,
        content_hash=result.content_hash,
        status=result.status.value,
        message=message,
        request_id=request_context.request_id,
        upload=upload_state,
        ingestion=ingestion_payload,
        reduced_scope=reduced_scope_meta,
    )
    return response.model_dump()


def _default_message(status_value: DocumentUploadStatus) -> str:
    if status_value is DocumentUploadStatus.DEDUPED:
        return "Duplicate upload reused the existing document."
    if status_value is DocumentUploadStatus.FEATURE_DISABLED:
        return "Upload skipped because non-text chunks are disabled during the demo."
    return "Document ingested successfully."


__all__ = ["router"]
