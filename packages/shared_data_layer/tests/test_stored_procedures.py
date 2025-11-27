from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared_data_layer.db.ltree import Ltree
from shared_data_layer.db.models.workflow import WorkflowNode
from shared_data_layer.testing.factories.workflow import (
    WorkflowGraphFactory,
    WorkflowNodeFactory,
    WorkflowVersionFactory,
)


@pytest.mark.asyncio
async def test_workflow_nodes_move_subtree(db_session: AsyncSession):
    # Setup graph and version
    graph = await WorkflowGraphFactory.create_async(
        session=db_session, max_depth=5, version_count=0
    )
    version = await WorkflowVersionFactory.create_async(session=db_session, graph=graph)

    # Create nodes hierarchy:
    # A
    # ├── B
    # │   └── C
    # └── D

    node_a = await WorkflowNodeFactory.create_async(
        session=db_session, version=version, path=Ltree("A")
    )
    node_b = await WorkflowNodeFactory.create_async(
        session=db_session, version=version, path=Ltree("A.B")
    )
    node_c = await WorkflowNodeFactory.create_async(
        session=db_session, version=version, path=Ltree("A.B.C")
    )
    node_d = await WorkflowNodeFactory.create_async(
        session=db_session, version=version, path=Ltree("A.D")
    )

    # Move B (and C) under D
    # New structure:
    # A
    # └── D
    #     └── B
    #         └── C

    # Store IDs before expire_all
    v_id = version.id
    node_a_id = node_a.id
    node_b_id = node_b.id
    node_c_id = node_c.id
    node_d_id = node_d.id

    await db_session.execute(
        text("SELECT workflow_nodes_move_subtree(:graph_id, :src, :dst)"),
        {"graph_id": graph.id, "src": "A.B", "dst": "A.D"},
    )
    await db_session.commit()
    db_session.expire_all()

    # Verify paths
    stmt = select(WorkflowNode).where(WorkflowNode.version_id == v_id)
    result = await db_session.execute(stmt)
    nodes = result.scalars().all()

    node_map = {n.id: n for n in nodes}

    assert str(node_map[node_a_id].path) == "A"
    assert str(node_map[node_d_id].path) == "A.D"
    assert str(node_map[node_b_id].path) == "A.D.B"
    assert str(node_map[node_c_id].path) == "A.D.B.C"


@pytest.mark.asyncio
async def test_workflow_nodes_move_subtree_cycle_detection(db_session: AsyncSession):
    graph = await WorkflowGraphFactory.create_async(session=db_session, version_count=0)
    version = await WorkflowVersionFactory.create_async(session=db_session, graph=graph)

    # A -> B
    _node_a = await WorkflowNodeFactory.create_async(
        session=db_session, version=version, path=Ltree("A")
    )
    _node_b = await WorkflowNodeFactory.create_async(
        session=db_session, version=version, path=Ltree("A.B")
    )

    # Try to move A under B (Cycle!)
    with pytest.raises(Exception) as excinfo:
        await db_session.execute(
            text("SELECT workflow_nodes_move_subtree(:graph_id, :src, :dst)"),
            {"graph_id": graph.id, "src": "A", "dst": "A.B"},
        )
    assert "Cannot move subtree into its own descendant" in str(excinfo.value)


@pytest.mark.asyncio
async def test_workflow_nodes_move_subtree_max_depth(db_session: AsyncSession):
    graph = await WorkflowGraphFactory.create_async(
        session=db_session, max_depth=2, version_count=0
    )
    version = await WorkflowVersionFactory.create_async(session=db_session, graph=graph)

    # A -> B
    _node_a = await WorkflowNodeFactory.create_async(
        session=db_session, version=version, path=Ltree("A")
    )
    _node_b = await WorkflowNodeFactory.create_async(
        session=db_session, version=version, path=Ltree("A.B")
    )

    # Create C (root)
    _node_c = await WorkflowNodeFactory.create_async(
        session=db_session, version=version, path=Ltree("C")
    )

    # Move A under C -> C.A.B (Depth 3, max 2)
    with pytest.raises(Exception) as excinfo:
        await db_session.execute(
            text("SELECT workflow_nodes_move_subtree(:graph_id, :src, :dst)"),
            {"graph_id": graph.id, "src": "A", "dst": "C"},
        )
    assert "Move violates max_depth constraint" in str(excinfo.value)


@pytest.mark.asyncio
async def test_workflow_nodes_depth_trigger(db_session: AsyncSession):
    graph = await WorkflowGraphFactory.create_async(
        session=db_session, max_depth=2, version_count=0
    )
    version = await WorkflowVersionFactory.create_async(session=db_session, graph=graph)

    with pytest.raises(Exception):
        await WorkflowNodeFactory.create_async(
            session=db_session,
            version=version,
            path=Ltree("root.child.grandchild"),
        )


@pytest.mark.asyncio
async def test_workflow_nodes_depth_check_constraint(db_session: AsyncSession):
    graph = await WorkflowGraphFactory.create_async(
        session=db_session, max_depth=2, version_count=0
    )
    version = await WorkflowVersionFactory.create_async(session=db_session, graph=graph)

    await db_session.execute(
        text(
            "ALTER TABLE workflow_nodes DISABLE TRIGGER "
            "trg_workflow_nodes_validate_depth"
        )
    )
    try:
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    """
                    INSERT INTO workflow_nodes (
                        id,
                        version_id,
                        node_key,
                        level,
                        path,
                        type,
                        config,
                        created_at,
                        updated_at
                    ) VALUES (
                        :id,
                        :version_id,
                        :node_key,
                        'coarse',
                        (:path)::ltree,
                        'task',
                        '{}'::jsonb,
                        now(),
                        now()
                    )
                    """
                ),
                {
                    "id": uuid4(),
                    "version_id": version.id,
                    "node_key": "too_deep",
                    "path": "root.child.grandchild",
                },
            )
    finally:
        await db_session.rollback()
        await db_session.execute(
            text(
                "ALTER TABLE workflow_nodes ENABLE TRIGGER "
                "trg_workflow_nodes_validate_depth"
            )
        )


@pytest.mark.asyncio
async def test_workflow_nodes_cycle_prevention_trigger(db_session: AsyncSession):
    graph = await WorkflowGraphFactory.create_async(session=db_session, version_count=0)
    version = await WorkflowVersionFactory.create_async(session=db_session, graph=graph)

    node_a = await WorkflowNodeFactory.create_async(
        session=db_session, version=version, path=Ltree("root")
    )
    await WorkflowNodeFactory.create_async(
        session=db_session, version=version, path=Ltree("root.child")
    )

    with pytest.raises(Exception) as excinfo:
        await db_session.execute(
            text(
                """
                UPDATE workflow_nodes
                SET path = (:new_path)::ltree
                WHERE id = :node_id
                """
            ),
            {"new_path": "root.child.root", "node_id": node_a.id},
        )
    await db_session.rollback()
    assert "descendant path" in str(excinfo.value)
