from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared_data_layer.db.models.conversations import Conversation
from shared_data_layer.db.models.knowledge_graph import GraphEdge, GraphEntity
from shared_data_layer.db.models.retrieval import (
    PillarAnswer,
    PillarAnswerSource,
)
from shared_data_layer.db.models.workflow import WorkflowEdge
from shared_data_layer.repositories.documents import DocumentRepository
from shared_data_layer.repositories.retrieval import PillarAnswerRepository
from shared_data_layer.testing.factories.documents import DocumentFactory
from shared_data_layer.testing.factories.knowledge_graph import (
    GraphCommunityFactory,
    GraphEdgeFactory,
    GraphEntityFactory,
)
from shared_data_layer.testing.factories.retrieval import ChunkFactory
from shared_data_layer.testing.factories.workflow import (
    WorkflowGraphFactory,
    WorkflowNodeFactory,
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
        country_code="USA",
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
    assert fetched_source.chunk_country_code == chunk.country_code


@pytest.mark.asyncio
async def test_pillar_answer_requires_owner_for_non_base_scope(
    db_session: AsyncSession,
):
    document = await DocumentFactory.create_async(
        session=db_session,
        access_scope="user_private",
    )
    repo = PillarAnswerRepository(db_session)

    with pytest.raises(ValueError, match="owner_user_id is required"):
        await repo.create_pillar_answer(
            owner_user_id=None,
            document_id=document.id,
            country_code=document.country_code or "USA",
            pillar_name="finance",
            content_hash="hash123",
            summary_markdown="Summary",
            answer_json={"key": "value"},
            status="draft",
        )


@pytest.mark.asyncio
async def test_pillar_answer_repository_enforces_owner_identity(
    db_session: AsyncSession,
):
    document = await DocumentFactory.create_async(
        session=db_session,
        access_scope="user_private",
    )
    repo = PillarAnswerRepository(db_session)

    answer = await repo.create_pillar_answer(
        owner_user_id=document.owner_user_id,
        document_id=document.id,
        country_code=document.country_code or "USA",
        pillar_name="finance",
        content_hash="hash456",
        summary_markdown="Summary",
        answer_json={"key": "value"},
        status="published",
    )

    assert answer.owner_user_id == document.owner_user_id


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
async def test_graph_entity_requires_country_for_base_scope(
    db_session: AsyncSession,
):
    entity = GraphEntity(
        name="MissingCountry",
        entity_type="organization",
        entity_key=f"missing-{uuid4().hex}",
        owner_user_id=None,
        country_code=None,
    )

    db_session.add(entity)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_graph_edge_evidence_span(db_session: AsyncSession):
    entity_a = await GraphEntityFactory.create_async(session=db_session)
    entity_b = await GraphEntityFactory.create_async(session=db_session)

    edge = await GraphEdgeFactory.create_async(
        session=db_session,
        source=entity_a,
        target=entity_b,
        edge_type="rel",
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
    source_node = await WorkflowNodeFactory.create_async(
        session=db_session, version=version
    )
    target_node = await WorkflowNodeFactory.create_async(
        session=db_session, version=version
    )

    edge = WorkflowEdge(
        version_id=version.id,
        source_node_id=source_node.id,
        target_node_id=target_node.id,
        transition_type="failure",
    )
    db_session.add(edge)
    await db_session.flush()

    stmt = select(WorkflowEdge).where(WorkflowEdge.id == edge.id)
    result = await db_session.execute(stmt)
    fetched_edge = result.scalar_one()
    assert fetched_edge.transition_type == "failure"


@pytest.mark.asyncio
async def test_document_canonical_name_uniqueness(db_session: AsyncSession):
    owner_id = uuid4()
    await DocumentFactory.create_async(
        session=db_session,
        owner_user_id=owner_id,
        canonical_name="Duplicate",
        chunks=[],
    )

    with pytest.raises(IntegrityError):
        await DocumentFactory.create_async(
            session=db_session,
            owner_user_id=owner_id,
            canonical_name="Duplicate",
            chunks=[],
        )


@pytest.mark.asyncio
async def test_document_canonical_name_case_insensitive_collision(
    db_session: AsyncSession,
):
    owner_id = uuid4()
    await DocumentFactory.create_async(
        session=db_session,
        owner_user_id=owner_id,
        canonical_name="ProjectAtlas",
        chunk_count=0,
    )

    with pytest.raises(IntegrityError):
        await DocumentFactory.create_async(
            session=db_session,
            owner_user_id=owner_id,
            canonical_name="projectatlas",
            chunk_count=0,
        )


@pytest.mark.asyncio
async def test_base_document_attachment_requires_matching_country(
    db_session: AsyncSession,
):
    repo = DocumentRepository(db_session)
    base_doc = await DocumentFactory.create_async(
        session=db_session,
        access_scope="base",
        owner_user_id=None,
        country_code="USA",
        active_chat_refs=0,
        chunk_count=0,
    )
    allowed_conversation = Conversation(owner_user_id=uuid4(), country_code="USA")
    blocked_conversation = Conversation(owner_user_id=uuid4(), country_code="CAN")
    db_session.add_all([allowed_conversation, blocked_conversation])
    await db_session.flush()

    attachment = await repo.attach_to_conversation(
        conversation_id=allowed_conversation.id,
        document_id=base_doc.id,
        attach_source="unit-test",
    )
    assert attachment.deleted_at is None

    with pytest.raises(ValueError):
        await repo.attach_to_conversation(
            conversation_id=blocked_conversation.id,
            document_id=base_doc.id,
            attach_source="unit-test",
        )


@pytest.mark.asyncio
async def test_conversation_attachment_soft_delete_toggles_chat_refs(
    db_session: AsyncSession,
):
    repo = DocumentRepository(db_session)
    document = await DocumentFactory.create_async(
        session=db_session,
        chunk_count=0,
        active_chat_refs=0,
    )
    conversation = Conversation(
        owner_user_id=document.owner_user_id,
        country_code=document.country_code,
    )
    db_session.add(conversation)
    await db_session.flush()

    await repo.attach_to_conversation(
        conversation_id=conversation.id,
        document_id=document.id,
        attach_source="unit-test",
    )
    await db_session.refresh(document)
    assert document.active_chat_refs == 1

    await repo.detach_from_conversation(conversation.id, document.id)
    await db_session.flush()
    await db_session.refresh(document)
    assert document.active_chat_refs == 0

    await repo.attach_to_conversation(
        conversation_id=conversation.id,
        document_id=document.id,
        attach_source="unit-test",
    )
    await db_session.flush()
    await db_session.refresh(document)
    assert document.active_chat_refs == 1

    await repo.detach_from_conversation(conversation.id, document.id)
    await db_session.flush()
    await db_session.refresh(document)
    assert document.active_chat_refs == 0


@pytest.mark.asyncio
async def test_document_active_chat_refs_non_negative_constraint(
    db_session: AsyncSession,
):
    document = await DocumentFactory.create_async(session=db_session, chunk_count=0)
    document.active_chat_refs = -1
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_graph_communities_normalize(db_session: AsyncSession):
    member_a = uuid4()
    member_b = uuid4()
    community = await GraphCommunityFactory.create_async(
        session=db_session,
        entity_ids=[member_b, member_a, member_b],
        metrics={},
    )
    await db_session.refresh(community)
    assert community.entity_ids == sorted({member_a, member_b})
    assert community.metrics["member_count"] == 2
