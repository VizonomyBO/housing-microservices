from polyfactory import Ignore, Use

from shared_data_layer.db.models.knowledge_graph import (
    GraphCommunity,
    GraphEdge,
    GraphEntity,
    GraphEvidence,
)
from shared_data_layer.testing.factories.base import AsyncSQLAlchemyFactory
from shared_data_layer.testing.factories.retrieval import ChunkFactory


class GraphEntityFactory(AsyncSQLAlchemyFactory[GraphEntity]):
    __model__ = GraphEntity
    embedding = Use(lambda: [0.0] * 512)
    edges_out = Ignore()
    edges_in = Ignore()

    # New fields
    document_id = Use(lambda: None)
    chunk_id = Use(lambda: None)
    algo_version = Use(lambda: "v1")
    labels = Use(lambda: ["label1"])
    properties = Use(lambda: {"prop": "val"})
    score = Use(lambda: 0.9)


class GraphEvidenceFactory(AsyncSQLAlchemyFactory[GraphEvidence]):
    __model__ = GraphEvidence
    chunk = Use(ChunkFactory.build)


class GraphEdgeFactory(AsyncSQLAlchemyFactory[GraphEdge]):
    __model__ = GraphEdge
    source = Use(GraphEntityFactory.build)
    target = Use(GraphEntityFactory.build)
    evidence = Use(GraphEvidenceFactory.batch, size=1)

    # New fields
    directional = Use(lambda: True)
    metadata_ = Use(lambda: {"meta": "data"})
    algo_version = Use(lambda: "v1")


class GraphCommunityFactory(AsyncSQLAlchemyFactory[GraphCommunity]):
    __model__ = GraphCommunity
    community_key = Use(lambda: "key")
    summary = Use(lambda: "summary")
