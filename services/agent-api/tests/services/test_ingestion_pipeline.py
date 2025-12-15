from __future__ import annotations

import pytest
from shared_data_layer.db.models.retrieval import Chunk
from sqlalchemy import select

from services.document_upload_service import (
    DocumentUploadData,
    DocumentUploadService,
)
from services.ingestion_pipeline import MarkdownChunker, VoyageIngestionPipeline

pytestmark = pytest.mark.asyncio(loop_scope="session")


class _StubVoyageClient:
    async def embed(self, texts):
        return [[0.1] * 1024 for _ in texts]


async def test_real_ingestion_persists_chunks(db_session):
    service = DocumentUploadService(session=db_session)
    payload = DocumentUploadData(
        document_name="Test Doc",
        content="## Page 1\n" + ("lorem ipsum " * 200),
        content_type="text/markdown",
        chunk_type="text",
        access_scope="user_private",
        country_code="USA",
        language="en",
        tags=[],
        metadata={},
        owner_user_id="123e4567-e89b-12d3-a456-426614174000",
    )
    result = await service.upload_markdown(payload, text_only=False)
    assert result.document is not None
    pipeline = VoyageIngestionPipeline(
        voyage_client=_StubVoyageClient(),
        chunker=MarkdownChunker(),
    )
    summary = await pipeline.ingest_document(
        document=result.document,
        upload_payload=payload,
        session=db_session,
    )
    await db_session.flush()
    chunks = (
        (await db_session.execute(select(Chunk).where(Chunk.document_id == result.document.id)))
        .scalars()
        .all()
    )
    assert chunks, "expected chunks to be persisted"
    assert summary.status == "succeeded"
    assert chunks[0].embedding is not None
