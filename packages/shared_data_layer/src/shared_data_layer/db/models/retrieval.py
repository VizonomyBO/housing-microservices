from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID as PyUUID
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared_data_layer.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Chunk(Base, TimestampMixin):
    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint(
            "token_count IS NULL OR token_count <= 800",
            name="ck_chunks_token_limit",
        ),
        PrimaryKeyConstraint("id", "country_code", name="pk_chunks"),
    )

    id: Mapped[PyUUID] = mapped_column(default=uuid4, nullable=False)
    document_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_type: Mapped[str] = mapped_column(String, nullable=False, default="text")
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    text_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    schema_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    table_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    section_path: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )
    bbox: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    embedding: Mapped[Optional[Vector]] = mapped_column(Vector(1024), nullable=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    owner_user_id: Mapped[Optional[PyUUID]] = mapped_column(nullable=True)
    country_code: Mapped[str] = mapped_column(String(3), default="UNK", nullable=False)
    artifact_uri: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    text_tsv: Mapped[Optional[str]] = mapped_column(
        "text_tsv",
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(text_content, ''))", persisted=True),
        nullable=True,
    )

    document: Mapped["Document"] = relationship("Document", back_populates="chunks")
    metrics: Mapped[Optional["ChunkMetrics"]] = relationship(
        "ChunkMetrics", back_populates="chunk", uselist=False
    )


class ChunkMetrics(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "chunk_metrics"

    chunk_id: Mapped[PyUUID] = mapped_column(nullable=False)
    chunk_country_code: Mapped[str] = mapped_column(String(3), nullable=False)
    quality_score: Mapped[Optional[float]] = mapped_column(Numeric(3, 2), nullable=True)
    retrieval_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    chunk: Mapped["Chunk"] = relationship("Chunk", back_populates="metrics")

    __table_args__ = (
        ForeignKeyConstraint(
            ["chunk_id", "chunk_country_code"],
            ["chunks.id", "chunks.country_code"],
            ondelete="CASCADE",
            name="fk_chunk_metrics_chunk",
        ),
        UniqueConstraint(
            "chunk_id", "chunk_country_code", name="uq_chunk_metrics_chunk"
        ),
    )


class RetrievalRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "retrieval_runs"

    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    filters: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    document_scope: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    top_k: Mapped[int] = mapped_column(Integer, default=10)

    items: Mapped[list["RetrievalRunItem"]] = relationship(
        "RetrievalRunItem", back_populates="run", cascade="all, delete-orphan"
    )


class RetrievalRunItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "retrieval_run_items"

    run_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("retrieval_runs.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[PyUUID] = mapped_column(nullable=False)
    chunk_country_code: Mapped[str] = mapped_column(String(3), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(6, 5), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)

    run: Mapped["RetrievalRun"] = relationship("RetrievalRun", back_populates="items")
    chunk: Mapped["Chunk"] = relationship("Chunk")

    __table_args__ = (
        ForeignKeyConstraint(
            ["chunk_id", "chunk_country_code"],
            ["chunks.id", "chunks.country_code"],
            ondelete="CASCADE",
            name="fk_retrieval_run_items_chunk",
        ),
    )


class PillarAnswer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "pillar_answers"

    owner_user_id: Mapped[PyUUID] = mapped_column(nullable=False)
    country_code: Mapped[str] = mapped_column(String(3), nullable=False)
    pillar_name: Mapped[str] = mapped_column(String, nullable=False)
    document_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)
    summary_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    answer_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    generated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sources: Mapped[list["PillarAnswerSource"]] = relationship(
        "PillarAnswerSource",
        back_populates="pillar_answer",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','running','published','superseded','rejected')",
            name="ck_pillar_answers_status_enum",
        ),
    )


class PillarAnswerSource(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "pillar_answer_sources"

    pillar_answer_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("pillar_answers.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[PyUUID] = mapped_column(nullable=False)
    chunk_country_code: Mapped[str] = mapped_column(String(3), nullable=False)
    contribution_type: Mapped[str] = mapped_column(String, nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(4, 3), default=1.0, nullable=False)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    pillar_answer: Mapped["PillarAnswer"] = relationship(
        "PillarAnswer", back_populates="sources"
    )
    chunk: Mapped["Chunk"] = relationship("Chunk")

    __table_args__ = (
        ForeignKeyConstraint(
            ["chunk_id", "chunk_country_code"],
            ["chunks.id", "chunks.country_code"],
            ondelete="CASCADE",
            name="fk_pillar_answer_sources_chunk",
        ),
        UniqueConstraint(
            "pillar_answer_id",
            "chunk_id",
            "chunk_country_code",
            name="uq_pillar_answer_sources_pair",
        ),
    )


class ActiveChunk(Base):
    """
    Read-only view representing chunks whose documents are active and not deleted.
    """

    __tablename__ = "active_chunks"
    __table_args__ = {"info": {"is_view": True}}

    id: Mapped[PyUUID] = mapped_column(primary_key=True)
    document_id: Mapped[PyUUID] = mapped_column(ForeignKey("documents.id"))
    chunk_type: Mapped[str] = mapped_column(String)
    country_code: Mapped[Optional[str]] = mapped_column(String(3))
    position: Mapped[int] = mapped_column(Integer)
    text_content: Mapped[Optional[str]] = mapped_column(Text)
    image_caption: Mapped[Optional[str]] = mapped_column(Text)
    section_path: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)
    embedding: Mapped[Optional[Vector]] = mapped_column(Vector(1024))
    content_hash: Mapped[str] = mapped_column(String)


from shared_data_layer.db.models.documents import Document  # noqa: E402  (circular)

Index(
    "ix_chunks_document_position",
    Chunk.document_id,
    Chunk.chunk_type,
    Chunk.position,
)

Index(
    "ix_chunks_text_tsv_gin",
    Chunk.text_tsv,
    postgresql_using="gin",
)

Index(
    "ix_chunks_country_chunk_type",
    Chunk.country_code,
    Chunk.chunk_type,
)

Index(
    "ix_chunks_created_at_brin",
    Chunk.created_at,
    postgresql_using="brin",
)

Index(
    "ix_chunks_updated_at_brin",
    Chunk.updated_at,
    postgresql_using="brin",
)

Index(
    "ix_chunk_metrics_chunk_id",
    ChunkMetrics.chunk_id,
    ChunkMetrics.chunk_country_code,
)

Index(
    "uq_pillar_answers_owner_country_pillar",
    PillarAnswer.owner_user_id,
    PillarAnswer.country_code,
    PillarAnswer.pillar_name,
    unique=True,
    postgresql_where=PillarAnswer.status == "published",
)

Index(
    "ix_pillar_answers_country_pillar",
    PillarAnswer.country_code,
    PillarAnswer.pillar_name,
    postgresql_where=PillarAnswer.status == "published",
)

Index(
    "ix_retrieval_runs_created_at",
    RetrievalRun.created_at,
)

Index(
    "ix_retrieval_runs_document_scope_gin",
    RetrievalRun.document_scope,
    postgresql_using="gin",
)
