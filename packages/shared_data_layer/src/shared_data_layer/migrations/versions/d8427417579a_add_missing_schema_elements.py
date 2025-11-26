"""add_missing_schema_elements

Revision ID: d8427417579a
Revises: a7f040967e5a
Create Date: 2025-11-25 19:13:06.219158

"""

from typing import Sequence, Union

import pgvector
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8427417579a"
down_revision: Union[str, None] = "a7f040967e5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create pillar_answers table
    op.create_table(
        "pillar_answers",
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("country_code", sa.String(length=3), nullable=False),
        sa.Column("pillar_name", sa.String(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("summary_markdown", sa.Text(), nullable=False),
        sa.Column("answer_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("generated_at", sa.Float(), nullable=True),
        sa.Column("expires_at", sa.Float(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_pillar_answers_document_id_documents"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_pillar_answers_owner_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pillar_answers")),
    )

    # 2. Create pillar_answer_sources table
    op.create_table(
        "pillar_answer_sources",
        sa.Column("pillar_answer_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("contribution_type", sa.String(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.id"],
            name=op.f("fk_pillar_answer_sources_chunk_id_chunks"),
        ),
        sa.ForeignKeyConstraint(
            ["pillar_answer_id"],
            ["pillar_answers.id"],
            name=op.f("fk_pillar_answer_sources_pillar_answer_id_pillar_answers"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pillar_answer_sources")),
    )

    # 3. Add embedding to graph_entities
    op.add_column(
        "graph_entities",
        sa.Column(
            "embedding", pgvector.sqlalchemy.vector.VECTOR(dim=512), nullable=True
        ),
    )

    # 4. Add evidence_span to graph_edges
    op.add_column("graph_edges", sa.Column("evidence_span", sa.Text(), nullable=True))

    # 5. Add transition_type to workflow_edges
    op.add_column(
        "workflow_edges",
        sa.Column(
            "transition_type", sa.String(), nullable=False, server_default="success"
        ),
    )
    # Remove default after creation to match model definition if desired, but keeping it is safer for existing rows (though table is likely empty)
    op.alter_column("workflow_edges", "transition_type", server_default=None)

    # 6. Update chunks.embedding dimension to 1024
    # Note: This requires dropping and recreating the column or using ALTER TYPE if supported by pgvector for dimension change.
    # pgvector supports ALTER COLUMN ... TYPE vector(1024) USING ...
    # But since we don't have data, we can just alter it.
    op.alter_column(
        "chunks",
        "embedding",
        type_=pgvector.sqlalchemy.vector.VECTOR(dim=1024),
        existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=1536),
        postgresql_using="embedding::vector(1024)",
    )


def downgrade() -> None:
    # 6. Revert chunks.embedding dimension
    op.alter_column(
        "chunks",
        "embedding",
        type_=pgvector.sqlalchemy.vector.VECTOR(dim=1536),
        existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=1024),
        postgresql_using="embedding::vector(1536)",
    )

    # 5. Drop transition_type
    op.drop_column("workflow_edges", "transition_type")

    # 4. Drop evidence_span
    op.drop_column("graph_edges", "evidence_span")

    # 3. Drop embedding
    op.drop_column("graph_entities", "embedding")

    # 2. Drop pillar_answer_sources
    op.drop_table("pillar_answer_sources")

    # 1. Drop pillar_answers
    op.drop_table("pillar_answers")
