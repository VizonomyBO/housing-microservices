from polyfactory import Use
from shared_data_layer.testing.factories.base import AsyncSQLAlchemyFactory

from shared_data_layer.db.models.workflow import WorkflowGraph, WorkflowVersion, WorkflowNode, WorkflowEdge

class WorkflowNodeFactory(AsyncSQLAlchemyFactory[WorkflowNode]):
    __model__ = WorkflowNode

class WorkflowEdgeFactory(AsyncSQLAlchemyFactory[WorkflowEdge]):
    __model__ = WorkflowEdge

class WorkflowVersionFactory(AsyncSQLAlchemyFactory[WorkflowVersion]):
    __model__ = WorkflowVersion
    nodes = Use(WorkflowNodeFactory.batch, size=2)
    edges = Use(WorkflowEdgeFactory.batch, size=1)

class WorkflowGraphFactory(AsyncSQLAlchemyFactory[WorkflowGraph]):
    __model__ = WorkflowGraph
    versions = Use(WorkflowVersionFactory.batch, size=1)
