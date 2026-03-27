from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID as PyUUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    and_,
    func,
    or_,
)
from sqlalchemy.dialects.postgresql import ARRAY, INT4RANGE, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared_data_layer.config import SYSTEM_OWNER_SENTINEL
from shared_data_layer.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from shared_data_layer.db.models.conversations import Conversation
    from shared_data_layer.db.models.retrieval import Chunk


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "documents"

    owner_user_id: Mapped[Optional[PyUUID]] = mapped_column(nullable=True)
    access_scope: Mapped[str] = mapped_column(String, nullable=False)
    canonical_name: Mapped[str] = mapped_column(String, nullable=False)
    country_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    ingestion_stage: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ingestion_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ingestion_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    source_uri: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    byte_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    visibility: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    managed_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    active_chat_refs: Mapped[int] = mapped_column(default=0, nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    artifacts: Mapped[list["Artifact"]] = relationship(
        "Artifact", back_populates="document", cascade="all, delete-orphan"
    )
    ingestion_jobs: Mapped[list["IngestionJob"]] = relationship(
        "IngestionJob", back_populates="document", cascade="all, delete-orphan"
    )
    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk", back_populates="document", cascade="all, delete-orphan"
    )
    gc_events: Mapped[list["DocumentGCEvent"]] = relationship(
        "DocumentGCEvent", back_populates="document", cascade="all, delete-orphan"
    )
    uploaded_files: Mapped[list["UploadedFile"]] = relationship(
        "UploadedFile", back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "access_scope <> 'base' "
            "OR owner_user_id IS NULL "
            f"OR owner_user_id = '{SYSTEM_OWNER_SENTINEL}'::uuid",
            name="ck_documents_base_owner_nullable",
        ),
        CheckConstraint(
            "access_scope <> 'base' OR country_code IS NOT NULL",
            name="ck_documents_base_country_required",
        ),
        CheckConstraint(
            "country_code IS NULL OR country_code ~ '^[A-Z]{3}$'",
            name="ck_documents_country_code_format",
        ),
        CheckConstraint(
            "status IN ('registered','ingesting','active','failed','archived')",
            name="ck_documents_status_enum",
        ),
        CheckConstraint(
            "access_scope IN ('base','user_private','user_shared')",
            name="ck_documents_access_scope_enum",
        ),
        CheckConstraint(
            "ingestion_stage IS NULL OR ingestion_stage IN "
            "('preflight','convert','chunk','embed','index','activate')",
            name="ck_documents_ingestion_stage_enum",
        ),
        CheckConstraint(
            "active_chat_refs >= 0", name="ck_documents_active_refs_non_negative"
        ),
    )


class IngestionJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ingestion_jobs"

    document_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    attempt: Mapped[int] = mapped_column(default=0)
    worker: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_error: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    trace_id: Mapped[Optional[PyUUID]] = mapped_column(nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    document: Mapped["Document"] = relationship(
        "Document", back_populates="ingestion_jobs"
    )

    __table_args__ = (
        CheckConstraint(
            "stage IN ('preflight','convert','chunk','embed','index','activate')",
            name="ck_ingestion_jobs_stage_enum",
        ),
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed','canceled')",
            name="ck_ingestion_jobs_status_enum",
        ),
    )


class Artifact(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "artifacts"

    document_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String, nullable=False)
    s3_uri: Mapped[str] = mapped_column(String, nullable=False)
    byte_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    page_range: Mapped[Optional[tuple[int, int]]] = mapped_column(
        INT4RANGE, nullable=True
    )
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="artifacts")

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "artifact_type",
            name="uq_artifacts_document_type",
        ),
    )


class ConversationDocument(Base, TimestampMixin):
    __tablename__ = "conversation_documents"

    conversation_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    attached_by_user_id: Mapped[Optional[PyUUID]] = mapped_column(nullable=True)
    attach_source: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    visibility_override: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="documents"
    )
    document: Mapped["Document"] = relationship("Document")

    __table_args__ = (
        PrimaryKeyConstraint(
            "conversation_id", "document_id", name="pk_conversation_documents"
        ),
    )


