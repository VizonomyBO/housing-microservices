"""FastAPI router for document upload and listing operations."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from shared_data_layer.db.models.documents import Document
from shared_data_layer.repositories.documents import UploadedFileRepository
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.deps import get_auth_context, get_db_session, get_request_context, get_settings
from agent_api.http.errors import GatewayError
from agent_api.http.schemas import DocumentListItem, DocumentListResponse, PaginationMetadata
from agent_api.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.get("", summary="List uploaded documents for the authenticated user")
async def list_documents(
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    tags: Annotated[list[str] | None, Query(description="Filter by tag (all must match)")] = None,
    content_hash: Annotated[
        list[str] | None,
        Query(description="Filter by SHA-256 content hash"),
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
) -> JSONResponse:
    user_id = _require_user(auth_context)
    user_uuid = UUID(user_id)
    stmt = select(Document).where(Document.owner_user_id == user_uuid)
    if tags:
        stmt = stmt.where(Document.tags.contains(tags))
    if content_hash:
        stmt = stmt.where(Document.content_hash.in_(content_hash))
    if country_code:
        stmt = stmt.where(Document.country_code.in_(country_code))
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
