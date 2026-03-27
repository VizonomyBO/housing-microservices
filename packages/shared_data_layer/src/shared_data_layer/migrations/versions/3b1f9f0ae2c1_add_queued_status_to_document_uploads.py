"""add queued status to document uploads

Revision ID: 3b1f9f0ae2c1
Revises: 9c4d2c71fb31
Create Date: 2026-03-12 20:10:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b1f9f0ae2c1"
down_revision: Union[str, None] = "9c4d2c71fb31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("document_uploads") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_document_uploads_reprocess_status_enum"),
            type_="check",
        )
        batch_op.create_check_constraint(
            op.f("ck_document_uploads_reprocess_status_enum"),
            "reprocess_status IN ('not_started','queued','ingesting','reprocessing_cache',"
            "'reprocessing_pdf','done','failed')",
        )


def downgrade() -> None:
    with op.batch_alter_table("document_uploads") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_document_uploads_reprocess_status_enum"),
            type_="check",
        )
        batch_op.create_check_constraint(
            op.f("ck_document_uploads_reprocess_status_enum"),
            "reprocess_status IN ('not_started','ingesting','reprocessing_cache',"
            "'reprocessing_pdf','done','failed')",
        )

