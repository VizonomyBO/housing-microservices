from polyfactory import Use
from shared_data_layer.testing.factories.base import AsyncSQLAlchemyFactory
from shared_data_layer.testing.factories.retrieval import ChunkFactory

from shared_data_layer.db.models.documents import Document, IngestionJob, Artifact

class DocumentFactory(AsyncSQLAlchemyFactory[Document]):
    __model__ = Document
    chunks = Use(ChunkFactory.batch, size=2)

class IngestionJobFactory(AsyncSQLAlchemyFactory[IngestionJob]):
    __model__ = IngestionJob

class ArtifactFactory(AsyncSQLAlchemyFactory[Artifact]):
    __model__ = Artifact
