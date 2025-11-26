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


class WorkflowEdgeFactory(BaseWorkflowFactory[WorkflowEdge]):
    __model__ = WorkflowEdge


class WorkflowVersionFactory(BaseWorkflowFactory[WorkflowVersion]):
    __model__ = WorkflowVersion
    nodes = Use(WorkflowNodeFactory.batch, size=2)
    edges = Use(WorkflowEdgeFactory.batch, size=1)


class WorkflowGraphFactory(BaseWorkflowFactory[WorkflowGraph]):
    __model__ = WorkflowGraph
    versions = Use(WorkflowVersionFactory.batch, size=1)
