"""Finalize ingestion by activating documents or recording failures."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from common.db import get_async_session
from common.ingestion import VALID_STAGES, IngestionJobManager
from shared_data_layer.db.maintenance import (
    refresh_active_chunks_view,
    refresh_base_documents_cache_for_country,
)
from shared_data_layer.db.models.documents import Document

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_STATE_STAGE_MAP = {
    "emitconvertstarted": "convert",
    "convert": "convert",
    "emitchunkstarted": "chunk",
    "chunk": "chunk",
    "parallelprocessing": "chunk",
    "normalizetables": "chunk",
    "captionimages": "chunk",
    "embed": "embed",
    "emitembedstarted": "embed",
    "index": "index",
    "emitindexstarted": "index",
    "activate": "activate",
    "emitactivatestarted": "activate",
}


def handler(event: dict, context: Any) -> dict:
    """Lambda entry point."""
    return asyncio.run(async_handler(event))


async def async_handler(event: dict) -> dict:
    document_id = event.get("document_id")
    if not document_id:
        raise ValueError("document_id is required")

    document_uuid = UUID(str(document_id))
    ingestion_id = event.get("ingestion_id")
    status = event.get("status", "completed")
    trace_id = event.get("trace_id")
    timestamps = event.get("timestamps") or {}
    chunk_result = event.get("chunk_result") or {}
    content_hash = event.get("content_hash")
    byte_size = event.get("byte_size")
    error_info = event.get("error") or {}
    requested_stage = error_info.get("state") or event.get("failed_stage")
    stage_for_failure = _normalize_stage(requested_stage)
    success = status != "failed"

    async with get_async_session() as session:
        document = await session.get(Document, document_uuid)
        if document is None:
            raise LookupError(f"Document {document_id} not found")

        job_manager = IngestionJobManager(session)
        stage_for_job = "activate" if success else stage_for_failure
        # If Stage is invalid fall back to activate for logging completeness.
        if stage_for_job not in VALID_STAGES:
            stage_for_job = "activate"

        job = await job_manager.start_job(
            document_uuid,
            stage_for_job,
            trace_id=trace_id,
        )

        try:
            if success:
                await _mark_document_active(
                    document=document,
                    chunk_count=chunk_result.get("chunk_count"),
                    content_hash=content_hash,
                    byte_size=byte_size,
                    timestamps=timestamps,
                )
                await job_manager.complete_job(job.id)
                await refresh_active_chunks_view(session)
                if document.access_scope == "base" and document.country_code:
                    await refresh_base_documents_cache_for_country(session, document.country_code)
            else:
                await _mark_document_failed(
                    document=document,
                    failure_stage=stage_for_job,
                    error_info=error_info,
                    timestamps=timestamps,
                )
                await job_manager.fail_job(
                    job.id,
                    error_code=_error_code(error_info),
                    error_message=_error_message(error_info),
                    error_details=error_info
                    if isinstance(error_info, dict)
                    else {"raw": str(error_info)},
                )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("ingestion_finalizer error for document %s", document_id)
            await job_manager.fail_job(
                job.id,
                error_code="FINALIZER_ERROR",
                error_message=str(exc),
                error_details={"document_id": document_id},
            )
            raise

    logger.info(
        "Ingestion finalizer updated document %s (status=%s)",
        document_id,
        document.status,
        extra={"document_id": document_id, "ingestion_id": ingestion_id, "status": document.status},
    )

    return {
        "statusCode": 200,
        "document_id": document_id,
        "ingestion_id": ingestion_id,
        "status": document.status,
        "stage": document.ingestion_stage,
    }


async def _mark_document_active(
    *,
    document: Document,
    chunk_count: int | None,
    content_hash: str | None,
    byte_size: int | None,
    timestamps: dict,
) -> None:
    document.status = "active"
    document.ingestion_stage = "activate"
    started_at = _parse_timestamp(timestamps.get("started_at"))
    completed_at = _parse_timestamp(timestamps.get("completed_at")) or datetime.now(UTC)
    document.ingestion_started_at = document.ingestion_started_at or started_at or completed_at
    document.ingestion_completed_at = completed_at
    if content_hash:
        document.content_hash = content_hash
    if byte_size is not None:
        try:
            document.byte_size = int(byte_size)
        except (TypeError, ValueError):
            document.byte_size = None
    if chunk_count:
        try:
            chunk_value = int(chunk_count)
        except (TypeError, ValueError):
            chunk_value = None
        if chunk_value:
            metadata = dict(document.metadata_ or {})
            ingestion_meta = metadata.setdefault("ingestion", {})
            ingestion_meta["chunk_count"] = chunk_value
            document.metadata_ = metadata


async def _mark_document_failed(
    *,
    document: Document,
    failure_stage: str,
    error_info: dict,
    timestamps: dict,
) -> None:
    document.status = "failed"
    document.ingestion_stage = failure_stage
    completed_at = _parse_timestamp(timestamps.get("completed_at")) or datetime.now(UTC)
    document.ingestion_completed_at = completed_at
    metadata = dict(document.metadata_ or {})
    failure_meta = metadata.setdefault("ingestion_failure", {})
    failure_meta["stage"] = failure_stage
    failure_meta["error"] = error_info
    failure_meta["occurred_at"] = completed_at.isoformat()
    document.metadata_ = metadata


def _normalize_stage(stage_name: str | None) -> str:
    if not stage_name:
        return "activate"
    normalized = stage_name.replace(" ", "").lower()
    if normalized in VALID_STAGES:
        return normalized
    return _STATE_STAGE_MAP.get(normalized, "activate")


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    text = str(value)
    if text.endswith("Z"):
        text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _error_code(error_info: dict) -> str:
    if not error_info:
        return "INGESTION_FAILED"
    return error_info.get("Error") or error_info.get("code") or "INGESTION_FAILED"


def _error_message(error_info: dict) -> str:
    if not error_info:
        return "Document ingestion failed"
    return error_info.get("Cause") or error_info.get("message") or "Document ingestion failed"
