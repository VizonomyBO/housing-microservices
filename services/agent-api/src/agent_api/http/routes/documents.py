"""FastAPI router for document upload and listing operations."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, File, Path, Query, UploadFile, status
from fastapi.responses import JSONResponse, Response
from shared_data_layer.db.models.documents import Document
from shared_data_layer.repositories.documents import UploadedFileRepository
from shared_data_layer.schemas.countries import REGION_BY_COUNTRY_ALPHA3, Region
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.deps import get_auth_context, get_db_session, get_request_context, get_settings
from agent_api.http.errors import GatewayError
from agent_api.http.schemas import DocumentListItem, DocumentListResponse, PaginationMetadata
from agent_api.settings import Settings
from agent_api.storage import upload_pdf_to_s3

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/documents", tags=["documents"])

_REGION_CODES = {r.value for r in Region}
_REGION_ONLY_CODES = {r.value for r in Region if r != Region.GLO}

_CHAT_SORT_COLUMNS = {
    "country": Document.country_code,
    "filename": Document.canonical_name,
    "upload_date": Document.created_at,
    "status": Document.status,
}


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


@router.get("/countries", summary="List countries that have documents")
async def list_countries_with_documents(
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    access_scope: Annotated[
        str | None,
        Query(description="Filter by access scope (e.g., 'base', 'user_private')"),
    ] = None,
    exclude_regions: Annotated[
        bool,
        Query(description="Exclude region codes (AFR, EAP, ECA, LAC, MNA, SAR, GLO)"),
    ] = True,
) -> JSONResponse:
    """
    Get a list of distinct country codes that have associated documents.

    Useful for scripts that need to generate reports for all available countries.
    By default, excludes region codes to return only actual country codes.
    """
    _require_user(auth_context)

    stmt = select(Document.country_code).where(Document.country_code.isnot(None)).distinct()

    if access_scope:
        stmt = stmt.where(Document.access_scope == access_scope)

    result = await db_session.execute(stmt)
    country_codes = [row[0] for row in result.fetchall() if row[0]]

    if exclude_regions:
        country_codes = [code for code in country_codes if code not in _REGION_CODES]

    # Sort alphabetically for consistency
    country_codes.sort()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "countries": country_codes,
            "count": len(country_codes),
            "request_id": request_context.request_id,
        },
    )


@router.get("", summary="List uploaded documents for the authenticated user")
async def list_documents(
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=1000)] = 20,
    search_name: Annotated[
        str | None,
        Query(description="Case-insensitive partial match on document name"),
    ] = None,
    tags: Annotated[list[str] | None, Query(description="Filter by tag (all must match)")] = None,
    content_hash: Annotated[
        list[str] | None,
        Query(description="Filter by SHA-256 content hash"),
    ] = None,
    doc_type: Annotated[
        Literal["regional", "country", "global"] | None,
        Query(alias="type", description="Filter by document type: regional, country, or global"),
    ] = None,
    country_code: Annotated[
        list[str] | None,
        Query(description="Filter by country code"),
    ] = None,
    created_after: Annotated[
        datetime | None,
        Query(description="Return documents created after this timestamp"),
    ] = None,
    created_before: Annotated[
        datetime | None,
        Query(description="Return documents created before this timestamp"),
    ] = None,
    sort_by: Annotated[
        Literal["country", "filename", "upload_date", "status"] | None,
        Query(description="Field to sort by"),
    ] = None,
    sort_order: Annotated[
        Literal["asc", "desc"],
        Query(description="Sort direction"),
    ] = "desc",
) -> JSONResponse:
    # user_id = _require_user(auth_context)
    # user_uuid = UUID(user_id)
    stmt = select(Document)  # .where(Document.owner_user_id == user_uuid)

    if search_name is not None:
        stmt = stmt.where(Document.canonical_name.ilike(f"%{search_name}%"))
    if tags is not None:
        stmt = stmt.where(Document.tags.contains(tags))
    if content_hash is not None:
        stmt = stmt.where(Document.content_hash.in_(content_hash))
    if doc_type == "regional":
        stmt = stmt.where(Document.country_code.in_(_REGION_ONLY_CODES))
    elif doc_type == "country":
        stmt = stmt.where(
            Document.country_code.isnot(None),
            Document.country_code.notin_(_REGION_ONLY_CODES | {"GLO"}),
        )
    elif doc_type == "global":
        stmt = stmt.where(Document.country_code == "GLO")
    if country_code is not None:
        stmt = stmt.where(Document.country_code.in_(country_code))
    if created_after is not None:
        stmt = stmt.where(Document.created_at >= created_after)
    if created_before is not None:
        stmt = stmt.where(Document.created_at <= created_before)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_count = (await db_session.execute(count_stmt)).scalar_one()

    sort_col = _CHAT_SORT_COLUMNS.get(sort_by or "upload_date", Document.created_at)
    order_fn = asc if sort_order == "asc" else desc
    rows = (
        (
            await db_session.execute(
                stmt.order_by(order_fn(sort_col))
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


@router.post("/upload-s3", summary="Upload PDF file to S3 only (no ingestion)")
async def upload_pdf_to_s3_endpoint(
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
    file: Annotated[UploadFile, File(...)],
) -> JSONResponse:
    """
    Upload a PDF file directly to S3 without ingestion.

    This endpoint is useful for batch uploads where you want to store files
    in S3 first and process them later.

    Returns:
        JSON with document_id (UUID) and s3_uri
    """
    _require_user(auth_context)

    if not settings.s3_housing_pdf_bucket:
        raise GatewayError(
            code="S3_NOT_CONFIGURED",
            message="S3 housing PDF bucket is not configured",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise GatewayError(
            code="VALIDATION_ERROR",
            message="Only PDF files are supported",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Generate document ID
    from uuid import uuid4

    document_id = uuid4()
    document_name = file.filename

    # Read file content
    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise GatewayError(
                code="VALIDATION_ERROR",
                message="File is empty",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
    except Exception as exc:
        raise GatewayError(
            code="UPLOAD_ERROR",
            message=f"Failed to read file: {exc}",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    # Upload to S3
    try:
        s3_uri = upload_pdf_to_s3(
            file_bytes=file_bytes,
            document_id=str(document_id),
            document_name=document_name,
            settings=settings,
        )
    except ValueError as exc:
        raise GatewayError(
            code="S3_NOT_CONFIGURED",
            message=str(exc),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    except RuntimeError as exc:
        raise GatewayError(
            code="S3_UPLOAD_FAILED",
            message=str(exc),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "document_id": str(document_id),
            "document_name": document_name,
            "s3_uri": s3_uri,
            "request_id": request_context.request_id,
        },
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
        settings.ingestion_base_url.rstrip("/") + f"/v1/documents/{document_id}/download"
    )
    timeout = httpx.Timeout(settings.ingestion_request_timeout_seconds)
    headers = {}
    if settings.ingestion_api_key:
        headers["Authorization"] = f"Bearer {settings.ingestion_api_key}"
    # Forward the user's auth token to ingestion service
    if auth_context.token:  # type: ignore[attr-defined]
        headers["Authorization"] = f"Bearer {auth_context.token}"  # type: ignore[attr-defined]

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
                        "content-disposition", 'attachment; filename="document.pdf"'
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
