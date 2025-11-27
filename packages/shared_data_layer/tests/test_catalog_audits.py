from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import pytest

from .catalog_utils import fetch_index_catalog, fetch_partition_catalog


@dataclass(frozen=True)
class PartitionExpectation:
    table_name: str
    strategy: str
    required_partitions: Tuple[str, ...]
    default_partition: str
    min_partition_count: int | None = None


@dataclass(frozen=True)
class IndexExpectation:
    table_name: str
    required_indexes: Dict[str, Tuple[str, ...]]


PARTITION_EXPECTATIONS: Tuple[PartitionExpectation, ...] = (
    PartitionExpectation(
        table_name="base_documents_by_country",
        strategy="l",
        required_partitions=(
            "base_documents_by_country_usa",
            "base_documents_by_country_gbr",
            "base_documents_by_country_can",
            "base_documents_by_country_default",
        ),
        default_partition="base_documents_by_country_default",
        min_partition_count=249,
    ),
    PartitionExpectation(
        table_name="chunks",
        strategy="l",
        required_partitions=(
            "chunks_usa",
            "chunks_gbr",
            "chunks_can",
            "chunks_default",
        ),
        default_partition="chunks_default",
    ),
    PartitionExpectation(
        table_name="graph_entities",
        strategy="l",
        required_partitions=(
            "graph_entities_usa",
            "graph_entities_gbr",
            "graph_entities_can",
            "graph_entities_default",
        ),
        default_partition="graph_entities_default",
    ),
)


INDEX_EXPECTATIONS: Tuple[IndexExpectation, ...] = (
    IndexExpectation(
        table_name="retrieval_runs",
        required_indexes={
            "ix_retrieval_runs_document_scope_gin": ("USING GIN", "JSONB_PATH_OPS"),
            "ix_retrieval_runs_document_scope_country_codes_gin": ("COUNTRY_CODES",),
        },
    ),
    IndexExpectation(
        table_name="chunks",
        required_indexes={
            "ix_chunks_document_position": ("DOCUMENT_ID", "CHUNK_TYPE", "POSITION"),
            "ix_chunks_text_tsv_gin": ("USING GIN", "TEXT_TSV"),
            "ix_chunks_country_chunk_type": ("COUNTRY_CODE", "CHUNK_TYPE"),
            "ix_chunks_created_at_brin": ("USING BRIN", "CREATED_AT"),
            "ix_chunks_updated_at_brin": ("USING BRIN", "UPDATED_AT"),
            "ix_chunks_embedding_ivfflat": ("USING IVFFLAT", "EMBEDDING"),
            "ix_chunks_embedding_hnsw": ("USING HNSW", "EMBEDDING"),
        },
    ),
    IndexExpectation(
        table_name="graph_entities",
        required_indexes={
            "ix_graph_entities_name": (),
            "ix_graph_entities_document_id": (),
            "ix_graph_entities_labels_gin": ("USING GIN", "LABELS"),
            "uq_graph_entities_base_scope": (),
            "uq_graph_entities_user_scope": (),
            "ix_graph_entities_embedding_hnsw": (
                "USING HNSW",
                "VECTOR_COSINE_OPS",
            ),
        },
    ),
    IndexExpectation(
        table_name="graph_edges",
        required_indexes={
            "ix_graph_edges_seen_brin": (
                "USING BRIN",
                "FIRST_SEEN_AT",
                "LAST_SEEN_AT",
            )
        },
    ),
    IndexExpectation(
        table_name="graph_communities",
        required_indexes={
            "ix_graph_communities_entity_ids_gin": (
                "USING GIN",
                "ENTITY_IDS",
            )
        },
    ),
    IndexExpectation(
        table_name="pillar_answers",
        required_indexes={
            "ix_pillar_answers_country_pillar": (
                "COUNTRY_CODE",
                "PILLAR_NAME",
                "STATUS",
                "PUBLISHED",
            )
        },
    ),
    IndexExpectation(
        table_name="workflow_nodes",
        required_indexes={
            "ix_workflow_nodes_version_path": (),
            "ix_workflow_nodes_path_gist": ("USING GIST",),
        },
    ),
)


@pytest.mark.asyncio
@pytest.mark.parametrize("expectation", PARTITION_EXPECTATIONS)
async def test_partition_catalog_expectations(db_session, expectation):
    snapshot = await fetch_partition_catalog(db_session, expectation.table_name)
    assert snapshot.strategy == expectation.strategy
    partitions = snapshot.partitions
    assert set(expectation.required_partitions).issubset(partitions)
    assert snapshot.default_partition == expectation.default_partition
    if expectation.min_partition_count:
        assert len(partitions) >= expectation.min_partition_count


@pytest.mark.asyncio
@pytest.mark.parametrize("expectation", INDEX_EXPECTATIONS)
async def test_index_catalog_expectations(db_session, expectation):
    index_map = await fetch_index_catalog(db_session, expectation.table_name)
    for index_name, tokens in expectation.required_indexes.items():
        assert index_name in index_map, (
            f"{index_name} missing for {expectation.table_name}"
        )
        definition = index_map[index_name].upper()
        for token in tokens:
            assert token.upper() in definition, (
                f"{token} missing from {index_name} definition"
            )
