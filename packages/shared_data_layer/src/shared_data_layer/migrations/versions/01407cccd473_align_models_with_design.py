"""align_models_with_design

Revision ID: 01407cccd473
Revises: 000000000001
Create Date: 2025-11-26 17:40:55.309654

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "01407cccd473"
down_revision: Union[str, None] = "000000000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("base_documents_by_country") as batch_op:
        batch_op.drop_constraint(
            op.f("uq_base_documents_document"),
            type_="unique",
        )
        batch_op.create_unique_constraint(
            op.f("uq_base_documents_by_country_document_id"),
            ["document_id", "country_code"],
        )


def downgrade() -> None:
    with op.batch_alter_table("base_documents_by_country") as batch_op:
        batch_op.drop_constraint(
            op.f("uq_base_documents_by_country_document_id"),
            type_="unique",
        )
        batch_op.create_unique_constraint(
            op.f("uq_base_documents_document"),
            ["document_id", "country_code"],
        )
