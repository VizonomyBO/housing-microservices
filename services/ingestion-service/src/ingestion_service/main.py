from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import Response
from pydantic import HttpUrl
from sqlalchemy import select

from ingestion_service.auth import AuthError, UserContext, verify_token
from ingestion_service.db import DBSession, SettingsDep, dispose_engine, init_engine
from ingestion_service.pipeline import IngestionError, IngestionPipeline
from ingestion_service.schemas import (
    DocumentDownloadResponse,
    UploadCompleteResponse,
    UploadInitRequest,
    UploadInitResponse,
    UploadInfo,
)
from ingestion_service.settings import (
    ALLOWED_VOYAGE_OUTPUT_DIMENSIONS,
    Settings,
    get_settings,
)
from ingestion_service.signing import now_seconds, sign_payload, verify_signature
from ingestion_service.storage import S3Storage, StorageError
from shared_data_layer.config import SYSTEM_OWNER_SENTINEL
from shared_data_layer.db.models.documents import Document, UploadedFile

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    await init_engine(settings)
    app.state.pipeline = IngestionPipeline(settings)
    app.state.storage = S3Storage(settings)
    logger.info("Ingestion service initialized")
    try:
        yield
    finally:
        await dispose_engine()


app = FastAPI(title="Ingestion Service", version="0.1.0", lifespan=lifespan)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def _require_user(
    authorization: str | None,
    settings: Settings,
) -> UserContext:
    try:
        return await verify_token(authorization, settings)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post(
    "/v1/documents/upload",
    response_model=UploadInitResponse,
    summary="Register an upload and receive form fields",
)
async def request_upload(
    request: Request,
    payload: UploadInitRequest,
    authorization: str | None = Header(default=None, convert_underscores=False),
    settings: Settings = Depends(get_settings),
) -> UploadInitResponse:
    user = await _require_user(authorization, settings)
    if not settings.signing_secret:
        raise HTTPException(
            status_code=500,
            detail="Signing secret is not configured",
        )
    if payload.source_type not in settings.allowed_source_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source_type '{payload.source_type}'",
        )
    if payload.file_size_bytes > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=413,
            detail="file_size_bytes exceeds configured maximum",
        )
    output_dimension = payload.output_dimension or settings.voyage_output_dimension
    if output_dimension != settings.vector_store_dimension:
        raise HTTPException(
            status_code=400,
            detail=(
                f"output_dimension {output_dimension} must match configured vector_store_dimension "
                f"{settings.vector_store_dimension}"
            ),
        )
    expires_at = now_seconds() + settings.upload_ttl_seconds
    document_id = uuid4()
    ingestion_id = uuid4()
    owner_field = user.user_id if payload.access_scope != "base" else ""

    fields: dict[str, Any] = {
        "document_id": str(document_id),
        "ingestion_id": str(ingestion_id),
        "owner_user_id": owner_field,
        "access_scope": payload.access_scope,
        "country_code": payload.country_code or "",
        "language": payload.language,
        "tags": json.dumps(payload.tags or []),
        "metadata": json.dumps(payload.metadata or {}),
        "document_name": payload.document_name,
        "source_type": payload.source_type,
        "output_dimension": str(output_dimension),
        "callback_url": str(payload.callback_url) if payload.callback_url else "",
        "trace_id": payload.trace_id or "",
        "expires_at": str(expires_at),
        "file_size_bytes": str(payload.file_size_bytes),
    }

    signature = sign_payload(fields, settings.signing_secret)
    fields["signature"] = signature

    upload_url = str(request.base_url).rstrip("/") + "/v1/documents/upload/complete"
    upload_info = UploadInfo(
        url=upload_url,
        fields={k: str(v) for k, v in fields.items()},
        expires_in_sec=settings.upload_ttl_seconds,
    )
    return UploadInitResponse(
        document_id=document_id,
        ingestion_id=ingestion_id,
        status="registered",
        upload=upload_info,
        message="Upload registered; POST form-data to upload.url",
    )


