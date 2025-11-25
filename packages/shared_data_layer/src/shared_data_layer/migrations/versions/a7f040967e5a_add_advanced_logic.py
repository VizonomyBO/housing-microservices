"""add_advanced_logic

Revision ID: a7f040967e5a
Revises: 3d2859a21d27
Create Date: 2025-11-25 18:22:51.745054

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7f040967e5a'
down_revision: Union[str, None] = '3d2859a21d27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Materialized View: graph_edge_evidence_rollup
    op.execute("""
    CREATE MATERIALIZED VIEW graph_edge_evidence_rollup AS
    SELECT
        edge_id,
        ARRAY_AGG(chunk_id ORDER BY chunk_id) AS evidence_chunk_ids,
        COUNT(chunk_id) AS evidence_count,
        NOW() AS last_refreshed_at
    FROM graph_evidence
    GROUP BY edge_id;
    """)
    op.execute("CREATE INDEX ix_graph_edge_evidence_rollup_edge_id ON graph_edge_evidence_rollup (edge_id);")
    op.execute("CREATE INDEX ix_graph_edge_evidence_rollup_evidence_chunk_ids ON graph_edge_evidence_rollup USING GIN (evidence_chunk_ids);")

    # 2. Materialized View: base_documents_by_country
    op.execute("""
    CREATE MATERIALIZED VIEW base_documents_by_country AS
    SELECT * FROM documents
    WHERE access_scope = 'base';
    """)
    op.execute("CREATE INDEX ix_base_documents_by_country_country_code ON base_documents_by_country (country_code);")

    # 3. Trigger: active_chat_refs
    op.execute("""
    CREATE OR REPLACE FUNCTION update_active_chat_refs() RETURNS TRIGGER AS $$
    BEGIN
        IF (TG_OP = 'INSERT') THEN
            UPDATE documents SET active_chat_refs = active_chat_refs + 1 WHERE id = NEW.document_id;
            RETURN NEW;
        ELSIF (TG_OP = 'DELETE') THEN
            UPDATE documents SET active_chat_refs = active_chat_refs - 1 WHERE id = OLD.document_id;
            RETURN OLD;
        END IF;
        RETURN NULL;
    END;
    $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
    CREATE TRIGGER trg_update_active_chat_refs
    AFTER INSERT OR DELETE ON conversation_documents
    FOR EACH ROW EXECUTE FUNCTION update_active_chat_refs();
    """)

    # 4. Stored Procedure: workflow_nodes_move_subtree
    # Implements safe subtree moves with ltree
    op.execute("""
    CREATE OR REPLACE FUNCTION workflow_nodes_move_subtree(
        p_version_id UUID,
        p_source_path ltree,
        p_target_parent_path ltree
    ) RETURNS VOID AS $$
    DECLARE
        v_max_depth INTEGER;
        v_graph_id UUID;
    BEGIN
        -- 1. Lock the source subtree
        PERFORM 1 FROM workflow_nodes
        WHERE version_id = p_version_id AND path::ltree <@ p_source_path
        FOR UPDATE;

        -- 2. Validate target is not within source (acyclicity)
        IF p_target_parent_path <@ p_source_path THEN
            RAISE EXCEPTION 'Cannot move subtree into its own descendant';
        END IF;

        -- 3. Update paths
        UPDATE workflow_nodes
        SET path = (p_target_parent_path || subpath(path::ltree, nlevel(p_source_path) - 1))::text
        WHERE version_id = p_version_id AND path::ltree <@ p_source_path;

        -- 4. Revalidate depth
        -- Get graph_id from version to check max_depth
        SELECT graph_id INTO v_graph_id FROM workflow_versions WHERE id = p_version_id;
        SELECT max_depth INTO v_max_depth FROM workflow_graphs WHERE id = v_graph_id;
        
        IF EXISTS (
            SELECT 1 FROM workflow_nodes 
            WHERE version_id = p_version_id 
            AND (p_target_parent_path || subpath(path::ltree, nlevel(p_source_path) - 1))::ltree <@ (p_target_parent_path || subpath(p_source_path, nlevel(p_source_path) - 1))
            AND nlevel((p_target_parent_path || subpath(path::ltree, nlevel(p_source_path) - 1))::ltree) > v_max_depth
        ) THEN
            RAISE EXCEPTION 'Move violates max_depth constraint';
        END IF;
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS workflow_nodes_move_subtree")
    op.execute("DROP TRIGGER IF EXISTS trg_update_active_chat_refs ON conversation_documents")
    op.execute("DROP FUNCTION IF EXISTS update_active_chat_refs")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS base_documents_by_country")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS graph_edge_evidence_rollup")
