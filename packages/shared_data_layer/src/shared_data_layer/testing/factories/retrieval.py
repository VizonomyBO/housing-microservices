from polyfactory import Ignore, Use

from shared_data_layer.db.models.retrieval import (
    Chunk,
    ChunkMetrics,
    RetrievalRun,
    RetrievalRunItem,
)
from shared_data_layer.testing.factories.base import AsyncSQLAlchemyFactory


class ChunkFactory(AsyncSQLAlchemyFactory[Chunk]):
    __model__ = Chunk

    @classmethod
    def _get_type_from_type_engine(cls, type_engine):
        try:
            return super()._get_type_from_type_engine(type_engine)
        except Exception:
            return str

    embedding = Use(lambda: [0.0] * 1024)
    content_hash = Use(lambda: "hash")
    text = Use(lambda: "chunk text")
    chunk_index = Use(lambda: 0)

    # New fields
    country_code = Use(lambda: "US")
    section_path = Use(lambda: ["Section 1"])
    bbox = Use(lambda: {"x1": 0, "y1": 0, "x2": 100, "y2": 100})
    text_tsv = Ignore()  # Generated column
    table_payload = Use(lambda: {"data": "test"})


class ChunkMetricsFactory(AsyncSQLAlchemyFactory[ChunkMetrics]):
    __model__ = ChunkMetrics


class RetrievalRunItemFactory(AsyncSQLAlchemyFactory[RetrievalRunItem]):
    __model__ = RetrievalRunItem
    chunk = Use(ChunkFactory.build)


class RetrievalRunFactory(AsyncSQLAlchemyFactory[RetrievalRun]):
    __model__ = RetrievalRun
    items = Use(RetrievalRunItemFactory.batch, size=2)
