from __future__ import annotations

import pytest
from shared_data_layer.db.models.documents import Document, IngestionJob
from shared_data_layer.testing.factories.documents import DocumentFactory
from sqlalchemy import select

from services.ingestion_job_service import (
    ReducedScopeCapabilityError,
    ReducedScopeIngestionJobService,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_auto_complete_marks_document_active(db_session):
    document = await DocumentFactory.create_async(session=db_session, chunk_count=0)
    service = ReducedScopeIngestionJobService(db_session, allowed_chunk_types=("text",))

    summary = await service.auto_complete(document_id=document.id, chunk_type="text")

    await db_session.refresh(document)
    job_row = (
        await db_session.execute(select(IngestionJob).where(IngestionJob.id == summary.id))
    ).scalar_one()

    assert summary.document_id == document.id
    assert summary.status == "succeeded"
    assert document.status == "active"
    assert document.ingestion_stage == "activate"
    assert document.ingestion_completed_at is not None
    assert job_row.status == "succeeded"
    assert job_row.stage == "activate"
    assert document.metadata_["reduced_scope"]["ingestion"]["auto_completed"] is True


async def test_auto_complete_rejects_non_text_chunks(db_session):
    document = await DocumentFactory.create_async(session=db_session, chunk_count=0)
    initial_completed = document.ingestion_completed_at
    service = ReducedScopeIngestionJobService(db_session, allowed_chunk_types=("text",))

    with pytest.raises(ReducedScopeCapabilityError):
        await service.auto_complete(document_id=document.id, chunk_type="image")

    refreshed = await db_session.get(Document, document.id)
    assert refreshed.ingestion_completed_at == initial_completed
