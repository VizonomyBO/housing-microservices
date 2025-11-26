import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy_utils import Ltree

from shared_data_layer.db.models.documents import BaseDocumentByCountry
from shared_data_layer.db.models.knowledge_graph import (
    GraphEdgeEvidenceRollup,
    GraphHotEntity,
)
from shared_data_layer.db.models.workflow import WorkflowNode
from shared_data_layer.repositories.documents import DocumentRepository
from shared_data_layer.repositories.knowledge_graph import KnowledgeGraphRepository
from shared_data_layer.repositories.workflow import WorkflowGraphRepository
from shared_data_layer.testing.factories.documents import ChunkFactory
from shared_data_layer.testing.factories.knowledge_graph import (
    GraphEdgeFactory,
    GraphEntityFactory,
)
from shared_data_layer.testing.factories.workflow import (
    WorkflowGraphFactory,
    WorkflowNodeFactory,
    WorkflowVersionFactory,
)


@pytest.mark.asyncio
async def test_document_repo_refresh_base_documents(db_session: AsyncSession):
    repo = DocumentRepository(db_session)

    # Create base document via repo
    await repo.create_or_get_document(
        owner_user_id=None,
        content_hash="hash1",
        access_scope="base",
        country_code="US",
        status="active",
        canonical_name="doc1",
    )

    # Check MV
    stmt = select(BaseDocumentByCountry)
    result = await db_session.execute(stmt)
    docs = result.scalars().all()

    assert len(docs) == 1
    assert docs[0].country_code == "US"


@pytest.mark.asyncio
async def test_kg_repo_refresh_hot_entities(db_session: AsyncSession):
    repo = KnowledgeGraphRepository(db_session)

    # Create entity
    entity = await GraphEntityFactory.create_async(session=db_session, name="HotRepo")

    # Upsert edge via repo (should trigger refresh)
    await repo.upsert_edge(
        {
            "source_id": entity.id,
            "target_id": entity.id,  # Self loop
            "relation": "self",
            "weight": 1.0,
        }
    )

    # Check MV
    stmt = select(GraphHotEntity).where(GraphHotEntity.id == entity.id)
    result = await db_session.execute(stmt)
    hot_entity = result.scalar_one_or_none()

    assert hot_entity is not None
    assert hot_entity.edge_count >= 1


@pytest.mark.asyncio
async def test_kg_repo_add_evidence_refresh_rollup(db_session: AsyncSession):
    repo = KnowledgeGraphRepository(db_session)

    # Create edge
    edge = await GraphEdgeFactory.create_async(session=db_session)
    chunk = await ChunkFactory.create_async(session=db_session)

    # Add evidence via repo
    await repo.add_evidence(edge.id, chunk.id, evidence_text="found it")

    # Check MV
    stmt = select(GraphEdgeEvidenceRollup).where(
        GraphEdgeEvidenceRollup.edge_id == edge.id
    )
    result = await db_session.execute(stmt)
    rollup = result.scalar_one_or_none()

    assert rollup is not None
    assert chunk.id in rollup.evidence_chunk_ids


@pytest.mark.asyncio
async def test_workflow_repo_move_subtree(db_session: AsyncSession):
    repo = WorkflowGraphRepository(db_session)

    # Setup graph
    graph = await WorkflowGraphFactory.create_async(session=db_session, max_depth=5)
    version = await WorkflowVersionFactory.create_async(session=db_session, graph=graph)

    # A -> B
    _node_a = await WorkflowNodeFactory.create_async(
        session=db_session, version=version, path=Ltree("A")
    )
    node_b = await WorkflowNodeFactory.create_async(
        session=db_session, version=version, path=Ltree("A.B")
    )
    _node_d = await WorkflowNodeFactory.create_async(
        session=db_session, version=version, path=Ltree("A.D")
    )

    # Move B under D
    node_b_id = node_b.id
    await repo.move_subtree(version.id, "A.B", "A.D")

    # Verify
    stmt = select(WorkflowNode).where(WorkflowNode.id == node_b_id)
    result = await db_session.execute(stmt)
    node_b_refreshed = result.scalar_one()

    assert str(node_b_refreshed.path) == "A.D.B"
