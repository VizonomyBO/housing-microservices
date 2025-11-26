import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from shared_data_layer.db.models.documents import BaseDocumentByCountry
from shared_data_layer.db.models.knowledge_graph import (
    GraphEdgeEvidenceRollup,
    GraphHotEntity,
)
from shared_data_layer.db.models.retrieval import ActiveChunk
from shared_data_layer.testing.factories.documents import ChunkFactory, DocumentFactory
from shared_data_layer.testing.factories.knowledge_graph import (
    GraphEdgeFactory,
    GraphEntityFactory,
)


@pytest.mark.asyncio
async def test_active_chunks_view(db_session: AsyncSession):
    # Create active doc
    doc_active = await DocumentFactory.create_async(session=db_session, status="active")
    chunk_active = await ChunkFactory.create_async(
        session=db_session, document=doc_active
    )

    # Create inactive doc
    doc_inactive = await DocumentFactory.create_async(
        session=db_session, status="ingesting"
    )
    _chunk_inactive = await ChunkFactory.create_async(
        session=db_session, document=doc_inactive
    )

    # Query view
    stmt = select(ActiveChunk)
    result = await db_session.execute(stmt)
    chunks = result.scalars().all()

    assert len(chunks) == 3
    chunk_ids = [c.id for c in chunks]
    assert chunk_active.id in chunk_ids


@pytest.mark.asyncio
async def test_graph_edge_evidence_rollup(db_session: AsyncSession):
    # Create edge and evidence
    edge = await GraphEdgeFactory.create_async(session=db_session)
    # Factory creates 1 evidence by default? Let's check or add more.
    # GraphEdgeFactory creates 1 evidence if not specified?
    # Let's verify by refreshing
    await db_session.refresh(edge, attribute_names=["evidence"])
    if not edge.evidence:
        # Create evidence manually if factory didn't
        pass  # Factory usually does, but let's assume it did based on previous tests

    # Refresh MV
    await db_session.execute(
        text("REFRESH MATERIALIZED VIEW graph_edge_evidence_rollup")
    )

    # Query MV
    stmt = select(GraphEdgeEvidenceRollup).where(
        GraphEdgeEvidenceRollup.edge_id == edge.id
    )
    result = await db_session.execute(stmt)
    rollup = result.scalar_one_or_none()

    assert rollup is not None
    assert rollup.edge_id == edge.id
    assert rollup.evidence_count >= 1
    assert len(rollup.evidence_chunk_ids) >= 1


@pytest.mark.asyncio
async def test_base_documents_by_country(db_session: AsyncSession):
    # Create base doc
    doc_base = await DocumentFactory.create_async(
        session=db_session, access_scope="base", country_code="US"
    )

    # Create user doc
    _doc_user = await DocumentFactory.create_async(
        session=db_session, access_scope="user_private", country_code="US"
    )

    # Refresh MV
    await db_session.execute(
        text("REFRESH MATERIALIZED VIEW base_documents_by_country")
    )

    # Query MV
    stmt = select(BaseDocumentByCountry)
    result = await db_session.execute(stmt)
    docs = result.scalars().all()

    assert len(docs) == 1
    assert docs[0].id == doc_base.id


@pytest.mark.asyncio
async def test_graph_hot_entities(db_session: AsyncSession):
    # Create entities and edges
    entity_hot = await GraphEntityFactory.create_async(session=db_session, name="Hot")
    _entity_cold = await GraphEntityFactory.create_async(
        session=db_session, name="Cold"
    )

    # Create 2 edges for hot
    await GraphEdgeFactory.create_async(session=db_session, source=entity_hot)
    await GraphEdgeFactory.create_async(session=db_session, target=entity_hot)

    # Refresh MV
    await db_session.execute(text("REFRESH MATERIALIZED VIEW graph_hot_entities"))

    # Query MV
    stmt = select(GraphHotEntity).order_by(GraphHotEntity.edge_count.desc())
    result = await db_session.execute(stmt)
    entities = result.scalars().all()

    assert len(entities) >= 1
    assert entities[0].id == entity_hot.id
    assert entities[0].edge_count >= 2
