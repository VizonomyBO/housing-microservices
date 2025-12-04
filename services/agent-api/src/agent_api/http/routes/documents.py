"""FastAPI router for document upload operations."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.deps import (
    get_auth_context,
    get_db_session,
    get_document_ingestion_pipeline,
    get_rate_limiter,
    get_reduced_scope_runtime,
    get_request_context,
    get_settings,
)
from agent_api.http.errors import GatewayError
from agent_api.http.rate_limit import RateLimiterProtocol
from agent_api.http.schemas import (
    DocumentListItem,
    DocumentListResponse,
    DocumentUploadRequest,
    DocumentUploadResponse,
    PaginationMetadata,
)
from agent_api.reduced_scope import reduced_scope_demo_metadata
from agent_api.settings import Settings
from services import (
    DocumentListEntry,
    DocumentListingService,
    DocumentUploadData,
    DocumentUploadResult,
    DocumentUploadService,
    DocumentUploadStatus,
    PaginationWindow,
    ReducedScopeCapabilityError,
    ReducedScopeWorkerRuntime,
)
from services.ingestion_pipeline import VoyageIngestionPipeline
from services.reduced_scope_runtime import IngestionCompletionPayload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.get("", summary="List uploaded documents for the authenticated user")
async def list_documents(  # pragma: no cover - exercised via HTTP tests
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
    rate_limiter: Annotated[RateLimiterProtocol, Depends(get_rate_limiter)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    tags: Annotated[list[str] | None, Query(description="Filter by tag (all must match)")] = None,
    content_hash: Annotated[
        list[str] | None,
        Query(description="Filter by SHA-256 content hash"),
    ] = None,
    created_after: Annotated[
        datetime | None,
        Query(description="Return documents created after this timestamp"),
    ] = None,
    created_before: Annotated[
        datetime | None,
        Query(description="Return documents created before this timestamp"),
    ] = None,
) -> JSONResponse:
    user_id = _require_user(auth_context)
    await rate_limiter.acquire(
        bucket="documents_list",
        tokens=1,
        route="documents.list",
        metadata={"page": page, "page_size": page_size},
    )
    listing_service = DocumentListingService(db_session)
    result = await listing_service.list_documents(
        owner_user_id=user_id,
        page=page,
        page_size=page_size,
        tags=tags or [],
        content_hashes=content_hash or [],
        created_after=created_after,
        created_before=created_before,
        include_base_documents=settings.reduced_scope.enabled,
    )
    reduced_meta = _maybe_reduced_scope(settings)
    response = DocumentListResponse(
        documents=[_to_document_schema(entry) for entry in result.items],
        pagination=_to_pagination_schema(result.pagination),
        request_id=request_context.request_id,
        reduced_scope=reduced_meta,
    )
    headers = _build_demo_headers(rate_limiter, settings)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response.model_dump(mode="json"),
        headers=headers,
    )


@router.post("/upload", summary="Register a markitdown text document")
async def upload_document(  # pragma: no cover - exercised via HTTP tests
    payload: DocumentUploadRequest,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
    rate_limiter: Annotated[RateLimiterProtocol, Depends(get_rate_limiter)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    runtime: Annotated[ReducedScopeWorkerRuntime, Depends(get_reduced_scope_runtime)],
    ingestion_pipeline: Annotated[
        VoyageIngestionPipeline | None, Depends(get_document_ingestion_pipeline)
    ],
) -> JSONResponse:
    await rate_limiter.acquire(
        bucket="documents_upload",
        tokens=1,
        route="documents.upload",
        metadata={"demo_mode": settings.reduced_scope.text_only_mode()},
    )
    upload_service = DocumentUploadService(
        session=db_session,
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
        use_real_tools = settings.reduced_scope.real_tooling_mode()
        result = await upload_service.upload_markdown(
            upload_data,
            text_only=not use_real_tools,
        )
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
    reduced_scope_meta = _maybe_reduced_scope(settings)

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

    use_real_tools = settings.reduced_scope.real_tooling_mode()
    if (
        use_real_tools
        and result.status == DocumentUploadStatus.COMPLETED
        and result.document is not None
        and result.created
    ):
        if ingestion_pipeline is None:
            raise GatewayError(
                code="INGESTION_DISABLED",
                message="Real-tool ingestion pipeline is not configured",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        ingestion_summary = await ingestion_pipeline.ingest_document(
            document=result.document,
            upload_payload=upload_data,
            session=db_session,
        )
        result.ingestion_job = ingestion_summary
    elif result.status == DocumentUploadStatus.COMPLETED and result.document is not None:
        ingestion_summary = await runtime.complete_ingestion_job(
            result.document.id,
            payload=IngestionCompletionPayload(
                chunk_type=payload.chunk_type,
                metadata={"source": "document_upload"},
            ),
        )
        result.ingestion_job = ingestion_summary

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


def _to_document_schema(entry: DocumentListEntry) -> DocumentListItem:
    return DocumentListItem(
        document_id=entry.document_id,
        canonical_name=entry.canonical_name,
        access_scope=entry.access_scope,
        country_code=entry.country_code,
        language=entry.language,
        tags=entry.tags,
        status=entry.status,
        ingestion_stage=entry.ingestion_stage,
        ingestion_started_at=entry.ingestion_started_at,
        ingestion_completed_at=entry.ingestion_completed_at,
        content_hash=entry.content_hash,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        metadata=entry.metadata,
    )


def _to_pagination_schema(window: PaginationWindow) -> PaginationMetadata:
    return PaginationMetadata(
        page=window.page,
        page_size=window.page_size,
        total_count=window.total_count,
        has_next=window.has_next,
    )


def _maybe_reduced_scope(settings: Settings) -> dict[str, Any] | None:
    if settings.reduced_scope.is_enabled():
        return reduced_scope_demo_metadata(settings.reduced_scope)
    return None


def _require_user(auth_context: AuthContext) -> str:
    if not auth_context.user_id:
        raise GatewayError(
            code="UNAUTHORIZED",
            message="Authentication required",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return auth_context.user_id


def _default_message(status_value: DocumentUploadStatus) -> str:
    if status_value is DocumentUploadStatus.DEDUPED:
        return "Duplicate upload reused the existing document."
    if status_value is DocumentUploadStatus.FEATURE_DISABLED:
        return "Upload skipped because non-text chunks are disabled during the demo."
    return "Document ingested successfully."


__all__ = ["router"]
