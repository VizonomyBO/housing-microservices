"""fix_sp_logic

Revision ID: 20251126143000
Revises: 20251126140000
Create Date: 2025-11-26 14:30:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251126143000"
down_revision: Union[str, None] = "20251126140000"
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
        v_new_root ltree;
    BEGIN
        -- 1. Lock the source subtree
        PERFORM 1 FROM workflow_nodes
        WHERE version_id = p_version_id AND path <@ p_source_path
        FOR UPDATE;

        -- 2. Validate target is not within source (acyclicity)
        IF p_target_parent_path <@ p_source_path THEN
            RAISE EXCEPTION 'Cannot move subtree into its own descendant';
        END IF;

        -- Calculate new root for the moved subtree
        -- e.g. src=A.B, dst=A.D. offset=1. subpath(A.B, 1)=B. new_root=A.D.B
        v_new_root := p_target_parent_path || subpath(p_source_path, nlevel(p_source_path) - 1);

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
            AND path <@ v_new_root
            AND nlevel(path) > v_max_depth
        ) THEN
            RAISE EXCEPTION 'Move violates max_depth constraint';
        END IF;
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # Revert to previous version (which was buggy but this is downgrade)
    pass
