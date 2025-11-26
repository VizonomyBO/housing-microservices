from typing import Optional
from uuid import UUID as PyUUID

from sqlalchemy import BigInteger, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared_data_layer.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "documents"

    owner_user_id: Mapped[Optional[PyUUID]] = mapped_column(nullable=True) # No FK to users (external)
    access_scope: Mapped[str] = mapped_column(String, nullable=False)  # Enum: base, user_private, user_shared
    canonical_name: Mapped[str] = mapped_column(String, nullable=False)
    country_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)  # Enum: registered, ingesting, active, failed, archived
    ingestion_stage: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    source_uri: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    byte_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    visibility: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    managed_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    active_chat_refs: Mapped[int] = mapped_column(default=0)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    artifacts: Mapped[list["Artifact"]] = relationship("Artifact", back_populates="document", cascade="all, delete-orphan")
    ingestion_jobs: Mapped[list["IngestionJob"]] = relationship("IngestionJob", back_populates="document", cascade="all, delete-orphan")
    chunks: Mapped[list["Chunk"]] = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("owner_user_id", "content_hash", name="uq_documents_owner_content_hash"),
    )


class IngestionJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ingestion_jobs"

    document_id: Mapped[PyUUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    attempt: Mapped[int] = mapped_column(default=0)
    worker: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_error: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    trace_id: Mapped[Optional[PyUUID]] = mapped_column(nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="ingestion_jobs")


class Artifact(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "artifacts"

    document_id: Mapped[PyUUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String, nullable=False)
    s3_uri: Mapped[str] = mapped_column(String, nullable=False)
    byte_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="artifacts")


class ConversationDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "conversation_documents"

    conversation_id: Mapped[str] = mapped_column(String, nullable=False) # FK to conversations table (in another module)
    document_id: Mapped[PyUUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    attached_by_user_id: Mapped[Optional[PyUUID]] = mapped_column(nullable=True) # No FK to users
    attach_source: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    visibility_override: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("conversation_id", "document_id", name="uq_conversation_documents_conv_doc"),
    )

