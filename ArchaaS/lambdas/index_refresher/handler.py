"""Refresh materialized indexes after embeddings land."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any
from uuid import UUID

from common.db import get_async_session
from common.ingestion import IngestionJobManager, update_document_stage
from shared_data_layer.db.maintenance import (
    refresh_active_chunks_view,
    refresh_base_documents_cache_for_country,
)
from shared_data_layer.db.models.documents import Document

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REFRESH_CONCURRENTLY = os.environ.get("REFRESH_ACTIVE_CHUNKS_CONCURRENTLY", "0") == "1"


def handler(event: dict, context: Any) -> dict:
    return asyncio.run(async_handler(event))


async def async_handler(event: dict) -> dict:
    document_id = event.get("document_id")
    if not document_id:
        raise ValueError("document_id is required")

    document_uuid = UUID(str(document_id))
    ingestion_id = event.get("ingestion_id")
    trace_id = event.get("trace_id")

    async with get_async_session() as session:
        document = await session.get(Document, document_uuid)
        if document is None:
            raise LookupError(f"Document {document_id} not found")

        job_manager = IngestionJobManager(session)
        job = await job_manager.start_job(document_uuid, "index", trace_id=trace_id)
        await update_document_stage(session, document_uuid, stage="index")

        try:
            await refresh_active_chunks_view(session, concurrently=REFRESH_CONCURRENTLY)
            if document.access_scope == "base" and document.country_code:
                await refresh_base_documents_cache_for_country(
                    session, document.country_code
                )
            await job_manager.complete_job(job.id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Index refresh failed for %s", document_id)
            await job_manager.fail_job(
                job.id,
                error_code="INDEX_REFRESH_ERROR",
                error_message=str(exc),
            )
            raise

    return {
        "statusCode": 200,
        "document_id": document_id,
        "ingestion_id": ingestion_id,
        "stage": "index",
        "message": "Materialized views refreshed",
    }
