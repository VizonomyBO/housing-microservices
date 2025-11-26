from typing import TypeVar

from polyfactory import Use
from sqlalchemy_utils import Ltree

from shared_data_layer.db.base import Base
from shared_data_layer.db.models.workflow import (
    WorkflowEdge,
    WorkflowGraph,
    WorkflowNode,
    WorkflowVersion,
)
from shared_data_layer.testing.factories.base import AsyncSQLAlchemyFactory

T = TypeVar("T", bound=Base)


class BaseWorkflowFactory(AsyncSQLAlchemyFactory[T]):
    __is_base_factory__ = True

    @classmethod
    def _get_type_from_type_engine(cls, type_engine):
        try:
            return super()._get_type_from_type_engine(type_engine)
        except Exception:
            return str


class WorkflowNodeFactory(BaseWorkflowFactory[WorkflowNode]):
    __model__ = WorkflowNode

    path = Ltree("top.child")
    type = Use(lambda: "task")
    level = Use(lambda: "coarse")
    description = Use(lambda: "desc")
    preconditions = Use(lambda: {"cond": "val"})
    tool_hints = Use(lambda: ["hint"])
    artifacts = Use(lambda: {"art": "val"})


class WorkflowEdgeFactory(BaseWorkflowFactory[WorkflowEdge]):
    __model__ = WorkflowEdge
    transition_type = Use(lambda: "success")
    confidence = Use(lambda: 0.9)
    metadata_ = Use(lambda: {"meta": "data"})


class WorkflowVersionFactory(BaseWorkflowFactory[WorkflowVersion]):
    __model__ = WorkflowVersion
    nodes = Use(WorkflowNodeFactory.batch, size=2)
    edges = Use(WorkflowEdgeFactory.batch, size=1)
    version_number = Use(lambda: 1)
    definition = Use(lambda: {"def": "val"})


class WorkflowGraphFactory(BaseWorkflowFactory[WorkflowGraph]):
    __model__ = WorkflowGraph
    versions = Use(WorkflowVersionFactory.batch, size=1)
    name = Use(lambda: "graph")
    domain = Use(lambda: "domain")
    status = Use(lambda: "published")
    metadata_ = Use(lambda: {"meta": "data"})
