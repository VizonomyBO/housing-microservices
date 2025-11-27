from __future__ import annotations

from itertools import count
from typing import TypeVar

from polyfactory import Use

from shared_data_layer.db.base import Base
from shared_data_layer.db.ltree import Ltree
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


_NODE_KEY_COUNTER = count()
_NODE_PATH_COUNTER = count()


def _next_node_key() -> str:
    return f"node_{next(_NODE_KEY_COUNTER)}"


def _next_node_path() -> Ltree:
    return Ltree(f"root.node{next(_NODE_PATH_COUNTER)}")


class WorkflowNodeFactory(BaseWorkflowFactory[WorkflowNode]):
    __model__ = WorkflowNode
    __set_relationships__ = False

    node_key = Use(_next_node_key)
    path = Use(_next_node_path)
    type = Use(lambda: "task")
    level = Use(lambda: "coarse")
    description = Use(lambda: "desc")
    preconditions = Use(lambda: {"cond": "val"})
    tool_hints = Use(lambda: ["hint"])
    artifacts = Use(lambda: {"art": "val"})


class WorkflowEdgeFactory(BaseWorkflowFactory[WorkflowEdge]):
    __model__ = WorkflowEdge
    __set_relationships__ = False
    transition_type = Use(lambda: "success")
    confidence = Use(lambda: 0.9)
    metadata_ = Use(lambda: {"meta": "data"})


class WorkflowVersionFactory(BaseWorkflowFactory[WorkflowVersion]):
    __model__ = WorkflowVersion
    __set_relationships__ = False
    definition = Use(lambda: {"def": "val"})
    from_version = Use(lambda: "0.0.1")
    to_version = Use(lambda: "0.0.2")

    _default_node_specs = [
        {"node_key": "root", "path": Ltree("root"), "level": "coarse", "type": "task"},
        {
            "node_key": "child",
            "path": Ltree("root.child"),
            "level": "coarse",
            "type": "task",
        },
    ]

    @classmethod
    async def create_async(  # type: ignore[override]
        cls,
        session,
        *,
        graph: WorkflowGraph | None = None,
        node_specs: list[dict] | None = None,
        edge_specs: list[dict] | None = None,
        **kwargs,
    ):
        if graph is None:
            graph = await WorkflowGraphFactory.create_async(
                session=session, version_count=0
            )

        version = await super().create_async(session=session, graph=graph, **kwargs)

        specs = node_specs or cls._default_node_specs
        nodes: list[WorkflowNode] = []
        for spec in specs:
            spec_copy = spec.copy()
            nodes.append(
                await WorkflowNodeFactory.create_async(
                    session=session,
                    version=version,
                    **spec_copy,
                )
            )

        edge_specs = edge_specs
        if edge_specs is None and len(nodes) >= 2:
            edge_specs = [{"source": nodes[0], "target": nodes[1]}]
        edge_specs = edge_specs or []

        for spec in edge_specs:
            spec_copy = spec.copy()
            source = spec_copy.pop("source")
            target = spec_copy.pop("target")
            await WorkflowEdgeFactory.create_async(
                session=session,
                version=version,
                source=source,
                target=target,
                **spec_copy,
            )

        await session.refresh(version, attribute_names=["nodes", "edges"])
        return version


class WorkflowGraphFactory(BaseWorkflowFactory[WorkflowGraph]):
    __model__ = WorkflowGraph
    __set_relationships__ = False
    name = Use(lambda: "graph")
    domain = Use(lambda: "domain")
    status = Use(lambda: "published")
    version = Use(lambda: "1.0.0")
    metadata_ = Use(lambda: {"meta": "data"})
    default_version_count = 1

    @classmethod
    async def create_async(  # type: ignore[override]
        cls,
        session,
        *,
        version_count: int | None = None,
        **kwargs,
    ):
        graph = await super().create_async(session=session, **kwargs)

        count = cls.default_version_count if version_count is None else version_count
        for _ in range(max(count, 0)):
            await WorkflowVersionFactory.create_async(session=session, graph=graph)

        await session.refresh(graph, attribute_names=["versions"])
        return graph
