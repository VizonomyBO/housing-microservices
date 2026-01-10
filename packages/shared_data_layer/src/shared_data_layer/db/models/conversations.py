from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from uuid import UUID as PyUUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared_data_layer.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from shared_data_layer.db.models.agents import AgentRun
    from shared_data_layer.db.models.documents import ConversationDocument
    from shared_data_layer.db.models.retrieval import Chunk


class Conversation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "conversations"

    owner_user_id: Mapped[Optional[PyUUID]] = mapped_column(nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    status: Mapped[str] = mapped_column(String, default="active", nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    document_scope: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, doc="Cached scope for routing hints"
    )
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )
    documents: Mapped[list["ConversationDocument"]] = relationship(
        "ConversationDocument",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    checkpoints: Mapped[list["AgentStateCheckpoint"]] = relationship(
        "AgentStateCheckpoint",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    agent_runs: Mapped[list["AgentRun"]] = relationship(
        "AgentRun",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active','archived','deleted')",
            name="ck_conversations_status_enum",
        ),
    )


class Message(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "messages"

    conversation_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String, default="final", nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )
    tool_calls: Mapped[list["MessageToolCall"]] = relationship(
        "MessageToolCall", back_populates="message", cascade="all, delete-orphan"
    )
    citations: Mapped[list["MessageCitation"]] = relationship(
        "MessageCitation", back_populates="message", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('system','user','assistant','tool')",
            name="ck_messages_role_enum",
        ),
    )


class MessageToolCall(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "message_tool_calls"

    message_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    call_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    arguments: Mapped[dict] = mapped_column(JSONB, nullable=False)
    response: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)

    message: Mapped["Message"] = relationship("Message", back_populates="tool_calls")

    __table_args__ = (
        UniqueConstraint(
            "message_id",
            "tool_name",
            "call_index",
            name="uq_message_tool_calls_unique_invocation",
        ),
    )


class MessageCitation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "message_citations"

    message_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[PyUUID] = mapped_column(nullable=False)
    chunk_country_code: Mapped[str] = mapped_column(String(3), nullable=False)
    snippet: Mapped[str] = mapped_column(String, nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    message: Mapped["Message"] = relationship("Message", back_populates="citations")
    chunk: Mapped["Chunk"] = relationship("Chunk")

    __table_args__ = (
        ForeignKeyConstraint(
            ["chunk_id", "chunk_country_code"],
            ["chunks.id", "chunks.country_code"],
            ondelete="RESTRICT",
            name="fk_message_citations_chunk",
        ),
    )


class AgentStateCheckpoint(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_state_checkpoints"

    conversation_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    checkpoint_type: Mapped[str] = mapped_column(String, nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="checkpoints"
    )


Index(
    "ix_messages_conversation_ordinal",
    Message.conversation_id,
    Message.ordinal,
)

Index(
    "ix_message_tool_calls_message",
    MessageToolCall.message_id,
)

Index(
    "ix_message_citations_chunk",
    MessageCitation.chunk_id,
    MessageCitation.chunk_country_code,
)


class ChatResponseCache(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Cache for chat responses to pillar questions by country."""

    __tablename__ = "chat_response_cache"

    country_code: Mapped[str] = mapped_column(String(3), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    question_hash: Mapped[str] = mapped_column(String, nullable=False)
    response: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "country_code",
            "question_hash",
            name="uq_chat_response_cache_country_hash",
        ),
    )
