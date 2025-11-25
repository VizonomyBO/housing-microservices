from shared_data_layer.testing.factories.base import AsyncSQLAlchemyFactory

from shared_data_layer.db.models.knowledge_graph import GraphEntity, GraphEdge, GraphEvidence, GraphCommunity

class GraphEntityFactory(AsyncSQLAlchemyFactory[GraphEntity]):
    __model__ = GraphEntity

class GraphEdgeFactory(AsyncSQLAlchemyFactory[GraphEdge]):
    __model__ = GraphEdge

class GraphEvidenceFactory(AsyncSQLAlchemyFactory[GraphEvidence]):
    __model__ = GraphEvidence

class GraphCommunityFactory(AsyncSQLAlchemyFactory[GraphCommunity]):
    __model__ = GraphCommunity
