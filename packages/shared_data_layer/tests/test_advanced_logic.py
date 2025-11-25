import pytest
from sqlalchemy import text, select
from uuid import uuid4

from shared_data_layer.testing.factories.documents import DocumentFactory
from shared_data_layer.testing.factories.knowledge_graph import GraphEdgeFactory, GraphEvidenceFactory
from shared_data_layer.testing.factories.workflow import WorkflowGraphFactory, WorkflowNodeFactory
from shared_data_layer.testing.base import AsyncBaseTestCase
from shared_data_layer.db.models.documents import Document
from shared_data_layer.db.models.workflow import WorkflowNode

@pytest.mark.asyncio
class TestAdvancedLogic(AsyncBaseTestCase):
    
    async def test_active_chat_refs_trigger(self, db_session):
        # 1. Create a document with explicit 0 refs
        doc = await DocumentFactory.create_async(session=db_session, active_chat_refs=0)
        assert doc.active_chat_refs == 0

        # 2. Attach to a conversation (insert into conversation_documents)
        conv_id = "conv_123"
        user_id = uuid4()
        
        await db_session.execute(
            text("""
            INSERT INTO conversation_documents 
            (id, conversation_id, document_id, attach_source, role, created_at, updated_at) 
            VALUES (:id, :conv_id, :doc_id, 'user_upload', 'primary', NOW(), NOW())
            """),
            {"id": uuid4(), "conv_id": conv_id, "doc_id": doc.id}
        )
        # Use flush() to fire triggers but keep transaction open for the test session
        await db_session.flush()

        # 3. Verify trigger incremented ref count
        # Need to refresh to see DB side changes
        await db_session.refresh(doc)
        assert doc.active_chat_refs == 1

        # 4. Detach (delete)
        await db_session.execute(
            text("DELETE FROM conversation_documents WHERE conversation_id = :conv_id AND document_id = :doc_id"),
            {"conv_id": conv_id, "doc_id": doc.id}
        )
        await db_session.flush()

        # 5. Verify trigger decremented ref count
        await db_session.refresh(doc)
        assert doc.active_chat_refs == 0

    async def test_graph_edge_evidence_rollup_mv(self, db_session):
        # 1. Create Edge and Evidence
        edge = await GraphEdgeFactory.create_async(session=db_session)
        
        # Refresh to make sure evidence is persisted
        await db_session.refresh(edge, attribute_names=["evidence"])
        assert len(edge.evidence) > 0
        evidence = edge.evidence[0]
        
        # 2. Refresh Materialized View
        await db_session.execute(text("REFRESH MATERIALIZED VIEW graph_edge_evidence_rollup"))
        
        # 3. Query the MV
        result = await db_session.execute(
            text("SELECT evidence_chunk_ids, evidence_count FROM graph_edge_evidence_rollup WHERE edge_id = :edge_id"),
            {"edge_id": edge.id}
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
            session=db_session,
            version=version,
            path="A"
        )
        # Child node B
        node_b = await WorkflowNodeFactory.create_async(
            session=db_session,
            version=version,
            path="A.B"
        )
        
        # Target parent C
        node_c = await WorkflowNodeFactory.create_async(
            session=db_session,
            version=version,
            path="C"
        )

        
        # 2. Call Stored Procedure to move A under C (so A becomes C.A, and A.B becomes C.A.B)
        # Note: The SP signature is (p_version_id, p_source_path, p_target_parent_path)
        
        await db_session.execute(
            text("SELECT workflow_nodes_move_subtree(:version_id, CAST(:source AS ltree), CAST(:target AS ltree))"),
            {"version_id": version.id, "source": "A", "target": "C"}
        )
        await db_session.flush()
        
        # 3. Verify new paths
        await db_session.refresh(node_a)
        await db_session.refresh(node_b)
        
        assert str(node_a.path) == "C.A"
        assert str(node_b.path) == "C.A.B"
