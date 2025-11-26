"""fix_audit_findings_remove_user_add_ltree

Revision ID: 20251125231500
Revises: d8427417579a
Create Date: 2025-11-25 23:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlalchemy_utils

# revision identifiers, used by Alembic.
revision: str = '20251125231500'
down_revision: Union[str, None] = 'd8427417579a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable ltree extension
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")

    # 2. Drop Foreign Keys to users
    # We need to know the constraint names. 
    # Based on naming convention in base.py: fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s
    
    # graph_entities.owner_user_id -> users.id
    op.drop_constraint('fk_graph_entities_owner_user_id_users', 'graph_entities', type_='foreignkey')
    
    # pillar_answers.owner_user_id -> users.id
    op.drop_constraint('fk_pillar_answers_owner_user_id_users', 'pillar_answers', type_='foreignkey')

    # 3. Drop users table (if it exists and we want to remove it entirely)
    # Note: If other tables reference it (that we missed), this will fail.
    # We should check if any other table references users.
    # Documents had no FK.
    op.drop_table('users')

    # 4. Update GraphCommunity
    op.add_column('graph_communities', sa.Column('entity_ids', postgresql.ARRAY(sa.UUID()), nullable=True))
    op.add_column('graph_communities', sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('graph_communities', sa.Column('country_code', sa.String(length=3), nullable=True))
    op.add_column('graph_communities', sa.Column('algo_version', sa.String(), nullable=True))

    # 5. Update WorkflowNode path to ltree
    # Since column was String, we can cast it.
    op.alter_column('workflow_nodes', 'path',
               existing_type=sa.VARCHAR(),
               type_=sqlalchemy_utils.types.ltree.LtreeType(),
               postgresql_using='path::ltree')


def downgrade() -> None:
    # 5. Revert WorkflowNode path
    op.alter_column('workflow_nodes', 'path',
               existing_type=sqlalchemy_utils.types.ltree.LtreeType(),
               type_=sa.VARCHAR(),
               postgresql_using='path::text')

    # 4. Revert GraphCommunity
    op.drop_column('graph_communities', 'algo_version')
    op.drop_column('graph_communities', 'country_code')
    op.drop_column('graph_communities', 'metrics')
    op.drop_column('graph_communities', 'entity_ids')

    # 3. Recreate users table
    op.create_table('users',
        sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('email', sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column('hashed_password', sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column('is_active', sa.BOOLEAN(), autoincrement=False, nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_users'),
        sa.UniqueConstraint('email', name='uq_users_email')
    )

    # 2. Recreate Foreign Keys
    op.create_foreign_key('fk_pillar_answers_owner_user_id_users', 'pillar_answers', 'users', ['owner_user_id'], ['id'])
    op.create_foreign_key('fk_graph_entities_owner_user_id_users', 'graph_entities', 'users', ['owner_user_id'], ['id'])

    # 1. Disable ltree extension (optional, usually keep extensions)
    # op.execute("DROP EXTENSION IF EXISTS ltree")
