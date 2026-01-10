"""add chat response cache

Revision ID: 40072d62267b
Revises: 01407cccd473
Create Date: 2026-01-09 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "40072d62267b"
down_revision: Union[str, None] = "01407cccd473"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_response_cache",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("country_code", sa.String(length=3), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("question_hash", sa.String(), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "country_code",
            "question_hash",
            name="uq_chat_response_cache_country_hash",
        ),
    )


def downgrade() -> None:
    op.drop_table("chat_response_cache")