def _parse_json_field(raw: str | None, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _parse_owner(raw_owner: str) -> UUID | None:
    candidate = (raw_owner or "").strip()
    if not candidate:
        return None
    try:
        owner_uuid = UUID(candidate)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid owner_user_id") from exc
    if owner_uuid == SYSTEM_OWNER_SENTINEL:
        return SYSTEM_OWNER_SENTINEL
    return owner_uuid


@app.post(
    "/v1/documents/upload/complete",
    response_model=UploadCompleteResponse,
    summary="Upload binary and run synchronous ingestion",
)
async def complete_upload(
    request: Request,
    db: DBSession,
    settings: SettingsDep,
    document_id: str = Form(...),
    ingestion_id: str = Form(...),
    owner_user_id: str = Form(...),
    access_scope: str = Form(...),
    country_code: str | None = Form(None),
    language: str = Form("en"),
    tags: str | None = Form(None),
    metadata: str | None = Form(None),
    document_name: str = Form(...),
    source_type: str = Form(...),
    output_dimension: str | None = Form(None),
    callback_url: str | None = Form(None),
    trace_id: str | None = Form(None),
    expires_at: str = Form(...),
    file_size_bytes: str = Form(...),
    signature: str = Form(...),
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None, convert_underscores=False),
) -> UploadCompleteResponse:
    # Validate signature + expiry
    if not settings.signing_secret:
        raise HTTPException(status_code=500, detail="Signing secret is not configured")
    fields = {
        "document_id": document_id,
        "ingestion_id": ingestion_id,
        "owner_user_id": owner_user_id,
        "access_scope": access_scope,
        "country_code": country_code or "",
        "language": language,
        "tags": tags or "[]",
        "metadata": metadata or "{}",
        "document_name": document_name,
        "source_type": source_type,
        "output_dimension": output_dimension or "",
        "callback_url": callback_url or "",
        "trace_id": trace_id or "",
        "expires_at": expires_at,
        "file_size_bytes": file_size_bytes,
    }
    if not verify_signature(fields, signature, settings.signing_secret):
        raise HTTPException(status_code=400, detail="Invalid signature")
    if now_seconds() > int(expires_at):
        raise HTTPException(status_code=410, detail="Upload request expired")

    # Optional auth on completion to mirror upstream clients
    try:
        document_uuid = UUID(document_id)
        ingestion_uuid = UUID(ingestion_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid identifiers") from exc

    if source_type not in settings.allowed_source_types:
        raise HTTPException(
            status_code=400, detail=f"Unsupported source_type '{source_type}'"
        )
    owner_uuid = _parse_owner(owner_user_id)
    if access_scope != "base" and owner_uuid is None:
        raise HTTPException(
            status_code=400, detail="owner_user_id required for non-base uploads"
        )

    tags_list = _parse_json_field(tags, [])
    metadata_obj = _parse_json_field(metadata, {})
    try:
        declared_size = int(file_size_bytes)
    except ValueError:
        declared_size = 0
    try:
        resolved_dimension = (
            int(output_dimension)
            if output_dimension
            else settings.voyage_output_dimension
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid output_dimension") from exc
    if resolved_dimension not in ALLOWED_VOYAGE_OUTPUT_DIMENSIONS:
        raise HTTPException(status_code=400, detail="Invalid output_dimension")
    if resolved_dimension != settings.vector_store_dimension:
        raise HTTPException(
            status_code=400,
            detail=(
                f"output_dimension {resolved_dimension} must match configured vector_store_dimension "
                f"{settings.vector_store_dimension}"
            ),
        )

    payload = UploadInitRequest(
        document_name=document_name,
        source_type=source_type,
        country_code=country_code or None,
        language=language,
        tags=tags_list,
        file_size_bytes=declared_size or 1,
        access_scope=access_scope,
        callback_url=None if not callback_url else cast(HttpUrl, callback_url),
        metadata=metadata_obj,
        trace_id=trace_id or None,
        output_dimension=resolved_dimension,
    )

    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="File is empty")
    actual_size = len(body)
    if declared_size and actual_size > declared_size + 1024:
        raise HTTPException(
            status_code=400, detail="Uploaded file exceeds declared size"
        )
    if actual_size > settings.max_file_size_bytes:
        raise HTTPException(status_code=413, detail="File exceeds max_file_size_bytes")
    payload.file_size_bytes = actual_size

    try:
        pipeline: IngestionPipeline = request.app.state.pipeline
        document, job = await pipeline.ingest_file(
            session=db,
            request=payload,
            owner_user_id=owner_uuid,
            document_id=document_uuid,
            ingestion_id=ingestion_uuid,
            file_bytes=body,
        )
        await db.commit()
    except IngestionError as exc:
        await db.commit()
        logger.exception("Ingestion failed for %s", document_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        await db.rollback()
        logger.exception("Unexpected failure")
        raise HTTPException(
            status_code=500, detail="Unexpected ingestion failure"
        ) from exc

    return UploadCompleteResponse(
        document_id=document.id,
        ingestion_id=job.id,
        status=document.status,
        content_hash=document.content_hash,
        message="Ingestion completed"
        if document.status == "active"
        else "Ingestion failed",
    )


@app.get(
    "/v1/documents/{document_id}/download",
    response_model=DocumentDownloadResponse,
    summary="Get a presigned URL to download the original document file",
)
async def download_document(
    request: Request,
    document_id: UUID,
    db: DBSession,
    settings: SettingsDep,
    authorization: str | None = Header(default=None, convert_underscores=False),
) -> DocumentDownloadResponse:
    """
    Generate a presigned URL to download the original uploaded document.

    The URL is valid for 1 hour by default.
    """
    user = await _require_user(authorization, settings)

    # Find the document
    doc_stmt = select(Document).where(
        Document.id == document_id,
        Document.deleted_at.is_(None),
    )
    result = await db.execute(doc_stmt)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Check access permissions
    if document.access_scope == "user_private":
        if document.owner_user_id != UUID(user.user_id):
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this document",
            )
    elif document.access_scope == "user_shared":
        # For shared docs, owner or anyone in a conversation with it can access
        # For now, allow if user is the owner
        if (
            document.owner_user_id
            and document.owner_user_id != UUID(user.user_id)
            and document.owner_user_id != SYSTEM_OWNER_SENTINEL
        ):
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this document",
            )
    # base documents are accessible to all authenticated users

    # Find the uploaded file record
    file_stmt = select(UploadedFile).where(UploadedFile.document_id == document_id)
    file_result = await db.execute(file_stmt)
    uploaded_file = file_result.scalar_one_or_none()

    if not uploaded_file:
        raise HTTPException(
            status_code=404,
            detail="Original file not available for download",
        )

    # Get the source type from metadata or infer from storage URI
    source_type = "pdf"  # default
    if uploaded_file.ingestion_metadata:
        source_type = uploaded_file.ingestion_metadata.get("source_type", "pdf")

    # Generate presigned download URL
    storage: S3Storage = request.app.state.storage
    expires_in = 3600  # 1 hour

    try:
        download_url = await storage.get_download_url(
            uploaded_file.storage_uri,
            expires_in=expires_in,
        )
    except StorageError as exc:
        logger.exception("Failed to generate download URL for document %s", document_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate download URL: {exc}",
        ) from exc

    return DocumentDownloadResponse(
        document_id=document.id,
        document_name=document.canonical_name,
        source_type=source_type,
        download_url=download_url,
        expires_in_sec=expires_in,
        byte_size=uploaded_file.byte_size,
    )


