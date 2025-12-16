"""FastAPI router for document upload operations."""

from __future__ import annotations

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
    get_rate_limiter,
    get_request_context,
    get_settings,
)
from agent_api.http.errors import GatewayError
from agent_api.http.rate_limit import RateLimiterProtocol
from agent_api.http.schemas import DocumentListItem, DocumentListResponse, PaginationMetadata
from agent_api.reduced_scope import reduced_scope_demo_metadata
from agent_api.settings import Settings
from services import (
    DocumentListEntry,
    DocumentListingService,
    PaginationWindow,
)

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
        country_codes=country_code or [],
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


def _build_demo_headers(
    rate_limiter: RateLimiterProtocol,
    settings: Settings,
) -> dict[str, str]:
    headers = dict(rate_limiter.response_headers())
    if settings.reduced_scope.text_only_mode():
        headers.setdefault("X-Cache-Mode", "text-only")
        headers.setdefault("Viz-Demo-Mode", "text-only")
    return headers


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


__all__ = ["router"]
