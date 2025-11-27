from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from shared_data_layer.db.ltree import Ltree
from shared_data_layer.db.models.documents import DocumentGCEvent
from shared_data_layer.testing.base import AsyncBaseTestCase
from shared_data_layer.testing.factories.documents import DocumentFactory
from shared_data_layer.testing.factories.knowledge_graph import (
    GraphEdgeFactory,
)
from shared_data_layer.testing.factories.workflow import (
    WorkflowGraphFactory,
    WorkflowNodeFactory,
)


@pytest.mark.asyncio
class TestAdvancedLogic(AsyncBaseTestCase):
    async def test_active_chat_refs_trigger(self, db_session):
        # 1. Create a document with explicit 0 refs
        doc = await DocumentFactory.create_async(session=db_session, active_chat_refs=0)
        assert doc.active_chat_refs == 0

        # 2. Attach to a conversation (insert into conversation_documents)
        conv_id = uuid4()

        await db_session.execute(
            text(
                "INSERT INTO conversations (id, owner_user_id) VALUES (:id, :owner_id)"
            ),
            {"id": conv_id, "owner_id": uuid4()},
        )

        await db_session.execute(
            text("""
            INSERT INTO conversation_documents 
            (conversation_id, document_id, attach_source, role) 
            VALUES (:conv_id, :doc_id, 'user_upload', 'primary')
            """),
            {"conv_id": conv_id, "doc_id": doc.id},
        )

        # 3. Trigger should have created a ref in active_chat_refs
        # Check it
        await db_session.refresh(doc)
        assert doc.active_chat_refs == 1

        # 4. Detach (delete from conversation_documents)
        await db_session.execute(
            text(
                "DELETE FROM conversation_documents "
                "WHERE conversation_id = :conv_id AND document_id = :doc_id"
            ),
            {"conv_id": conv_id, "doc_id": doc.id},
        )

        # 5. Trigger should have removed the ref
        await db_session.refresh(doc)
        assert doc.active_chat_refs == 0

        # Soft delete should also decrement
        await db_session.execute(
            text(
                "UPDATE conversation_documents SET deleted_at = now()"
                " WHERE conversation_id = :conv_id AND document_id = :doc_id"
            ),
            {"conv_id": conv_id, "doc_id": doc.id},
        )
        await db_session.refresh(doc)
        assert doc.active_chat_refs == 0

        # Restore should increment
        await db_session.execute(
            text(
                "UPDATE conversation_documents SET deleted_at = NULL"
                " WHERE conversation_id = :conv_id AND document_id = :doc_id"
            ),
            {"conv_id": conv_id, "doc_id": doc.id},
        )
        await db_session.refresh(doc)
        assert doc.active_chat_refs == 1

        # Clean up by hard delete
        await db_session.execute(
            text(
                "DELETE FROM conversation_documents "
                "WHERE conversation_id = :conv_id AND document_id = :doc_id"
            ),
            {"conv_id": conv_id, "doc_id": doc.id},
        )
        await db_session.refresh(doc)
        assert doc.active_chat_refs == 0

    async def test_graph_edge_evidence_rollup_mv(self, db_session):
        # 1. Create Edge (factory creates 1 evidence by default)
        edge = await GraphEdgeFactory.create_async(session=db_session)
        # Refresh to get the evidence created by factory
        await db_session.refresh(edge, attribute_names=["evidence"])
        assert len(edge.evidence) == 1
        evidence = edge.evidence[0]

        # Refresh MV (if it's a materialized view, we need to refresh it
        # manually or wait?)
        # The migration defined it as a VIEW or MATERIALIZED VIEW?
        # Let's check migration a7f040967e5a. It says "CREATE MATERIALIZED VIEW".
        # So we must refresh it.
        await db_session.execute(
            text("REFRESH MATERIALIZED VIEW graph_edge_evidence_rollup")
        )

        # 2. Query the view
        result = await db_session.execute(
            text(
                "SELECT evidence_chunk_ids, evidence_count "
                "FROM graph_edge_evidence_rollup WHERE edge_id = :edge_id"
            ),
            {"edge_id": edge.id},
        )
        row = result.first()

        assert row is not None
        assert row.evidence_count == 1
        # Postgres arrays come back as lists in SQLAlchemy
        assert row.evidence_chunk_ids == [evidence.chunk_id]

    async def test_workflow_nodes_move_subtree_sp(self, db_session):
        # 1. Create a Graph and Nodes
        # Structure: A -> B
        graph = await WorkflowGraphFactory.create_async(session=db_session)

        # Eager load versions
        await db_session.refresh(graph, attribute_names=["versions"])
        version = graph.versions[0]

        # We need to manually create nodes with specific paths to test ltree logic
        # Root node A
        node_a = await WorkflowNodeFactory.create_async(
            session=db_session, version=version, path=Ltree("A")
        )
        # Child node B
        node_b = await WorkflowNodeFactory.create_async(
            session=db_session, version=version, path=Ltree("A.B")
        )

        # Target parent C
        await WorkflowNodeFactory.create_async(
            session=db_session, version=version, path=Ltree("C")
        )

        # 2. Call Stored Procedure to move A under C (so A becomes C.A, and A.B
        # becomes C.A.B)
        # Note: The SP signature is (p_version_id, p_source_path, p_target_parent_path)

        await db_session.execute(
            text(
                "SELECT workflow_nodes_move_subtree("
                ":graph_id, CAST(:source AS ltree), CAST(:target AS ltree))"
            ),
            {"graph_id": graph.id, "source": "A", "target": "C"},
        )
        await db_session.flush()

        # 3. Verify new paths
        await db_session.refresh(node_a)
        await db_session.refresh(node_b)

        assert str(node_a.path) == "C.A"
        assert str(node_b.path) == "C.A.B"


@pytest.mark.asyncio
async def test_document_gc_events_logged(db_session):
    doc = await DocumentFactory.create_async(session=db_session, active_chat_refs=0)
    conv_id = uuid4()

    await db_session.execute(
        text("INSERT INTO conversations (id) VALUES (:id)"),
        {"id": conv_id},
    )

    await db_session.execute(
        text(
            "INSERT INTO conversation_documents "
            "(conversation_id, document_id, attach_source, role) "
            "VALUES (:conv_id, :doc_id, 'user_upload', 'primary')"
        ),
        {"conv_id": conv_id, "doc_id": doc.id},
    )

    await db_session.execute(
        text(
            "DELETE FROM conversation_documents "
            "WHERE conversation_id = :conv_id AND document_id = :doc_id"
        ),
        {"conv_id": conv_id, "doc_id": doc.id},
    )

    stmt = select(DocumentGCEvent).where(DocumentGCEvent.document_id == doc.id)
    events = (await db_session.execute(stmt)).scalars().all()
    assert any(event.event_type == "active_refs_zero" for event in events)

    doc.deleted_at = datetime.now(timezone.utc)
    await db_session.flush()

    stmt = select(DocumentGCEvent).where(DocumentGCEvent.document_id == doc.id)
    events = (await db_session.execute(stmt)).scalars().all()
    assert any(event.event_type == "deleted_state_changed" for event in events)
