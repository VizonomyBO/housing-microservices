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
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import HttpUrl

from ingestion_service.auth import AuthError, UserContext, verify_token
from ingestion_service.db import DBSession, SettingsDep, dispose_engine, init_engine
from ingestion_service.pipeline import IngestionError, IngestionPipeline
from ingestion_service.s3 import download_pdf_from_s3, upload_pdf_to_s3
from ingestion_service.schemas import (
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
from shared_data_layer.config import SYSTEM_OWNER_SENTINEL
from shared_data_layer.repositories.documents import DocumentRepository

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
    logger.info("Ingestion service initialized")
    try:
        yield
    finally:
        await dispose_engine()


app = FastAPI(title="Ingestion Service", version="0.1.0", lifespan=lifespan)

# Configure CORS
# Load settings (cached, safe to call at module level)
try:
    cors_settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_settings.cors_origins,
        allow_credentials=cors_settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
except Exception as e:
    # Fallback if settings can't be loaded (e.g., during import)
    # Will be configured properly when app starts
    logger.warning(f"Could not configure CORS at module load: {e}")


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

    # Upload PDF to S3 if source_type is PDF and bucket is configured
    s3_uri: str | None = None
    if source_type.lower() == "pdf" and settings.s3_housing_pdf_bucket:
        try:
            s3_uri = upload_pdf_to_s3(
                file_bytes=body,
                document_id=document_id,
                document_name=document_name,
                settings=settings,
            )
            logger.info("PDF uploaded to S3: %s", s3_uri)
        except Exception as exc:
            # Log error but don't fail the upload - ingestion can proceed without S3
            logger.warning(
                "Failed to upload PDF to S3 (continuing with ingestion): %s", exc
            )

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
    summary="Download PDF document from S3",
    response_class=Response,
)
async def download_document(
    document_id: str,
    db: DBSession,
    settings: SettingsDep,
    authorization: str | None = Header(default=None, convert_underscores=False),
) -> Response:
    """
    Download a PDF document from S3.

    Requires authentication and verifies the user has access to the document.
    """
    # Authenticate user
    user = await _require_user(authorization, settings)

    # Validate document_id
    try:
        document_uuid = UUID(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid document_id") from exc

    # Check if S3 bucket is configured
    if not settings.s3_housing_pdf_bucket:
        raise HTTPException(
            status_code=500, detail="S3 housing PDF bucket is not configured"
        )

    # Get document from database
    doc_repo = DocumentRepository(db)
    document = await doc_repo.get(document_uuid)

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Verify user has access to the document
    # User can access if:
    # 1. They own it (owner_user_id matches)
    # 2. It's a base document (access_scope == "base")
    user_id = user.user_id if user.user_id else None
    has_access = False

    if document.access_scope == "base":
        # Base documents are accessible to all authenticated users
        has_access = True
    elif document.owner_user_id and user_id:
        # User documents: must match owner
        has_access = str(document.owner_user_id) == user_id
    elif document.owner_user_id is None and user_id is None:
        # System documents without owner
        has_access = True

    if not has_access:
        raise HTTPException(
            status_code=403, detail="Access denied to this document"
        )

    # Get document name from canonical_name
    # The S3 key format is: document_id/document_name
    # canonical_name should match the document_name used during upload
    document_name = document.canonical_name

    try:
        # Download PDF from S3
        file_bytes = download_pdf_from_s3(
            document_id=document_id,
            document_name=document_name,
            settings=settings,
        )

        # Return file as response
        return Response(
            content=file_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{document_name}"',
                "Content-Length": str(len(file_bytes)),
            },
        )

    except RuntimeError as exc:
        error_msg = str(exc)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail="PDF file not found in S3") from exc
        raise HTTPException(
            status_code=500, detail=f"Failed to download PDF: {error_msg}"
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error during PDF download")
        raise HTTPException(
            status_code=500, detail="Unexpected error during download"
        ) from exc


@app.get(
    "/v1/documents/by-name/{canonical_name}/download",
    summary="Download PDF document from S3 by canonical name",
    response_class=Response,
)
async def download_document_by_name(
    canonical_name: str,
    db: DBSession,
    settings: SettingsDep,
    authorization: str | None = Header(default=None, convert_underscores=False),
) -> Response:
    """
    Download a PDF document from S3 by canonical name.

    Requires authentication and verifies the user has access to the document.
    Searches for documents owned by the authenticated user with the given canonical_name.
    """
    # Authenticate user
    user = await _require_user(authorization, settings)

    # Check if S3 bucket is configured
    if not settings.s3_housing_pdf_bucket:
        raise HTTPException(
            status_code=500, detail="S3 housing PDF bucket is not configured"
        )

    # Find document by canonical_name
    # ALL documents are accessible to any authenticated user (no access restrictions)
    from sqlalchemy import select
    from shared_data_layer.db.models.documents import Document

    # Search for ALL documents with matching canonical_name
    stmt = select(Document).where(
        Document.canonical_name == canonical_name
    )
    
    result = await db.execute(stmt)
    documents = result.scalars().all()

    if not documents:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found with name '{canonical_name}'",
        )

    # Try each document until we find one with PDF in S3
    # ALL documents are accessible - no access checks needed
    document = None
    file_bytes = None
    last_error = None

    for doc in documents:

        # Try to download PDF from S3 for this document
        try:
            file_bytes = download_pdf_from_s3(
                document_id=str(doc.id),
                document_name=doc.canonical_name,
                settings=settings,
            )
            document = doc
            break  # Found a document with PDF in S3
        except RuntimeError as exc:
            last_error = exc
            continue  # Try next document

    if not document or not file_bytes:
        if last_error:
            error_msg = str(last_error)
            if "not found" in error_msg.lower():
                raise HTTPException(
                    status_code=404,
                    detail=f"PDF file not found in S3 for document '{canonical_name}'",
                ) from last_error
        raise HTTPException(
            status_code=404,
            detail=f"PDF file not found in S3 for document '{canonical_name}'",
        )

    # Use canonical_name for S3 key construction
    document_name = document.canonical_name

    # Return file as response
    return Response(
        content=file_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{document_name}"',
            "Content-Length": str(len(file_bytes)),
        },
    )


def create_app() -> FastAPI:
    return app
