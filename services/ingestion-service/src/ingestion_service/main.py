from __future__ import annotations

import gc
import hashlib
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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
from fastapi import status as http_status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import HttpUrl
from shared_data_layer.config import SYSTEM_OWNER_SENTINEL
from shared_data_layer.db.models import ChatResponseCache
from shared_data_layer.db.models.documents import DocumentUpload
from shared_data_layer.repositories.documents import DocumentRepository, DocumentUploadRepository
from sqlalchemy import and_, func, select, update

from ingestion_service.auth import AuthError, UserContext, verify_token
from ingestion_service.db import DBSession, SettingsDep, dispose_engine, init_engine
from ingestion_service.pipeline import IngestionError, IngestionPipeline
from ingestion_service.s3 import (
    download_pdf_from_s3,
    download_pdf_from_s3_by_name,
    upload_pdf_to_s3,
)
from ingestion_service.schemas import (
    AdminCountryReprocessStatusResponse,
    AdminDocumentUploadListResponse,
    AdminDocumentUploadResponse,
    PaginationMetadata,
    UploadCompleteResponse,
    UploadInfo,
    UploadInitRequest,
    UploadInitResponse,
)
from ingestion_service.settings import (
    ALLOWED_VOYAGE_OUTPUT_DIMENSIONS,
    Settings,
    get_settings,
)
from ingestion_service.signing import now_seconds, sign_payload, verify_signature
from ingestion_service.storage import S3StorageClient

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
        CORSMiddleware,  # type: ignore[arg-type]
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


@app.get("/v1/db-status", include_in_schema=False)
async def database_status(
    db: DBSession,
    settings: SettingsDep,
) -> dict[str, Any]:
    """Check current database connection details and verify connectivity."""
    try:
        from sqlalchemy import text

        # Get database configuration from settings
        db_url = settings.database_url

        # Parse connection details
        import re

        host_match = re.search(r"@([^:]+):", db_url)
        db_match = re.search(r"/([^?]+)(\?|$)", db_url)

        host = host_match.group(1) if host_match else "unknown"
        database = db_match.group(1) if db_match else "unknown"

        # Test actual connection and get row counts
        doc_result = await db.execute(text("SELECT COUNT(*) FROM documents"))
        doc_count = doc_result.scalar()

        # Get latest document
        latest_doc = await db.execute(
            text(
                "SELECT canonical_name, created_at FROM documents ORDER BY created_at DESC LIMIT 1"
            )
        )
        latest = latest_doc.fetchone()

        return {
            "status": "connected",
            "database": {"host": host, "database_name": database, "connection_status": "active"},
            "stats": {
                "total_documents": doc_count,
                "latest_document": {
                    "name": latest[0] if latest else None,
                    "created_at": str(latest[1]) if latest else None,
                }
                if latest
                else None,
            },
        }
    except Exception as e:
        return {
            "status": "error",
            "database": {
                "host": host if "host" in locals() else "unknown",
                "database_name": database if "database" in locals() else "unknown",
                "connection_status": "failed",
            },
            "error": str(e),
        }


async def _require_user(
    authorization: str | None,
    settings: Settings,
) -> UserContext:
    try:
        return await verify_token(authorization, settings)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/v1/admin/documents/upload", response_model=AdminDocumentUploadResponse)
