"""add_views

Revision ID: 20251126140000
Revises: 20251125233000
Create Date: 2025-11-26 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251126140000"
down_revision: Union[str, None] = "1fc8daf120c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. active_chunks VIEW
    op.execute("DROP VIEW IF EXISTS active_chunks")
    op.execute("""
    CREATE VIEW active_chunks AS
    SELECT c.id, c.document_id, c.chunk_index, c.text, c.embedding, c.token_count, 
           c.page_num, c.type, c.artifact_uri, c.schema_summary, c.content_hash, 
           c.owner_user_id, c.country_code, c.section_path, c.bbox, c.text_tsv, 
           c.table_payload, c.metadata, c.created_at, c.updated_at
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE d.status = 'active';
    """)

    # 2. graph_edge_evidence_rollup MATERIALIZED VIEW
    op.execute("DROP MATERIALIZED VIEW IF EXISTS graph_edge_evidence_rollup")
    op.execute("""
    CREATE MATERIALIZED VIEW graph_edge_evidence_rollup AS
    SELECT
        edge_id,
        array_agg(chunk_id ORDER BY chunk_id) AS evidence_chunk_ids,
        count(chunk_id) AS evidence_count,
        now() AS last_refreshed_at
    FROM graph_evidence
    GROUP BY edge_id;
    """)
    op.create_index(
        "ix_graph_edge_evidence_rollup_edge_id",
        "graph_edge_evidence_rollup",
        ["edge_id"],
    )
    op.execute(
        "CREATE INDEX ix_graph_edge_evidence_rollup_evidence_chunk_ids ON graph_edge_evidence_rollup USING GIN (evidence_chunk_ids)"
    )

    # 3. base_documents_by_country MATERIALIZED VIEW
    op.execute("DROP MATERIALIZED VIEW IF EXISTS base_documents_by_country")
    op.execute("""
    CREATE MATERIALIZED VIEW base_documents_by_country AS
    SELECT *
    FROM documents
    WHERE access_scope = 'base';
    """)
    op.create_index(
        "ix_base_documents_by_country_country_code",
        "base_documents_by_country",
        ["country_code"],
    )

    # 4. graph_hot_entities MATERIALIZED VIEW
    op.execute("DROP MATERIALIZED VIEW IF EXISTS graph_hot_entities")
    op.execute("""
    CREATE MATERIALIZED VIEW graph_hot_entities AS
    SELECT
        e.id,
        e.name,
        e.type,
        e.country_code,
        count(ge.id) as edge_count
    FROM graph_entities e
    JOIN graph_edges ge ON e.id = ge.source_id OR e.id = ge.target_id
    GROUP BY e.id, e.name, e.type, e.country_code
    ORDER BY count(ge.id) DESC
    LIMIT 1000;
    """)
    op.create_index(
        "ix_graph_hot_entities_country_code", "graph_hot_entities", ["country_code"]
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS graph_hot_entities")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS base_documents_by_country")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS graph_edge_evidence_rollup")
    op.execute("DROP VIEW IF EXISTS active_chunks")
