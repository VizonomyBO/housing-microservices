from polyfactory import Use
from shared_data_layer.testing.factories.base import AsyncSQLAlchemyFactory

from shared_data_layer.db.models.retrieval import Chunk, ChunkMetrics, RetrievalRun, RetrievalRunItem

class ChunkFactory(AsyncSQLAlchemyFactory[Chunk]):
    __model__ = Chunk
    embedding = Use(lambda: [0.1] * 1536)

class ChunkMetricsFactory(AsyncSQLAlchemyFactory[ChunkMetrics]):
    __model__ = ChunkMetrics

class RetrievalRunFactory(AsyncSQLAlchemyFactory[RetrievalRun]):
    __model__ = RetrievalRun

class RetrievalRunItemFactory(AsyncSQLAlchemyFactory[RetrievalRunItem]):
    __model__ = RetrievalRunItem
