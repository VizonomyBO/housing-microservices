"""FastAPI router for document upload and listing operations."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import JSONResponse, Response
from shared_data_layer.db.models.documents import Document
from shared_data_layer.repositories.documents import UploadedFileRepository
from shared_data_layer.schemas.countries import REGION_BY_COUNTRY_ALPHA3, Region
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.deps import get_auth_context, get_db_session, get_request_context, get_settings
from agent_api.http.errors import GatewayError
from agent_api.http.schemas import DocumentListItem, DocumentListResponse, PaginationMetadata
from agent_api.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/documents", tags=["documents"])

# Set of all region codes for quick lookup
_REGION_CODES = {r.value for r in Region}


def _expand_country_codes(codes: list[str], include_global: bool = True) -> list[str]:
    """Expand country codes to include their region and optionally global.

    When querying for a specific country (e.g., CMR), we also want to return
    documents from the region (AFR) and global documents (GLO).

    If a region code is passed (e.g., AFR), it's kept as-is.
    """
    expanded = set(codes)
    for code in codes:
        # Skip if it's already a region code
        if code in _REGION_CODES:
            continue
        # Look up the region for this country
        region = REGION_BY_COUNTRY_ALPHA3.get(code)
        if region:
            expanded.add(region.value)
    # Include global documents
    if include_global:
        expanded.add(Region.GLO.value)
    return list(expanded)


@router.get("", summary="List uploaded documents for the authenticated user")
async def list_documents(
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=1000)] = 20,
    tags: Annotated[list[str] | None, Query(description="Filter by tag (all must match)")] = None,
    content_hash: Annotated[
        list[str] | None,
        Query(description="Filter by SHA-256 content hash"),
    ] = None,
    country_code: Annotated[
        list[str] | None,
        Query(description="Filter by country code"),
    ] = None,
    include_global: Annotated[
        bool,
        Query(description="Include global (GLO) documents in country queries"),
    ] = False,
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
    user_uuid = UUID(user_id)
    stmt = select(Document).where(Document.owner_user_id == user_uuid)
    if tags:
        stmt = stmt.where(Document.tags.contains(tags))
    if content_hash:
        stmt = stmt.where(Document.content_hash.in_(content_hash))
    if country_code:
        # Expand country codes to include their region (and optionally global) documents
        expanded_codes = _expand_country_codes(country_code, include_global=include_global)
        stmt = stmt.where(Document.country_code.in_(expanded_codes))
    if created_after:
        stmt = stmt.where(Document.created_at >= created_after)
    if created_before:
        stmt = stmt.where(Document.created_at <= created_before)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_count = (await db_session.execute(count_stmt)).scalar_one()
    rows = (
        (
            await db_session.execute(
                stmt.order_by(Document.created_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        .scalars()
        .all()
    )

    response = DocumentListResponse(
        documents=[_to_document_schema(doc) for doc in rows],
        pagination=PaginationMetadata(
            page=page,
            page_size=page_size,
            total_count=total_count,
            has_next=(page * page_size) < (total_count or 0),
        ),
        request_id=request_context.request_id,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response.model_dump(mode="json"),
    )


@router.post("/upload", summary="Upload and ingest a document")
async def upload_document(
    payload: dict,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    user_id = _require_user(auth_context)
    user_uuid = UUID(user_id)
    document_name = (payload.get("document_name") or "").strip()
    content = (payload.get("content") or "").strip()
    chunk_type = (payload.get("chunk_type") or "text").lower()

    if not document_name or not content:
        raise GatewayError(
            code="VALIDATION_ERROR",
            message="document_name and content are required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if chunk_type != "text":
        response = {
            "status": "FEATURE_DISABLED",
            "document_id": None,
            "ingestion_id": None,
            "upload": {"status": "skipped", "reason": "Only text chunks are supported"},
        }
        headers = {"Retry-After": "86400"}
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=response, headers=headers)

    # Proxy to ingestion service
    ingestion_url = settings.ingestion_base_url.rstrip("/") + "/v1/documents/upload"
    proxy_payload = dict(payload)
    proxy_payload.setdefault("owner_user_id", user_id)
    timeout = httpx.Timeout(settings.ingestion_request_timeout_seconds)
    headers = {}
    if settings.ingestion_api_key:
        headers["Authorization"] = f"Bearer {settings.ingestion_api_key}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(ingestion_url, json=proxy_payload, headers=headers)
        if response.status_code >= 500:
            raise GatewayError(
                code="INGESTION_FAILED",
                message="Ingestion service unavailable",
                status_code=503,
            )
        if response.status_code >= 400:
            raise GatewayError(
                code="INGESTION_FAILED",
                message=response.text,
                status_code=response.status_code,
            )
        data = response.json()

    # Track upload locally
    upload_repo = UploadedFileRepository(db_session)
    if data.get("document_id"):
        await upload_repo.register_upload(
            document_id=UUID(str(data.get("document_id"))),
            owner_user_id=user_uuid,
            storage_uri=f"s3://ingest/{data.get('document_id')}",
            byte_size=len(content.encode("utf-8")),
            content_hash=data.get("content_hash") or "",
            ingestion_metadata={"ingestion_id": data.get("ingestion_id")},
        )
    await db_session.commit()
    return JSONResponse(status_code=response.status_code, content=data)


@router.get(
    "/{document_id}/download",
    summary="Download PDF document from S3",
    response_class=Response,
)
async def download_document(
    document_id: Annotated[str, Path(description="Document UUID")],
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """
    Download a PDF document from S3 via ingestion service.

    Requires authentication and verifies the user has access to the document.
    """
    _require_user(auth_context)

    # Validate document_id format
    try:
        UUID(document_id)
    except ValueError as exc:
        raise GatewayError(
            code="VALIDATION_ERROR",
            message="Invalid document_id format",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    # Proxy to ingestion service
    ingestion_url = (
        settings.ingestion_base_url.rstrip("/")
        + f"/v1/documents/{document_id}/download"
    )
    timeout = httpx.Timeout(settings.ingestion_request_timeout_seconds)
    headers = {}
    if settings.ingestion_api_key:
        headers["Authorization"] = f"Bearer {settings.ingestion_api_key}"
    # Forward the user's auth token to ingestion service
    if auth_context.token:
        headers["Authorization"] = f"Bearer {auth_context.token}"

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(ingestion_url, headers=headers)
            if response.status_code >= 500:
                raise GatewayError(
                    code="INGESTION_FAILED",
                    message="Ingestion service unavailable",
                    status_code=503,
                )
            if response.status_code >= 400:
                error_text = response.text
                raise GatewayError(
                    code="DOWNLOAD_FAILED",
                    message=error_text,
                    status_code=response.status_code,
                )

            # Return the PDF file with proper headers
            return Response(
                content=response.content,
                media_type=response.headers.get("content-type", "application/pdf"),
                headers={
                    "Content-Disposition": response.headers.get(
                        "content-disposition", f'attachment; filename="document.pdf"'
                    ),
                    "Content-Length": str(len(response.content)),
                },
            )
    except httpx.TimeoutException as exc:
        raise GatewayError(
            code="TIMEOUT",
            message="Request to ingestion service timed out",
            status_code=504,
        ) from exc
    except httpx.RequestError as exc:
        raise GatewayError(
            code="INGESTION_FAILED",
            message=f"Failed to connect to ingestion service: {exc}",
            status_code=503,
        ) from exc


def _to_document_schema(doc: Document) -> DocumentListItem:
    return DocumentListItem(
        document_id=str(doc.id),
        canonical_name=doc.canonical_name,
        access_scope=doc.access_scope,
        country_code=doc.country_code,
        language=doc.language,
        tags=doc.tags or [],
        status=doc.status,
        ingestion_stage=doc.ingestion_stage,
        ingestion_started_at=doc.ingestion_started_at,
        ingestion_completed_at=doc.ingestion_completed_at,
        content_hash=doc.content_hash,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        metadata=doc.metadata_,
    )


def _require_user(auth_context: AuthContext) -> str:
    if not auth_context.user_id:
        raise GatewayError(
            code="UNAUTHORIZED",
            message="Authentication required",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return auth_context.user_id


__all__ = ["router"]
