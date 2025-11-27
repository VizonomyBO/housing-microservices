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
    position = Use(lambda: 0)
    chunk_type = Use(lambda: "text")
    text_content = Use(lambda: "chunk text")
    page_number = Use(lambda: 1)
    schema_summary = Use(lambda: "summary")
    country_code = Use(lambda: "USA")
    section_path = Use(lambda: ["Section 1"])
    bbox = Use(lambda: {"x1": 0, "y1": 0, "x2": 100, "y2": 100})
    token_count = Use(lambda: 200)
    text_tsv = Ignore()  # Generated column
    table_payload = Use(lambda: {"data": "test"})
    document = Use(
        lambda: _document_stub(),
    )


def _document_stub():
    from shared_data_layer.testing.factories.documents import DocumentFactory

    return DocumentFactory.build(chunks=[], ingestion_jobs=[])


class ChunkMetricsFactory(AsyncSQLAlchemyFactory[ChunkMetrics]):
    __model__ = ChunkMetrics
    chunk = Use(ChunkFactory.build)
    quality_score = Use(lambda: 0.9)

    @classmethod
    def _prepare_chunk(cls, kwargs):
        chunk = kwargs.get("chunk")
        if chunk is None:
            chunk = ChunkFactory.build()
            kwargs["chunk"] = chunk
        return chunk

    @classmethod
    def build(cls, **kwargs):
        chunk = cls._prepare_chunk(kwargs)
        kwargs.setdefault("chunk_country_code", chunk.country_code)
        return super().build(**kwargs)

    @classmethod
    async def create_async(cls, session, **kwargs):  # type: ignore[override]
        chunk = kwargs.get("chunk")
        if chunk is None:
            chunk = await ChunkFactory.create_async(session=session)
            kwargs["chunk"] = chunk
        kwargs.setdefault("chunk_country_code", chunk.country_code)
        return await super().create_async(session=session, **kwargs)


class RetrievalRunItemFactory(AsyncSQLAlchemyFactory[RetrievalRunItem]):
    __model__ = RetrievalRunItem
    chunk = Use(ChunkFactory.build)

    @classmethod
    def _prepare_chunk(cls, kwargs):
        chunk = kwargs.get("chunk")
        if chunk is None:
            chunk = ChunkFactory.build()
            kwargs["chunk"] = chunk
        return chunk

    @classmethod
    def build(cls, **kwargs):
        chunk = cls._prepare_chunk(kwargs)
        kwargs.setdefault("chunk_country_code", chunk.country_code)
        return super().build(**kwargs)

    @classmethod
    async def create_async(cls, session, **kwargs):  # type: ignore[override]
        chunk = kwargs.get("chunk")
        if chunk is None:
            chunk = await ChunkFactory.create_async(session=session)
            kwargs["chunk"] = chunk
        kwargs.setdefault("chunk_country_code", chunk.country_code)
        return await super().create_async(session=session, **kwargs)


class RetrievalRunFactory(AsyncSQLAlchemyFactory[RetrievalRun]):
    __model__ = RetrievalRun
    items = Use(RetrievalRunItemFactory.batch, size=2)
