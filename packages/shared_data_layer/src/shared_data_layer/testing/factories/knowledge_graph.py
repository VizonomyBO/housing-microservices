from polyfactory import Use
from shared_data_layer.testing.factories.base import AsyncSQLAlchemyFactory

from shared_data_layer.db.models.knowledge_graph import GraphEntity, GraphEdge, GraphEvidence, GraphCommunity

from polyfactory import Use, Ignore

class GraphEntityFactory(AsyncSQLAlchemyFactory[GraphEntity]):
    __model__ = GraphEntity
    edges_out = Ignore()
    edges_in = Ignore()
    
    @classmethod
    def embedding(cls) -> list[float]:
        return [0.1] * 512

from shared_data_layer.testing.factories.retrieval import ChunkFactory

class GraphEvidenceFactory(AsyncSQLAlchemyFactory[GraphEvidence]):
    __model__ = GraphEvidence
    chunk = Use(ChunkFactory.build)

class GraphEdgeFactory(AsyncSQLAlchemyFactory[GraphEdge]):
    __model__ = GraphEdge
    evidence = Use(GraphEvidenceFactory.batch, size=1)

class GraphCommunityFactory(AsyncSQLAlchemyFactory[GraphCommunity]):
    __model__ = GraphCommunity
