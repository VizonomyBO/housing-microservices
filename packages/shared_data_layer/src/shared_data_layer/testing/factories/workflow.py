from shared_data_layer.testing.factories.base import AsyncSQLAlchemyFactory

from shared_data_layer.db.models.workflow import WorkflowGraph, WorkflowVersion, WorkflowNode, WorkflowEdge

class WorkflowGraphFactory(AsyncSQLAlchemyFactory[WorkflowGraph]):
    __model__ = WorkflowGraph

class WorkflowVersionFactory(AsyncSQLAlchemyFactory[WorkflowVersion]):
    __model__ = WorkflowVersion

class WorkflowNodeFactory(AsyncSQLAlchemyFactory[WorkflowNode]):
    __model__ = WorkflowNode

class WorkflowEdgeFactory(AsyncSQLAlchemyFactory[WorkflowEdge]):
    __model__ = WorkflowEdge
