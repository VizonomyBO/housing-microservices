"""add document uploads and cache status

Revision ID: 9c4d2c71fb31
Revises: 40072d62267b
Create Date: 2026-03-12 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9c4d2c71fb31"
down_revision: Union[str, None] = "40072d62267b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_uploads",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("country_code", sa.String(length=3), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("storage_uri", sa.String(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("uploaded_by", sa.UUID(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("verified_by", sa.UUID(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column(
            "reprocess_status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'not_started'"),
        ),
        sa.Column("reprocess_error", sa.Text(), nullable=True),
        sa.Column("reprocess_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reprocess_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.CheckConstraint(
            "country_code ~ '^[A-Z]{3}$'",
            name=op.f("ck_document_uploads_country_code_format"),
        ),
        sa.CheckConstraint(
            "byte_size >= 0",
            name=op.f("ck_document_uploads_byte_size_non_negative"),
        ),
        sa.CheckConstraint(
            "reprocess_status IN ('not_started','ingesting','reprocessing_cache',"
            "'reprocessing_pdf','done','failed')",
            name=op.f("ck_document_uploads_reprocess_status_enum"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_uploads_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_uploads")),
    )
    op.create_index(
        "ix_document_uploads_country_code",
        "document_uploads",
        ["country_code"],
        unique=False,
    )
    op.create_index(
        "ix_document_uploads_verified_reprocess_status",
        "document_uploads",
        ["verified", "reprocess_status"],
        unique=False,
    )
    op.create_index(
        "ix_document_uploads_document_id",
        "document_uploads",
        ["document_id"],
        unique=False,
    )

    with op.batch_alter_table("chat_response_cache") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(),
                nullable=False,
                server_default=sa.text("'ready'"),
            )
        )
        batch_op.create_check_constraint(
            op.f("ck_chat_response_cache_status_enum"),
            "status IN ('ready','stale','reprocessing')",
        )

    op.execute("UPDATE chat_response_cache SET status = 'ready' WHERE status IS NULL")
    op.create_index(
        "ix_chat_response_cache_country_code_status",
        "chat_response_cache",
        ["country_code", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chat_response_cache_country_code_status",
        table_name="chat_response_cache",
    )
    with op.batch_alter_table("chat_response_cache") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_chat_response_cache_status_enum"),
            type_="check",
        )
        batch_op.drop_column("status")

    op.drop_index("ix_document_uploads_document_id", table_name="document_uploads")
    op.drop_index(
        "ix_document_uploads_verified_reprocess_status",
        table_name="document_uploads",
    )
    op.drop_index("ix_document_uploads_country_code", table_name="document_uploads")
    op.drop_table("document_uploads")
