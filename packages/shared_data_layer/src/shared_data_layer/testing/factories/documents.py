from typing import Optional
from uuid import uuid4

from polyfactory import Use

from shared_data_layer.db.maintenance import refresh_base_documents_cache
from shared_data_layer.db.models.documents import (
    Artifact,
    Document,
    IngestionJob,
    UploadedFile,
)
from shared_data_layer.testing.factories.base import AsyncSQLAlchemyFactory
from shared_data_layer.testing.factories.retrieval import ChunkFactory


class DocumentFactory(AsyncSQLAlchemyFactory[Document]):
    __model__ = Document
    __set_relationships__ = False
    owner_user_id = Use(uuid4)
    content_hash = Use(lambda: uuid4().hex)
    canonical_name = Use(lambda: "doc_name")
    access_scope = Use(lambda: "user_private")
    status = Use(lambda: "active")
    ingestion_stage = Use(lambda: "activate")
    country_code = Use(lambda: "USA")
    deleted_at = Use(lambda: None)

    default_chunk_count = 2

    @classmethod
    async def create_async(  # type: ignore[override]
        cls,
        session,
        *,
        chunk_count: Optional[int] = None,
        **kwargs,
    ):
        chunk_defs = kwargs.pop("chunks", None)
        access_scope = kwargs.get("access_scope")
        if access_scope == "base" and "owner_user_id" not in kwargs:
            kwargs["owner_user_id"] = None
        document = await super().create_async(session=session, **kwargs)

        desired_chunks = cls.default_chunk_count if chunk_count is None else chunk_count
        if chunk_defs is not None:
            for idx, chunk_kwargs in enumerate(chunk_defs):
                merged_kwargs = {"document": document, "position": idx} | chunk_kwargs
                await ChunkFactory.create_async(
                    session=session,
                    **merged_kwargs,
                )
        else:
            for idx in range(desired_chunks):
                await ChunkFactory.create_async(
                    session=session,
                    document=document,
                    position=idx,
                    chunk_type="text",
                    text_content=f"chunk-{idx}",
                )

        await session.refresh(document, attribute_names=["chunks"])
        if document.access_scope == "base" and document.country_code:
            await refresh_base_documents_cache(session, document.country_code)
        return document


class IngestionJobFactory(AsyncSQLAlchemyFactory[IngestionJob]):
    __model__ = IngestionJob
    stage = Use(lambda: "convert")
    status = Use(lambda: "succeeded")


class ArtifactFactory(AsyncSQLAlchemyFactory[Artifact]):
    __model__ = Artifact
    artifact_type = Use(lambda: "markdown")
    s3_uri = Use(lambda: "s3://bucket/key")
    content_hash = Use(lambda: "hash")


class UploadedFileFactory(AsyncSQLAlchemyFactory[UploadedFile]):
    __model__ = UploadedFile
    __set_relationships__ = False
    storage_uri = Use(lambda: f"s3://uploads/{uuid4().hex}.bin")
    byte_size = Use(lambda: 4096)
    content_hash = Use(lambda: uuid4().hex)
    checksum = Use(lambda: uuid4().hex[:16])
    ingestion_metadata = Use(lambda: {"stage": "upload"})

    @classmethod
    async def create_async(  # type: ignore[override]
        cls,
        session,
        *,
        document=None,
        **kwargs,
    ):
        document_obj = document
        if document_obj is None and "document_id" not in kwargs:
            document_obj = await DocumentFactory.create_async(
                session=session, chunk_count=0
            )
        if document_obj is not None:
            kwargs.setdefault("document_id", document_obj.id)
            kwargs.setdefault("owner_user_id", document_obj.owner_user_id)
        return await super().create_async(session=session, **kwargs)
