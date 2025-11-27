from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID as PyUUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared_data_layer.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from shared_data_layer.db.models.conversations import Conversation


class AgentRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_runs"

    owner_user_id: Mapped[Optional[PyUUID]] = mapped_column(nullable=True)
    conversation_id: Mapped[Optional[PyUUID]] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    country_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    planner_name: Mapped[str] = mapped_column(String, nullable=False)
    planner_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="running",
    )
    document_scope: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    input_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    conversation: Mapped[Optional["Conversation"]] = relationship(
        "Conversation", back_populates="agent_runs"
    )
    events: Mapped[list["AgentEvent"]] = relationship(
        "AgentEvent",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AgentEvent.sequence_index",
    )

    __table_args__ = (
        CheckConstraint(
            "country_code IS NULL OR country_code ~ '^[A-Z]{3}$'",
            name="ck_agent_runs_country_code_format",
        ),
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed','canceled')",
            name="ck_agent_runs_status_enum",
        ),
    )


class AgentEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_events"

    run_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    owner_user_id: Mapped[Optional[PyUUID]] = mapped_column(nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    sequence_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    error_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    run: Mapped["AgentRun"] = relationship("AgentRun", back_populates="events")

    __table_args__ = (
        CheckConstraint(
            "country_code IS NULL OR country_code ~ '^[A-Z]{3}$'",
            name="ck_agent_events_country_code_format",
        ),
        CheckConstraint(
            "sequence_index >= 0",
            name="ck_agent_events_sequence_non_negative",
        ),
    )


Index(
    "ix_agent_runs_owner_created_at",
    AgentRun.owner_user_id,
    AgentRun.created_at,
)

Index(
    "ix_agent_runs_conversation_created_at",
    AgentRun.conversation_id,
    AgentRun.created_at,
)

Index(
    "ix_agent_runs_country_code_created_at",
    AgentRun.country_code,
    AgentRun.created_at,
)

Index(
    "ix_agent_events_run_sequence",
    AgentEvent.run_id,
    AgentEvent.sequence_index,
)

Index(
    "ix_agent_events_owner_created_at",
    AgentEvent.owner_user_id,
    AgentEvent.created_at,
)
