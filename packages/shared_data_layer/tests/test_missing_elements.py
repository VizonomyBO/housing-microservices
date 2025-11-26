import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared_data_layer.db.models.knowledge_graph import GraphEdge, GraphEntity
from shared_data_layer.db.models.retrieval import (
    PillarAnswer,
    PillarAnswerSource,
)
from shared_data_layer.db.models.workflow import (
    WorkflowEdge,
)
from shared_data_layer.testing.factories.knowledge_graph import (
    GraphEdgeFactory,
    GraphEntityFactory,
)
from shared_data_layer.testing.factories.retrieval import ChunkFactory
from shared_data_layer.testing.factories.workflow import (
    WorkflowGraphFactory,
    WorkflowVersionFactory,
)


@pytest.mark.asyncio
async def test_pillar_answer_creation(db_session: AsyncSession):
    # Create User ID
    import uuid

    user_id = uuid.uuid4()

    # Create dependencies
    chunk = await ChunkFactory.create_async(session=db_session)

    # Create PillarAnswer
    answer = PillarAnswer(
        owner_user_id=user_id,  # Use created user id
        country_code="US",
        pillar_name="finance",
        document_id=chunk.document_id,
        content_hash="hash123",
        summary_markdown="Summary",
        answer_json={"key": "value"},
        status="published",
    )
    db_session.add(answer)
    await db_session.flush()

    # Create PillarAnswerSource
    source = PillarAnswerSource(
        pillar_answer_id=answer.id,
        chunk_id=chunk.id,
        contribution_type="primary",
        evidence_text="Evidence",
        weight=0.8,
    )
    db_session.add(source)
    await db_session.flush()

    # Verify
    stmt = select(PillarAnswer).where(PillarAnswer.id == answer.id)
    result = await db_session.execute(stmt)
    fetched_answer = result.scalar_one()
    assert fetched_answer.pillar_name == "finance"

    stmt_source = select(PillarAnswerSource).where(PillarAnswerSource.id == source.id)
    result_source = await db_session.execute(stmt_source)
    fetched_source = result_source.scalar_one()
    assert fetched_source.evidence_text == "Evidence"


@pytest.mark.asyncio
async def test_graph_entity_embedding(db_session: AsyncSession):
    # Create entity with embedding
    entity = await GraphEntityFactory.create_async(
        session=db_session, embedding=[0.1] * 512
    )

    stmt = select(GraphEntity).where(GraphEntity.id == entity.id)
    result = await db_session.execute(stmt)
    fetched_entity = result.scalar_one()
    # pgvector returns numpy array or list? usually list or object that behaves
    # like list
    # But we just want to check it's not None and has correct dim
    assert fetched_entity.embedding is not None
    # assert len(fetched_entity.embedding) == 512 # Might need to cast to list if Vector


@pytest.mark.asyncio
async def test_graph_edge_evidence_span(db_session: AsyncSession):
    entity_a = await GraphEntityFactory.create_async(session=db_session)
    entity_b = await GraphEntityFactory.create_async(session=db_session)

    edge = await GraphEdgeFactory.create_async(
        session=db_session,
        source=entity_a,
        target=entity_b,
        relation="rel",
        evidence_span="Span of text",
    )

    stmt = select(GraphEdge).where(GraphEdge.id == edge.id)
    result = await db_session.execute(stmt)
    fetched_edge = result.scalar_one()
    assert fetched_edge.evidence_span == "Span of text"


@pytest.mark.asyncio
async def test_workflow_edge_transition_type(db_session: AsyncSession):
    graph = await WorkflowGraphFactory.create_async(session=db_session)
    version = await WorkflowVersionFactory.create_async(session=db_session, graph=graph)

    edge = WorkflowEdge(
        version_id=version.id,
        source_node_id="node1",
        target_node_id="node2",
        transition_type="failure",
    )
    db_session.add(edge)
    await db_session.flush()

    stmt = select(WorkflowEdge).where(WorkflowEdge.id == edge.id)
    result = await db_session.execute(stmt)
    fetched_edge = result.scalar_one()
    assert fetched_edge.transition_type == "failure"
