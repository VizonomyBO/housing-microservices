from polyfactory import Use

from shared_data_layer.db.models.documents import Artifact, Document, IngestionJob
from shared_data_layer.testing.factories.base import AsyncSQLAlchemyFactory
from shared_data_layer.testing.factories.retrieval import ChunkFactory


class DocumentFactory(AsyncSQLAlchemyFactory[Document]):
    __model__ = Document
    chunks = Use(ChunkFactory.batch, size=2)
    content_hash = Use(lambda: "hash")
    canonical_name = Use(lambda: "doc_name")
    access_scope = Use(lambda: "user_private")
    status = Use(lambda: "active")


class IngestionJobFactory(AsyncSQLAlchemyFactory[IngestionJob]):
    __model__ = IngestionJob
    stage = Use(lambda: "completed")
    status = Use(lambda: "succeeded")


class ArtifactFactory(AsyncSQLAlchemyFactory[Artifact]):
    __model__ = Artifact
    artifact_type = Use(lambda: "markdown")
    s3_uri = Use(lambda: "s3://bucket/key")
