import pytest
from sqlalchemy.exc import IntegrityError

from shared_data_layer.repositories.documents import UploadedFileRepository
from shared_data_layer.testing.factories.documents import (
    DocumentFactory,
    UploadedFileFactory,
)


@pytest.mark.asyncio
async def test_uploaded_file_unique_owner_hash_constraint(db_session):
    document = await DocumentFactory.create_async(session=db_session, chunk_count=0)

    await UploadedFileFactory.create_async(
        session=db_session,
        document=document,
        content_hash="dup-hash",
        owner_user_id=document.owner_user_id,
    )

    with pytest.raises(IntegrityError):
        await UploadedFileFactory.create_async(
            session=db_session,
            document=document,
            content_hash="dup-hash",
            owner_user_id=document.owner_user_id,
        )


@pytest.mark.asyncio
async def test_uploaded_file_repository_handles_base_documents(db_session):
    base_document = await DocumentFactory.create_async(
        session=db_session,
        access_scope="base",
        owner_user_id=None,
        chunk_count=0,
    )
    repo = UploadedFileRepository(db_session)

    first = await repo.register_upload(
        document_id=base_document.id,
        owner_user_id=None,
        storage_uri="s3://bucket/base.pdf",
        byte_size=512,
        content_hash="base-hash",
    )
    second = await repo.register_upload(
        document_id=base_document.id,
        owner_user_id=None,
        storage_uri="s3://bucket/base.pdf",
        byte_size=512,
        content_hash="base-hash",
    )

    assert first.id != second.id


@pytest.mark.asyncio
async def test_uploaded_file_factory_sets_defaults(db_session):
    upload = await UploadedFileFactory.create_async(session=db_session)
    assert upload.document_id is not None
    assert upload.storage_uri.startswith("s3://uploads/")
    assert upload.byte_size > 0
