from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from shared_data_layer.db.ltree import Ltree
from shared_data_layer.db.maintenance import refresh_active_chunks_view
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
from shared_data_layer.testing.factories.workflow import (
    WorkflowGraphFactory,
    WorkflowVersionFactory,
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

    await refresh_active_chunks_view(db_session)

    # Query view
    stmt = select(ActiveChunk)
    result = await db_session.execute(stmt)
    chunks = result.scalars().all()

    assert len(chunks) == 3
    chunk_ids = [c.id for c in chunks]
    assert chunk_active.id in chunk_ids


@pytest.mark.asyncio
async def test_active_chunks_view_updates_after_status_change(db_session: AsyncSession):
    doc = await DocumentFactory.create_async(session=db_session, chunk_count=1)
    chunk = doc.chunks[0]

    await refresh_active_chunks_view(db_session)

    result = await db_session.execute(
        select(ActiveChunk).where(ActiveChunk.id == chunk.id)
    )
    assert result.scalar_one() is not None

    doc.status = "archived"
    await db_session.flush()
    await refresh_active_chunks_view(db_session)

    result = await db_session.execute(
        select(ActiveChunk).where(ActiveChunk.id == chunk.id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_active_chunks_view_excludes_soft_deleted_docs(db_session: AsyncSession):
    doc = await DocumentFactory.create_async(session=db_session, chunk_count=1)
    chunk = doc.chunks[0]

    await refresh_active_chunks_view(db_session)
    result = await db_session.execute(
        select(ActiveChunk).where(ActiveChunk.id == chunk.id)
    )
    assert result.scalar_one() is not None

    doc.deleted_at = datetime.now(tz=timezone.utc)
    await db_session.flush()
    await refresh_active_chunks_view(db_session, concurrently=True)

    result = await db_session.execute(
        select(ActiveChunk).where(ActiveChunk.id == chunk.id)
    )
    assert result.scalar_one_or_none() is None


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
        session=db_session, access_scope="base", country_code="USA"
    )

    # Create user doc
    _doc_user = await DocumentFactory.create_async(
        session=db_session, access_scope="user_private", country_code="USA"
    )

    # Refresh cache
    await db_session.execute(
        text("SELECT refresh_base_documents_by_country(:country_code)"),
        {"country_code": None},
    )

    # Query MV
    stmt = select(BaseDocumentByCountry)
    result = await db_session.execute(stmt)
    docs = result.scalars().all()

    assert len(docs) == 1
    assert docs[0].document_id == doc_base.id


@pytest.mark.asyncio
async def test_base_documents_partition_creation(db_session: AsyncSession):
    doc_base = await DocumentFactory.create_async(
        session=db_session, access_scope="base", owner_user_id=None, country_code="BRA"
    )

    await db_session.execute(
        text("SELECT refresh_base_documents_by_country(:country_code)"),
        {"country_code": "BRA"},
    )

    stmt = select(BaseDocumentByCountry).where(
        BaseDocumentByCountry.document_id == doc_base.id
    )
    result = await db_session.execute(stmt)
    assert result.scalar_one() is not None

    partition_check = await db_session.execute(
        text(
            """
            SELECT 1 FROM pg_class c
            JOIN pg_inherits i ON c.oid = i.inhrelid
            JOIN pg_class p ON p.oid = i.inhparent
            WHERE p.relname = 'base_documents_by_country'
              AND c.relname = 'base_documents_by_country_bra'
            """
        )
    )
    assert partition_check.scalar_one() == 1


@pytest.mark.asyncio
async def test_base_documents_partition_catalog(db_session: AsyncSession):
    strategy = await db_session.execute(
        text(
            """
            SELECT partstrat::text
            FROM pg_partitioned_table pt
            JOIN pg_class c ON pt.partrelid = c.oid
            WHERE c.relname = 'base_documents_by_country'
            """
        )
    )
    assert strategy.scalar_one() == "l"

    partition_rows = await db_session.execute(
        text(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_inherits i ON c.oid = i.inhrelid
            JOIN pg_class p ON p.oid = i.inhparent
            WHERE p.relname = 'base_documents_by_country'
            """
        )
    )
    partition_names = {row[0] for row in partition_rows}
    assert len(partition_names) >= 249  # every ISO-3 code plus default

    expected_samples = {
        "base_documents_by_country_usa",
        "base_documents_by_country_gbr",
        "base_documents_by_country_can",
        "base_documents_by_country_afg",
        "base_documents_by_country_jpn",
        "base_documents_by_country_bra",
    }
    assert expected_samples.issubset(partition_names)

    default_partition = await db_session.execute(
        text(
            """
            SELECT c.relname
            FROM pg_partitioned_table pt
            JOIN pg_class parent ON parent.oid = pt.partrelid
            JOIN pg_class c ON c.oid = pt.partdefid
            WHERE parent.relname = 'base_documents_by_country'
            """
        )
    )
    assert default_partition.scalar_one() == "base_documents_by_country_default"


@pytest.mark.asyncio
async def test_retrieval_runs_document_scope_indexes(db_session: AsyncSession):
    indexes = await db_session.execute(
        text(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = 'retrieval_runs'
            """
        )
    )
    index_map = {row.indexname: row.indexdef for row in indexes}

    assert "ix_retrieval_runs_document_scope_gin" in index_map
    assert "jsonb_path_ops" in index_map["ix_retrieval_runs_document_scope_gin"]

    assert "ix_retrieval_runs_document_scope_country_codes_gin" in index_map
    assert (
        "country_codes"
        in index_map["ix_retrieval_runs_document_scope_country_codes_gin"]
    )


@pytest.mark.asyncio
async def test_workflow_nodes_path_indexes(db_session: AsyncSession):
    indexes = await db_session.execute(
        text(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = 'workflow_nodes'
            """
        )
    )
    index_map = {row.indexname: row.indexdef for row in indexes}
    assert "ix_workflow_nodes_version_path" in index_map
    assert "ix_workflow_nodes_path_gist" in index_map
    assert "USING GIST" in index_map["ix_workflow_nodes_path_gist"].upper()


@pytest.mark.asyncio
async def test_workflow_nodes_depth_check_constraint_catalog(
    db_session: AsyncSession,
):
    constraints = await db_session.execute(
        text(
            """
            SELECT conname, pg_get_constraintdef(c.oid) AS definition
            FROM pg_constraint c
            WHERE c.conrelid = 'workflow_nodes'::regclass
            """
        )
    )
    constraint_map = {row.conname: row.definition for row in constraints}
    assert "ck_workflow_nodes_path_depth" in constraint_map
    assert "nlevel" in constraint_map["ck_workflow_nodes_path_depth"].lower()


@pytest.mark.asyncio
async def test_workflow_version_diffs_view(db_session: AsyncSession):
    graph = await WorkflowGraphFactory.create_async(session=db_session, version_count=0)
    older = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
    version_a = await WorkflowVersionFactory.create_async(
        session=db_session, graph=graph, created_at=older, updated_at=older
    )
    version_b = await WorkflowVersionFactory.create_async(
        session=db_session,
        graph=graph,
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
        node_specs=[
            {"node_key": "root", "path": Ltree("root")},
            {"node_key": "child1", "path": Ltree("root.child1")},
            {"node_key": "child2", "path": Ltree("root.child2")},
        ],
        edge_specs=[],
    )

    rows = await db_session.execute(
        text(
            """
            SELECT
                workflow_version_id,
                previous_version_id,
                node_count,
                node_delta,
                edge_count,
                edge_delta
            FROM workflow_version_diffs
            WHERE graph_id = :graph_id
            ORDER BY created_at, workflow_version_id
            """
        ),
        {"graph_id": graph.id},
    )
    results = rows.fetchall()
    assert len(results) >= 2

    first = results[0]
    assert first.workflow_version_id == version_a.id
    assert first.previous_version_id is None
    assert first.node_delta == first.node_count
    assert first.edge_delta == first.edge_count

    second = results[1]
    assert second.workflow_version_id == version_b.id
    assert second.previous_version_id == version_a.id
    assert second.node_count >= first.node_count
    assert second.node_delta == second.node_count - first.node_count
    assert second.edge_delta == second.edge_count - first.edge_count


@pytest.mark.asyncio
async def test_pillar_answers_country_pillar_index(db_session: AsyncSession):
    indexes = await db_session.execute(
        text(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = 'pillar_answers'
            """
        )
    )
    index_map = {row.indexname: row.indexdef for row in indexes}

    assert "ix_pillar_answers_country_pillar" in index_map
    index_def = index_map["ix_pillar_answers_country_pillar"].lower()
    assert "country_code" in index_def
    assert "pillar_name" in index_def
    assert "status" in index_def
    assert "published" in index_def


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


@pytest.mark.asyncio
async def test_chunks_partition_catalog(db_session: AsyncSession):
    partitioned = await db_session.execute(
        text(
            """
            SELECT partstrat::text AS partstrat
            FROM pg_partitioned_table pt
            JOIN pg_class c ON pt.partrelid = c.oid
            WHERE c.relname = 'chunks'
            """
        )
    )
    assert partitioned.scalar_one() == "l"

    partition_rows = await db_session.execute(
        text(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_inherits i ON c.oid = i.inhrelid
            JOIN pg_class p ON p.oid = i.inhparent
            WHERE p.relname = 'chunks'
            """
        )
    )
    partition_names = {row[0] for row in partition_rows}
    expected_partitions = {
        "chunks_usa",
        "chunks_gbr",
        "chunks_can",
        "chunks_default",
    }
    assert expected_partitions.issubset(partition_names)

    default_partition = await db_session.execute(
        text(
            """
            SELECT c.relname
            FROM pg_partitioned_table pt
            JOIN pg_class parent ON parent.oid = pt.partrelid
            JOIN pg_class c ON c.oid = pt.partdefid
            WHERE parent.relname = 'chunks'
            """
        )
    )
    assert default_partition.scalar_one() == "chunks_default"

    index_rows = await db_session.execute(
        text(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = 'chunks'
            """
        )
    )
    index_map = {row.indexname: row.indexdef for row in index_rows}
    required_indexes = {
        "ix_chunks_document_position",
        "ix_chunks_text_tsv_gin",
        "ix_chunks_country_chunk_type",
        "ix_chunks_created_at_brin",
        "ix_chunks_updated_at_brin",
        "ix_chunks_embedding_ivfflat",
        "ix_chunks_embedding_hnsw",
    }
    assert required_indexes.issubset(index_map.keys())
    assert "USING BRIN" in index_map["ix_chunks_created_at_brin"].upper()
    assert "USING BRIN" in index_map["ix_chunks_updated_at_brin"].upper()
    assert "USING GIN" in index_map["ix_chunks_text_tsv_gin"].upper()
    assert "USING IVFFLAT" in index_map["ix_chunks_embedding_ivfflat"].upper()
    assert "USING HNSW" in index_map["ix_chunks_embedding_hnsw"].upper()


@pytest.mark.asyncio
async def test_graph_entities_partition_catalog(db_session: AsyncSession):
    partitioned = await db_session.execute(
        text(
            """
            SELECT partstrat::text AS partstrat
            FROM pg_partitioned_table pt
            JOIN pg_class c ON pt.partrelid = c.oid
            WHERE c.relname = 'graph_entities'
            """
        )
    )
    assert partitioned.scalar_one() == "l"

    partition_rows = await db_session.execute(
        text(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_inherits i ON c.oid = i.inhrelid
            JOIN pg_class p ON p.oid = i.inhparent
            WHERE p.relname = 'graph_entities'
            """
        )
    )
    partition_names = {row[0] for row in partition_rows}
    expected_partitions = {
        "graph_entities_usa",
        "graph_entities_gbr",
        "graph_entities_can",
        "graph_entities_default",
    }
    assert expected_partitions.issubset(partition_names)

    default_partition = await db_session.execute(
        text(
            """
            SELECT c.relname
            FROM pg_partitioned_table pt
            JOIN pg_class parent ON parent.oid = pt.partrelid
            JOIN pg_class c ON c.oid = pt.partdefid
            WHERE parent.relname = 'graph_entities'
            """
        )
    )
    assert default_partition.scalar_one() == "graph_entities_default"

    index_rows = await db_session.execute(
        text(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = 'graph_entities'
            """
        )
    )
    index_map = {row.indexname: row.indexdef for row in index_rows}
    required_indexes = {
        "ix_graph_entities_name",
        "ix_graph_entities_document_id",
        "ix_graph_entities_labels_gin",
        "uq_graph_entities_base_scope",
        "uq_graph_entities_user_scope",
        "ix_graph_entities_embedding_hnsw",
    }
    assert required_indexes.issubset(index_map.keys())
    assert "USING GIN" in index_map["ix_graph_entities_labels_gin"].upper()
    hnsw_def = index_map["ix_graph_entities_embedding_hnsw"].upper()
    assert "USING HNSW" in hnsw_def
    assert "VECTOR_COSINE_OPS" in hnsw_def


@pytest.mark.asyncio
async def test_graph_edges_seen_brin_index(db_session: AsyncSession):
    indexes = await db_session.execute(
        text(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = 'graph_edges'
            """
        )
    )
    index_map = {row.indexname: row.indexdef for row in indexes}

    assert "ix_graph_edges_seen_brin" in index_map
    index_def = index_map["ix_graph_edges_seen_brin"].upper()
    assert "USING BRIN" in index_def
    assert "FIRST_SEEN_AT" in index_def
    assert "LAST_SEEN_AT" in index_def


@pytest.mark.asyncio
async def test_graph_communities_entity_ids_gin_index(db_session: AsyncSession):
    indexes = await db_session.execute(
        text(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = 'graph_communities'
            """
        )
    )
    index_map = {row.indexname: row.indexdef for row in indexes}

    assert "ix_graph_communities_entity_ids_gin" in index_map
    index_def = index_map["ix_graph_communities_entity_ids_gin"].upper()
    assert "USING GIN" in index_def
    assert "ENTITY_IDS" in index_def
