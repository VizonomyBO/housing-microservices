import uuid
from datetime import UTC, datetime

import pytest

from shared_data_layer.repositories.documents import DocumentUploadRepository
from shared_data_layer.testing.factories.documents import DocumentFactory


@pytest.mark.asyncio
async def test_document_upload_repository_create_and_list(db_session):
    repo = DocumentUploadRepository(db_session)
    uploaded_by = uuid.uuid4()

    created = await repo.create_upload(
        country_code="NPL",
        filename="sample.pdf",
        storage_uri="s3://raw/documents/1/source.pdf",
        byte_size=512,
        content_hash="abc123",
        source="World Bank",
        uploaded_by=uploaded_by,
        metadata_={"source_type": "pdf"},
    )
    await db_session.commit()

    assert created.country_code == "NPL"
    assert created.verified is False
    assert created.reprocess_status == "not_started"

    listed = await repo.list_uploads(country_code="NPL", limit=10, offset=0)
    assert len(listed) == 1
    assert listed[0].id == created.id


@pytest.mark.asyncio
async def test_document_upload_repository_status_and_pending(db_session):
    repo = DocumentUploadRepository(db_session)
    uploaded_by = uuid.uuid4()
    approver = uuid.uuid4()
    started_at = datetime.now(UTC)

    first = await repo.create_upload(
        country_code="KEN",
        filename="one.pdf",
        storage_uri="s3://raw/documents/1/source.pdf",
        byte_size=512,
        content_hash="hash-1",
        source="Country",
        uploaded_by=uploaded_by,
        metadata_={"source_type": "pdf"},
    )
    second = await repo.create_upload(
        country_code="KEN",
        filename="two.pdf",
        storage_uri="s3://raw/documents/2/source.pdf",
        byte_size=256,
        content_hash="hash-2",
        source="Country",
        uploaded_by=uploaded_by,
        metadata_={"source_type": "pdf"},
    )

    await repo.set_verified(
        upload_id=first.id,
        verified=True,
        verified_by=approver,
        verified_at=started_at,
    )
    await repo.update_reprocess_status(
        upload_id=first.id,
        status="queued",
        started_at=started_at,
    )
    await repo.update_reprocess_status(
        upload_id=second.id,
        status="done",
        completed_at=started_at,
    )
    await db_session.commit()

    pending = await repo.list_pending_reprocessing(country_code="KEN")
    assert len(pending) == 1
    assert pending[0].id == first.id


@pytest.mark.asyncio
async def test_document_upload_repository_claim_next_queued_upload(db_session):
    repo = DocumentUploadRepository(db_session)
    uploaded_by = uuid.uuid4()
    approver = uuid.uuid4()
    queued_at = datetime.now(UTC)

    older = await repo.create_upload(
        country_code="GHA",
        filename="older.pdf",
        storage_uri="s3://raw/documents/older/source.pdf",
        byte_size=500,
        content_hash="old-hash",
        source="Country",
        uploaded_by=uploaded_by,
        metadata_={"source_type": "pdf"},
    )
    newer = await repo.create_upload(
        country_code="GHA",
        filename="newer.pdf",
        storage_uri="s3://raw/documents/newer/source.pdf",
        byte_size=500,
        content_hash="new-hash",
        source="Country",
        uploaded_by=uploaded_by,
        metadata_={"source_type": "pdf"},
    )
    await repo.set_verified(
        upload_id=older.id,
        verified=True,
        verified_by=approver,
        verified_at=queued_at,
    )
    await repo.set_verified(
        upload_id=newer.id,
        verified=True,
        verified_by=approver,
        verified_at=queued_at,
    )
    await repo.queue_upload(upload_id=older.id)
    await repo.queue_upload(upload_id=newer.id)
    await db_session.commit()

    claimed = await repo.claim_next_queued_upload(claimed_at=datetime.now(UTC))
    assert claimed is not None
    assert claimed.id == older.id
    assert claimed.reprocess_status == "ingesting"


@pytest.mark.asyncio
async def test_document_upload_repository_document_link(db_session):
    upload_repo = DocumentUploadRepository(db_session)
    uploaded_by = uuid.uuid4()

    document = await DocumentFactory.create_async(
        session=db_session,
        country_code="GHA",
        chunk_count=0,
    )

    upload = await upload_repo.create_upload(
        country_code="GHA",
        filename="country-report.pdf",
        storage_uri="s3://raw/documents/3/source.pdf",
        byte_size=1024,
        content_hash="hash-link",
        source="Other",
        uploaded_by=uploaded_by,
        metadata_={"source_type": "pdf"},
    )
    linked = await upload_repo.set_document_link(
        upload_id=upload.id,
        document_id=document.id,
    )
    await db_session.commit()

    assert linked is not None
    assert linked.document_id == document.id


@pytest.mark.asyncio
async def test_document_upload_repository_ingestion_progress(db_session):
    repo = DocumentUploadRepository(db_session)
    uploaded_by = uuid.uuid4()

    upload = await repo.create_upload(
        country_code="LUA",
        filename="progress.pdf",
        storage_uri="s3://raw/documents/4/source.pdf",
        byte_size=2048,
        content_hash="hash-progress",
        source="World Bank",
        uploaded_by=uploaded_by,
        metadata_={"source_type": "pdf"},
    )
    await repo.queue_upload(upload_id=upload.id)
    await repo.claim_next_queued_upload(claimed_at=datetime.now(UTC))
    await repo.set_ingestion_progress(
        upload_id=upload.id,
        total_chunks=145,
        total_batches=15,
        processed_chunks=40,
        processed_batches=4,
        batch_size=10,
    )
    await db_session.commit()

    refreshed = await repo.get_upload(upload.id)
    assert refreshed is not None
    assert isinstance(refreshed.metadata_, dict)
    assert refreshed.metadata_["ingestion_progress"]["processed_batches"] == 4
    assert refreshed.metadata_["ingestion_progress"]["total_chunks"] == 145

    await repo.update_reprocess_status(upload_id=upload.id, status="reprocessing_cache")
    await db_session.commit()

    final = await repo.get_upload(upload.id)
    assert final is not None
    assert isinstance(final.metadata_, dict)
    assert final.metadata_.get("ingestion_progress") is None
