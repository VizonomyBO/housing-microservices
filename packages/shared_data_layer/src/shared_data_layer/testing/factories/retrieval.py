from polyfactory import Use
from shared_data_layer.testing.factories.base import AsyncSQLAlchemyFactory

from shared_data_layer.db.models.retrieval import Chunk, ChunkMetrics, RetrievalRun, RetrievalRunItem

class ChunkFactory(AsyncSQLAlchemyFactory[Chunk]):
    __model__ = Chunk
    @classmethod
    def embedding(cls) -> list[float]:
        return [0.1] * 1024

class ChunkMetricsFactory(AsyncSQLAlchemyFactory[ChunkMetrics]):
    __model__ = ChunkMetrics

class RetrievalRunItemFactory(AsyncSQLAlchemyFactory[RetrievalRunItem]):
    __model__ = RetrievalRunItem
    chunk = Use(ChunkFactory.build)

class RetrievalRunFactory(AsyncSQLAlchemyFactory[RetrievalRun]):
    __model__ = RetrievalRun
    items = Use(RetrievalRunItemFactory.batch, size=2)
