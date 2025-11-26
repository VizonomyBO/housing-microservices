"""add_graph_edges_constraint

Revision ID: 20251126150000
Revises: 20251126143000
Create Date: 2025-11-26 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251126150000"
down_revision: Union[str, None] = "20251126143000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_graph_edges_source_target_relation",
        "graph_edges",
        ["source_id", "target_id", "relation"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_graph_edges_source_target_relation", "graph_edges", type_="unique"
    )