class BaseDocumentByCountry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Logical representation of the partitioned cache for base documents.
    """

    __tablename__ = "base_documents_by_country"

    document_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    country_code: Mapped[str] = mapped_column(
        String(3), nullable=False, primary_key=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)

    document: Mapped["Document"] = relationship("Document")

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "country_code",
            name="uq_base_documents_by_country_document_id",
        ),
    )


class DocumentGCEvent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "document_gc_events"

    document_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    prev_active_chat_refs: Mapped[Optional[int]] = mapped_column(nullable=True)
    new_active_chat_refs: Mapped[Optional[int]] = mapped_column(nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped["Document"] = relationship("Document", back_populates="gc_events")


class UploadedFile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "uploaded_files"

    owner_user_id: Mapped[Optional[PyUUID]] = mapped_column(nullable=True)
    document_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    storage_uri: Mapped[str] = mapped_column(String, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    checksum: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ingestion_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    document: Mapped["Document"] = relationship(
        "Document", back_populates="uploaded_files"
    )
    __table_args__ = (
        CheckConstraint(
            "byte_size >= 0", name="ck_uploaded_files_byte_size_non_negative"
        ),
    )


class DocumentUpload(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "document_uploads"

    country_code: Mapped[str] = mapped_column(String(3), nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    storage_uri: Mapped[str] = mapped_column(String, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    uploaded_by: Mapped[PyUUID] = mapped_column(nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_by: Mapped[Optional[PyUUID]] = mapped_column(nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    document_id: Mapped[Optional[PyUUID]] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    reprocess_status: Mapped[str] = mapped_column(
        String, nullable=False, default="not_started"
    )
    reprocess_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reprocess_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reprocess_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    document: Mapped[Optional["Document"]] = relationship("Document")

    __table_args__ = (
        CheckConstraint(
            "country_code ~ '^[A-Z]{3}$'",
            name="ck_document_uploads_country_code_format",
        ),
        CheckConstraint(
            "byte_size >= 0",
            name="ck_document_uploads_byte_size_non_negative",
        ),
        CheckConstraint(
            "reprocess_status IN ('not_started','queued','ingesting','reprocessing_cache',"
            "'reprocessing_pdf','done','failed')",
            name="ck_document_uploads_reprocess_status_enum",
        ),
    )


Index(
    "ix_documents_status_updated_at",
    Document.status,
    Document.updated_at,
)

Index(
    "ix_documents_scope_country",
    Document.access_scope,
    Document.country_code,
)

Index(
    "uq_documents_owner_content_hash_active",
    Document.owner_user_id,
    Document.content_hash,
    unique=True,
    postgresql_where=and_(
        Document.owner_user_id.isnot(None),
        Document.deleted_at.is_(None),
    ),
)

Index(
    "uq_documents_base_country_hash",
    Document.country_code,
    Document.content_hash,
    unique=True,
    postgresql_where=and_(
        or_(
            Document.owner_user_id.is_(None),
            Document.owner_user_id == SYSTEM_OWNER_SENTINEL,
        ),
        Document.access_scope == "base",
        Document.deleted_at.is_(None),
    ),
)

Index(
    "uq_documents_owner_canonical_name_active",
    Document.owner_user_id,
    func.lower(Document.canonical_name),
    unique=True,
    postgresql_where=and_(
        Document.owner_user_id.isnot(None),
        Document.deleted_at.is_(None),
        Document.access_scope != "base",
    ),
)

Index(
    "ix_ingestion_jobs_document_stage",
    IngestionJob.document_id,
    IngestionJob.stage,
)

Index(
    "ix_ingestion_jobs_status_filter",
    IngestionJob.status,
    postgresql_where=IngestionJob.status.in_(["pending", "failed"]),
)

Index(
    "ix_artifacts_metadata_gin",
    Artifact.metadata_,
    postgresql_using="gin",
)

Index(
    "ix_conversation_documents_document_id",
    ConversationDocument.document_id,
)

Index(
    "ix_conversation_documents_attach_source",
    ConversationDocument.attach_source,
)

Index(
    "ix_uploaded_files_document_id",
    UploadedFile.document_id,
)

Index(
    "ix_uploaded_files_owner_user_id",
    UploadedFile.owner_user_id,
)

Index(
    "uq_uploaded_files_owner_content_hash",
    UploadedFile.owner_user_id,
    UploadedFile.content_hash,
    unique=True,
    postgresql_where=UploadedFile.owner_user_id.isnot(None),
)

Index(
    "ix_document_uploads_country_code",
    DocumentUpload.country_code,
)

Index(
    "ix_document_uploads_verified_reprocess_status",
    DocumentUpload.verified,
    DocumentUpload.reprocess_status,
)

Index(
    "ix_document_uploads_document_id",
    DocumentUpload.document_id,
)
