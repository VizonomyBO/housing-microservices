"""fix_sp_ltree

Revision ID: 20251125233000
Revises: 20251125231500
Create Date: 2025-11-25 23:30:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251125233000"
down_revision: Union[str, None] = "20251125231500"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
        WHERE version_id = p_version_id AND path <@ p_source_path
        FOR UPDATE;

        -- 2. Validate target is not within source (acyclicity)
        IF p_target_parent_path <@ p_source_path THEN
            RAISE EXCEPTION 'Cannot move subtree into its own descendant';
        END IF;

        -- 3. Update paths
        -- CAST to ltree, not text
        UPDATE workflow_nodes
        SET path = (p_target_parent_path || subpath(path, nlevel(p_source_path) - 1))
        WHERE version_id = p_version_id AND path <@ p_source_path;

        -- 4. Revalidate depth
        -- Get graph_id from version to check max_depth
        SELECT graph_id INTO v_graph_id FROM workflow_versions WHERE id = p_version_id;
        SELECT max_depth INTO v_max_depth FROM workflow_graphs WHERE id = v_graph_id;
        
        IF EXISTS (
            SELECT 1 FROM workflow_nodes 
            WHERE version_id = p_version_id 
            AND (p_target_parent_path || subpath(path, nlevel(p_source_path) - 1)) <@ (p_target_parent_path || subpath(p_source_path, nlevel(p_source_path) - 1))
            AND nlevel((p_target_parent_path || subpath(path, nlevel(p_source_path) - 1))) > v_max_depth
        ) THEN
            RAISE EXCEPTION 'Move violates max_depth constraint';
        END IF;
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # Revert to text cast version (technically wrong for ltree column, but this is downgrade)
    # Actually, if we downgrade, we might revert column type too?
    # No, this migration only fixes the SP.
    # If we downgrade this, the SP will be broken again.
    pass
