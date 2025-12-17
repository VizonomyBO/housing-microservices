from uuid import uuid4

from polyfactory import Ignore, Use

from shared_data_layer.config import EMBEDDING_DIMENSION
from shared_data_layer.db.maintenance import refresh_graph_materializations
from shared_data_layer.db.models.knowledge_graph import (
    GraphCommunity,
    GraphEdge,
    GraphEntity,
    GraphEvidence,
)
from shared_data_layer.testing.factories.base import AsyncSQLAlchemyFactory
from shared_data_layer.testing.factories.documents import DocumentFactory
from shared_data_layer.testing.factories.retrieval import ChunkFactory


class GraphEntityFactory(AsyncSQLAlchemyFactory[GraphEntity]):
    __model__ = GraphEntity
    embedding = Use(lambda: [0.0] * EMBEDDING_DIMENSION)
    edges_out = Ignore()
    edges_in = Ignore()
    name = Use(lambda: f"Entity-{uuid4().hex[:8]}")
    entity_type = Use(lambda: "organization")
    entity_key = Use(lambda: f"entity-{uuid4().hex}")
    country_code = Use(lambda: "USA")
    labels = Use(lambda: ["label1"])
    properties = Use(lambda: {"prop": "val"})
    score = Use(lambda: 0.9)
    algo_version = Use(lambda: "v1")
    document_id = Use(lambda: None)
    chunk_id = Use(lambda: None)

    @classmethod
    def build(cls, **kwargs):  # type: ignore[override]
        return super().build(**kwargs)


def _chunk_with_document():
    document = DocumentFactory.build(chunks=[], ingestion_jobs=[])
    return ChunkFactory.build(document=document)


class GraphEvidenceFactory(AsyncSQLAlchemyFactory[GraphEvidence]):
    __model__ = GraphEvidence
    chunk = Use(_chunk_with_document)
    confidence = Use(lambda: 0.9)
    offsets = Use(lambda: (0, 10))

    @classmethod
    def _ensure_chunk(cls, kwargs):
        chunk = kwargs.get("chunk")
        if chunk is None:
            chunk = _chunk_with_document()
            kwargs["chunk"] = chunk
        return chunk

    @classmethod
    def build(cls, **kwargs):
        chunk = cls._ensure_chunk(kwargs)
        kwargs.setdefault("chunk_country_code", getattr(chunk, "country_code", "USA"))
        return super().build(**kwargs)

    @classmethod
    async def create_async(cls, session, **kwargs):  # type: ignore[override]
        chunk = kwargs.get("chunk")
        if chunk is None:
            chunk = await ChunkFactory.create_async(session=session)
            kwargs["chunk"] = chunk
        kwargs.setdefault("chunk_country_code", chunk.country_code)
        evidence = await super().create_async(session=session, **kwargs)
        await refresh_graph_materializations(session)
        return evidence


class GraphEdgeFactory(AsyncSQLAlchemyFactory[GraphEdge]):
    __model__ = GraphEdge
    source = Use(GraphEntityFactory.build)
    target = Use(GraphEntityFactory.build)
    evidence = Use(GraphEvidenceFactory.batch, size=1)
    edge_type = Use(lambda: "reported_in")
    directional = Use(lambda: True)
    metadata_ = Use(lambda: {"meta": "data"})
    algo_version = Use(lambda: "v1")
    weight = Use(lambda: 0.6)

    @classmethod
    def build(cls, **kwargs):  # type: ignore[override]
        source = kwargs.get("source")
        if source is None:
            source = GraphEntityFactory.build()
            kwargs["source"] = source

        target = kwargs.get("target")
        if target is None:
            target = GraphEntityFactory.build()
            kwargs["target"] = target

        kwargs.setdefault("source_entity_country_code", source.country_code)
        kwargs.setdefault("target_entity_country_code", target.country_code)
        return super().build(**kwargs)

    @classmethod
    async def create_async(cls, session, **kwargs):  # type: ignore[override]
        edge = await super().create_async(session=session, **kwargs)
        await refresh_graph_materializations(session)
        return edge


class GraphCommunityFactory(AsyncSQLAlchemyFactory[GraphCommunity]):
    __model__ = GraphCommunity
    community_key = Use(lambda: "key")
    summary = Use(lambda: "summary")
    entity_ids = Use(lambda: [])
    algo_version = Use(lambda: "v1")