@app.get(
    "/v1/documents/{document_id}/download/direct",
    summary="Download the original document file directly",
    responses={
        200: {
            "description": "The document file",
            "content": {"application/octet-stream": {}},
        }
    },
)
async def download_document_direct(
    request: Request,
    document_id: UUID,
    db: DBSession,
    settings: SettingsDep,
    authorization: str | None = Header(default=None, convert_underscores=False),
) -> Response:
    """
    Download the original uploaded document file directly.

    Returns the file bytes with appropriate content-type and filename headers.
    """
    user = await _require_user(authorization, settings)

    # Find the document
    doc_stmt = select(Document).where(
        Document.id == document_id,
        Document.deleted_at.is_(None),
    )
    result = await db.execute(doc_stmt)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Check access permissions
    if document.access_scope == "user_private":
        if document.owner_user_id != UUID(user.user_id):
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this document",
            )
    elif document.access_scope == "user_shared":
        if (
            document.owner_user_id
            and document.owner_user_id != UUID(user.user_id)
            and document.owner_user_id != SYSTEM_OWNER_SENTINEL
        ):
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this document",
            )

    # Find the uploaded file record
    file_stmt = select(UploadedFile).where(UploadedFile.document_id == document_id)
    file_result = await db.execute(file_stmt)
    uploaded_file = file_result.scalar_one_or_none()

    if not uploaded_file:
        raise HTTPException(
            status_code=404,
            detail="Original file not available for download",
        )

    # Get source type and determine content type
    source_type = "pdf"
    if uploaded_file.ingestion_metadata:
        source_type = uploaded_file.ingestion_metadata.get("source_type", "pdf")

    content_type_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "txt": "text/plain",
        "md": "text/markdown",
        "html": "text/html",
        "json": "application/json",
    }
    content_type = content_type_map.get(source_type, "application/octet-stream")

    # Download from S3
    storage: S3Storage = request.app.state.storage
    try:
        file_bytes = await storage.download(uploaded_file.storage_uri)
    except StorageError as exc:
        logger.exception("Failed to download document %s from storage", document_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to download file: {exc}",
        ) from exc

    # Build filename
    filename = document.canonical_name
    if not filename.lower().endswith(f".{source_type}"):
        filename = f"{filename}.{source_type}"

    return Response(
        content=file_bytes,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(file_bytes)),
        },
    )


def create_app() -> FastAPI:
    return app