async def admin_upload_document(
    db: DBSession,
    settings: SettingsDep,
    country_code: str = Form(...),
    source: str = Form(...),
    metadata: str | None = Form(None),
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None, convert_underscores=False),
) -> dict[str, Any]:
    user = await _require_user(authorization, settings)
    uploader_id = _parse_user_uuid(user)
    normalized_country = country_code.upper().strip()
    if len(normalized_country) != 3:
        raise HTTPException(status_code=400, detail="country_code must be ISO-3")
    if file.filename is None or file.filename.strip() == "":
        raise HTTPException(status_code=400, detail="filename is required")

    filename = file.filename.strip()
    source_type = _infer_source_type(filename)
    if source_type not in settings.allowed_source_types:
        raise HTTPException(status_code=400, detail=f"Unsupported source_type '{source_type}'")

    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="File is empty")
    if len(body) > settings.max_file_size_bytes:
        raise HTTPException(status_code=413, detail="File exceeds max_file_size_bytes")

    metadata_obj = _parse_json_field(metadata, {})
    if not isinstance(metadata_obj, dict):
        metadata_obj = {}
    metadata_obj["source_type"] = source_type

    storage_client = S3StorageClient(settings)
    raw_storage_document_id = uuid4()
    try:
        storage_uri = storage_client.upload_document(
            document_id=raw_storage_document_id,
            file_bytes=body,
            content_type=file.content_type or "application/octet-stream",
            source_type=source_type,
            filename=filename,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to store file: {exc}") from exc

    repo = DocumentUploadRepository(db)
    upload = await repo.create_upload(
        country_code=normalized_country,
        filename=filename,
        storage_uri=storage_uri,
        byte_size=len(body),
        content_hash=hashlib.sha256(body).hexdigest(),
        source=source,
        uploaded_by=uploader_id,
        metadata_=metadata_obj,
    )
    await db.commit()
    return {"upload": _serialize_document_upload(upload)}


@app.get("/v1/admin/documents", response_model=AdminDocumentUploadListResponse)
async def admin_list_documents(
    db: DBSession,
    settings: SettingsDep,
    country_code: str | None = None,
    verified: bool | None = None,
    reprocess_status: str | None = None,
    approved_and_done_only: bool | None = None,
    page: int = 1,
    page_size: int = 20,
    authorization: str | None = Header(default=None, convert_underscores=False),
) -> dict[str, Any]:
    await _require_user(authorization, settings)
    normalized_country = country_code.upper().strip() if country_code is not None else None

    filters = []
    if normalized_country is not None:
        filters.append(DocumentUpload.country_code == normalized_country)
    if approved_and_done_only is True:
        filters.append(DocumentUpload.verified.is_(True))
        filters.append(DocumentUpload.reprocess_status == "done")
    elif approved_and_done_only is False:
        filters.append(
            ~and_(
                DocumentUpload.verified.is_(True),
                DocumentUpload.reprocess_status == "done",
            )
        )

    if verified is not None:
        filters.append(DocumentUpload.verified == verified)
    if reprocess_status is not None:
        filters.append(DocumentUpload.reprocess_status == reprocess_status)

    base_stmt = select(DocumentUpload)
    if filters:
        base_stmt = base_stmt.where(and_(*filters))

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total_count = (await db.execute(count_stmt)).scalar_one()

    rows_stmt = (
        base_stmt.order_by(DocumentUpload.created_at.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    result = await db.execute(rows_stmt)
    uploads = list(result.scalars().all())

    return {
        "items": [_serialize_document_upload(u) for u in uploads],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "has_next": (page * page_size) < total_count,
        },
    }


@app.get(
    "/v1/admin/documents/reprocess-status",
    response_model=AdminCountryReprocessStatusResponse,
)
async def admin_reprocess_status(
    db: DBSession,
    settings: SettingsDep,
    authorization: str | None = Header(default=None, convert_underscores=False),
) -> dict[str, Any]:
    await _require_user(authorization, settings)
    stmt = (
        select(
            DocumentUpload.country_code,
            DocumentUpload.reprocess_status,
            func.count(DocumentUpload.id),
        )
        .where(DocumentUpload.verified.is_(True))
        .group_by(DocumentUpload.country_code, DocumentUpload.reprocess_status)
    )
    result = await db.execute(stmt)
    status_rows = result.all()
    per_country: dict[str, dict[str, int]] = {}
    for country, status, count in status_rows:
        if country not in per_country:
            per_country[country] = {}
        per_country[country][status] = int(count)

    items: list[dict[str, Any]] = []
    for country, counts in per_country.items():
        items.append(
            {
                "country_code": country,
                "counts": counts,
                "total": int(sum(counts.values())),
            }
        )
    items.sort(key=lambda item: item["country_code"])
    return {"items": items, "count": len(items)}


@app.get("/v1/admin/documents/{upload_id}", response_model=AdminDocumentUploadResponse)
async def admin_get_document(
    upload_id: str,
    db: DBSession,
    settings: SettingsDep,
    authorization: str | None = Header(default=None, convert_underscores=False),
) -> dict[str, Any]:
    await _require_user(authorization, settings)
    try:
        upload_uuid = UUID(upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid upload_id") from exc

    repo = DocumentUploadRepository(db)
    upload = await repo.get_upload(upload_uuid)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    return {"upload": _serialize_document_upload(upload)}


@app.patch(
    "/v1/admin/documents/{upload_id}/approve",
    response_model=AdminDocumentUploadResponse,
    status_code=http_status.HTTP_202_ACCEPTED,
)
async def admin_approve_document(
    upload_id: str,
    db: DBSession,
    settings: SettingsDep,
    authorization: str | None = Header(default=None, convert_underscores=False),
) -> dict[str, Any]:
    user = await _require_user(authorization, settings)
    approver_id = _parse_user_uuid(user)
    try:
        upload_uuid = UUID(upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid upload_id") from exc

    repo = DocumentUploadRepository(db)
    upload = await repo.get_upload(upload_uuid)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload.verified and upload.reprocess_status in {
        "queued",
        "ingesting",
        "reprocessing_cache",
        "reprocessing_pdf",
        "done",
    }:
        raise HTTPException(status_code=409, detail="Upload already approved")

    now = datetime.now(timezone.utc)
    await repo.set_verified(
        upload_id=upload_uuid,
        verified=True,
        verified_by=approver_id,
        verified_at=now,
    )
    await repo.queue_upload(upload_id=upload_uuid)
    await db.commit()

    refreshed = await repo.get_upload(upload_uuid)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="Upload not found after approval")
    return {"upload": _serialize_document_upload(refreshed)}


@app.patch("/v1/admin/documents/{upload_id}/reject", response_model=AdminDocumentUploadResponse)
async def admin_reject_document(
    upload_id: str,
    db: DBSession,
    settings: SettingsDep,
    authorization: str | None = Header(default=None, convert_underscores=False),
) -> dict[str, Any]:
    user = await _require_user(authorization, settings)
    reviewer_id = _parse_user_uuid(user)
    try:
        upload_uuid = UUID(upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid upload_id") from exc

    repo = DocumentUploadRepository(db)
    upload = await repo.get_upload(upload_uuid)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")

    now = datetime.now(timezone.utc)
    await repo.set_verified(
        upload_id=upload_uuid,
        verified=False,
        verified_by=reviewer_id,
        verified_at=now,
    )
    await repo.update_reprocess_status(
        upload_id=upload_uuid,
        status="failed",
        error="rejected",
        completed_at=now,
    )
    await db.commit()
    refreshed = await repo.get_upload(upload_uuid)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="Upload not found after reject")
    return {"upload": _serialize_document_upload(refreshed)}


@app.delete("/v1/admin/documents/{upload_id}")
async def admin_delete_document(
    upload_id: str,
    db: DBSession,
    settings: SettingsDep,
    authorization: str | None = Header(default=None, convert_underscores=False),
) -> dict[str, Any]:
    await _require_user(authorization, settings)
    try:
        upload_uuid = UUID(upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid upload_id") from exc

    repo = DocumentUploadRepository(db)
    upload = await repo.get_upload(upload_uuid)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")

    storage_client = S3StorageClient(settings)
    try:
        storage_client.delete_document(storage_uri=upload.storage_uri)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to delete stored file: {exc}") from exc

    deleted = await repo.delete(upload_uuid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Upload not found")
    await db.commit()
    return {"deleted": True, "upload_id": upload_id}


def _resolve_internal_worker_secret(settings: Settings) -> str | None:
    if settings.auth_shared_secret is not None and settings.auth_shared_secret.strip() != "":
        return settings.auth_shared_secret
    if settings.jwt_secret_key is not None and settings.jwt_secret_key.strip() != "":
        return settings.jwt_secret_key
    return None


def _require_internal_worker_secret(
    worker_secret: str | None,
    settings: Settings,
) -> None:
    expected_secret = _resolve_internal_worker_secret(settings)
    if expected_secret is None:
        raise HTTPException(status_code=500, detail="Internal worker secret not configured")
    if worker_secret is None or worker_secret != expected_secret:
        raise HTTPException(status_code=401, detail="Invalid internal worker secret")


async def _ingest_approved_upload(
    *,
    upload_uuid: UUID,
    request: Request,
    db: DBSession,
    settings: Settings,
) -> dict[str, Any]:
    repo = DocumentUploadRepository(db)
    upload = await repo.get_upload(upload_uuid)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    if not upload.verified:
        raise HTTPException(status_code=409, detail="Upload must be approved first")
    if upload.document_id is not None and upload.reprocess_status in {
        "reprocessing_cache",
        "reprocessing_pdf",
        "done",
    }:
        return {"upload": _serialize_document_upload(upload)}

    now = datetime.now(timezone.utc)
    await repo.update_reprocess_status(
        upload_id=upload_uuid,
        status="ingesting",
        error=None,
        started_at=now,
    )
    await db.commit()

    source_type = _infer_source_type(upload.filename)
    if source_type not in settings.allowed_source_types:
        await repo.update_reprocess_status(
            upload_id=upload_uuid,
            status="failed",
            error=f"Unsupported source_type '{source_type}'",
            completed_at=datetime.now(timezone.utc),
        )
        await db.commit()
        raise HTTPException(status_code=400, detail=f"Unsupported source_type '{source_type}'")

    storage_client = S3StorageClient(settings)
    try:
        body = storage_client.download_document(storage_uri=upload.storage_uri)
    except Exception as exc:
        await repo.update_reprocess_status(
            upload_id=upload_uuid,
            status="failed",
            error=f"Failed to fetch stored file: {exc}",
            completed_at=datetime.now(timezone.utc),
        )
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Failed to fetch stored file: {exc}") from exc

    metadata_obj = upload.metadata_ if isinstance(upload.metadata_, dict) else {}
    language_value = metadata_obj.get("language", "en")
    language = str(language_value) if language_value is not None else "en"
    tags_value = metadata_obj.get("tags", [])
    tags_list = tags_value if isinstance(tags_value, list) else []
    access_scope_value = metadata_obj.get("access_scope", "base")
    access_scope = str(access_scope_value) if access_scope_value is not None else "base"
    trace_id_value = metadata_obj.get("trace_id")
    trace_id = str(trace_id_value) if trace_id_value is not None else None

    payload = UploadInitRequest(
        document_name=upload.filename,
        source_type=source_type,
        country_code=upload.country_code,
        language=language,
        tags=tags_list,
        file_size_bytes=upload.byte_size,
        access_scope=access_scope,
        callback_url=None,
        metadata=metadata_obj,
        trace_id=trace_id,
        output_dimension=settings.voyage_output_dimension,
    )

    pipeline: IngestionPipeline = request.app.state.pipeline
    document_uuid = uuid4()
    ingestion_uuid = uuid4()

    async def _progress_callback(progress: dict[str, int]) -> None:
        await repo.set_ingestion_progress(
            upload_id=upload_uuid,
            total_chunks=progress["total_chunks"],
            total_batches=progress["total_batches"],
            processed_chunks=progress["processed_chunks"],
            processed_batches=progress["processed_batches"],
            batch_size=progress["batch_size"],
        )

    try:
        document, _ = await pipeline.ingest_file(
            session=db,
            request=payload,
            owner_user_id=None,
            document_id=document_uuid,
            ingestion_id=ingestion_uuid,
            file_bytes=body,
            progress_callback=_progress_callback,
        )
        await repo.set_document_link(upload_id=upload_uuid, document_id=document.id)
        await repo.update_reprocess_status(
            upload_id=upload_uuid,
            status="reprocessing_cache",
            error=None,
        )
        await db.execute(
            update(ChatResponseCache)
            .where(ChatResponseCache.country_code == upload.country_code)
            .values(status="stale")
        )
        await db.commit()
    except IngestionError as exc:
        await db.rollback()
        await repo.update_reprocess_status(
            upload_id=upload_uuid,
            status="failed",
            error=str(exc),
            completed_at=datetime.now(timezone.utc),
        )
        await db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        await repo.update_reprocess_status(
            upload_id=upload_uuid,
            status="failed",
            error=str(exc),
            completed_at=datetime.now(timezone.utc),
        )
        await db.commit()
        raise HTTPException(status_code=500, detail="Unexpected ingestion failure") from exc
    finally:
        del body
        gc.collect()

    refreshed = await repo.get_upload(upload_uuid)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="Upload not found after ingestion")
    return {"upload": _serialize_document_upload(refreshed)}


@app.post(
    "/v1/internal/admin/documents/{upload_id}/ingest",
    response_model=AdminDocumentUploadResponse,
)
async def internal_ingest_approved_document(
    upload_id: str,
    request: Request,
    db: DBSession,
    settings: SettingsDep,
    x_worker_secret: str | None = Header(default=None, alias="X-Worker-Secret"),
) -> dict[str, Any]:
    _require_internal_worker_secret(x_worker_secret, settings)
    try:
        upload_uuid = UUID(upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid upload_id") from exc
    return await _ingest_approved_upload(
        upload_uuid=upload_uuid,
        request=request,
        db=db,
        settings=settings,
    )


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


def _parse_user_uuid(user: UserContext) -> UUID:
    try:
        return UUID(user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid authenticated user id") from exc


def _infer_source_type(filename: str) -> str:
    if "." not in filename:
        return "pdf"
    return filename.rsplit(".", 1)[1].lower()


def _extract_ingestion_progress(metadata: Any) -> dict[str, int] | None:
    if not isinstance(metadata, dict):
        return None
    raw_progress = metadata.get("ingestion_progress")
    if not isinstance(raw_progress, dict):
        return None
    keys = (
        "total_chunks",
        "total_batches",
        "processed_chunks",
        "processed_batches",
        "batch_size",
    )
    progress: dict[str, int] = {}
    for key in keys:
        value = raw_progress.get(key)
        if value is None:
            return None
        try:
            progress[key] = int(value)
        except (TypeError, ValueError):
            return None
    return progress


def _serialize_document_upload(upload: Any) -> dict[str, Any]:
    return {
        "id": str(upload.id),
        "country_code": upload.country_code,
        "filename": upload.filename,
        "storage_uri": upload.storage_uri,
        "byte_size": upload.byte_size,
        "content_hash": upload.content_hash,
        "source": upload.source,
        "uploaded_by": str(upload.uploaded_by),
        "verified": upload.verified,
        "verified_by": str(upload.verified_by) if upload.verified_by is not None else None,
        "verified_at": upload.verified_at.isoformat() if upload.verified_at is not None else None,
        "document_id": str(upload.document_id) if upload.document_id is not None else None,
        "reprocess_status": upload.reprocess_status,
        "reprocess_error": upload.reprocess_error,
        "reprocess_started_at": upload.reprocess_started_at.isoformat()
        if upload.reprocess_started_at is not None
        else None,
        "reprocess_completed_at": upload.reprocess_completed_at.isoformat()
        if upload.reprocess_completed_at is not None
        else None,
        "ingestion_progress": _extract_ingestion_progress(upload.metadata_),
        "metadata": upload.metadata_,
        "created_at": upload.created_at.isoformat(),
        "updated_at": upload.updated_at.isoformat(),
    }


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
        raise HTTPException(status_code=400, detail=f"Unsupported source_type '{source_type}'")
    owner_uuid = _parse_owner(owner_user_id)
    if access_scope != "base" and owner_uuid is None:
        raise HTTPException(status_code=400, detail="owner_user_id required for non-base uploads")

    tags_list = _parse_json_field(tags, [])
    metadata_obj = _parse_json_field(metadata, {})
    try:
        declared_size = int(file_size_bytes)
    except ValueError:
        declared_size = 0
    try:
        resolved_dimension = (
            int(output_dimension) if output_dimension else settings.voyage_output_dimension
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
        raise HTTPException(status_code=400, detail="Uploaded file exceeds declared size")
    if actual_size > settings.max_file_size_bytes:
        raise HTTPException(status_code=413, detail="File exceeds max_file_size_bytes")
    payload.file_size_bytes = actual_size

    try:
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
                logger.warning("Failed to upload PDF to S3 (continuing with ingestion): %s", exc)

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
            raise HTTPException(status_code=500, detail="Unexpected ingestion failure") from exc

        return UploadCompleteResponse(
            document_id=document.id,
            ingestion_id=job.id,
            status=document.status,
            content_hash=document.content_hash,
            message="Ingestion completed" if document.status == "active" else "Ingestion failed",
        )
    finally:
        del body
        gc.collect()


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
        raise HTTPException(status_code=500, detail="S3 housing PDF bucket is not configured")

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
        raise HTTPException(status_code=403, detail="Access denied to this document")

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
        raise HTTPException(status_code=500, detail=f"Failed to download PDF: {error_msg}") from exc
    except Exception as exc:
        logger.exception("Unexpected error during PDF download")
        raise HTTPException(status_code=500, detail="Unexpected error during download") from exc


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

    First looks up the DocumentUpload record by filename to get the exact storage_uri,
    then falls back to a bucket-wide search for documents uploaded via the legacy flow.
    Requires authentication.
    """
    await _require_user(authorization, settings)

    if not settings.s3_housing_pdf_bucket:
        raise HTTPException(status_code=500, detail="S3 housing PDF bucket is not configured")

    upload_repo = DocumentUploadRepository(db)
    upload = await upload_repo.get_latest_by_filename(canonical_name)

    if upload is not None:
        storage_client = S3StorageClient(settings)
        try:
            file_bytes = storage_client.download_document(storage_uri=upload.storage_uri)
        except RuntimeError as exc:
            error_msg = str(exc)
            if "not found" in error_msg.lower():
                raise HTTPException(
                    status_code=404,
                    detail=f"PDF file not found in S3 for document '{canonical_name}'",
                ) from exc
            raise HTTPException(status_code=500, detail=f"Failed to download PDF: {error_msg}") from exc
    else:
        try:
            file_bytes = download_pdf_from_s3_by_name(
                document_name=canonical_name,
                settings=settings,
            )
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except RuntimeError as exc:
            error_msg = str(exc)
            if "not found" in error_msg.lower():
                raise HTTPException(
                    status_code=404,
                    detail=f"PDF file not found in S3 for document '{canonical_name}'",
                ) from exc
            raise HTTPException(status_code=500, detail=f"Failed to download PDF: {error_msg}") from exc

    return Response(
        content=file_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{canonical_name}"',
            "Content-Length": str(len(file_bytes)),
        },
    )


def create_app() -> FastAPI:
    return app
