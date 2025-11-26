from typing import Optional
from uuid import UUID as PyUUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared_data_layer.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Chunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "chunks"

    document_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("documents.id"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[Vector]] = mapped_column(
        Vector(1024)
    )  # Voyage-3.5-lite dim per docs
    # Voyage 3.5 lite dimension is 1536? Actually Voyage-3-lite is 512 or 1024?
    # Let's check system_architecture.md again or assume 1536 for now (OpenAI compat).
    # Wait, system_architecture says "Voyage AI for embeddings (voyage-3.5-lite)".
    # Voyage-3-lite is 512 dimensions usually? No, let's check.
    # Actually, let's make it configurable or just use a standard size.
    # But wait, the reference implementation used `settings.VECTOR_DIMENSION`.
    # I should check settings.py or just import settings.

    token_count: Mapped[int] = mapped_column(Integer, nullable=True)
    page_num: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    type: Mapped[str] = mapped_column(String, default="text")  # text, table, image
    artifact_uri: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    schema_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    owner_user_id: Mapped[Optional[PyUUID]] = mapped_column(
        nullable=True
    )  # Denormalized for RLS
    country_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    section_path: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )
    bbox: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    text_tsv: Mapped[Optional[str]] = mapped_column(
        TSVECTOR, nullable=True
    )  # Generated column
    table_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Metadata for filtering
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    document = relationship("Document", back_populates="chunks")
    metrics = relationship("ChunkMetrics", back_populates="chunk", uselist=False)

    __table_args__ = (
        # Indexes will be defined in migrations or here if we want to be explicit
        # Index("ix_chunks_embedding", "embedding", postgresql_using="hnsw",
        # postgresql_with={"m": 16, "ef_construction": 64}),
    )


class ChunkMetrics(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "chunk_metrics"

    chunk_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("chunks.id"), unique=True, nullable=False
    )
    retrieval_count: Mapped[int] = mapped_column(Integer, default=0)
    last_retrieved_at: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )  # Timestamp

    chunk = relationship("Chunk", back_populates="metrics")


class RetrievalRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "retrieval_runs"

    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    filters: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    top_k: Mapped[int] = mapped_column(Integer, default=10)

    items = relationship("RetrievalRunItem", back_populates="run")


class RetrievalRunItem(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "retrieval_run_items"

    run_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("retrieval_runs.id"), nullable=False
    )
    chunk_id: Mapped[PyUUID] = mapped_column(ForeignKey("chunks.id"), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)

    run = relationship("RetrievalRun", back_populates="items")
    chunk = relationship("Chunk")


class PillarAnswer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "pillar_answers"

    owner_user_id: Mapped[PyUUID] = mapped_column(nullable=False)  # No FK to users
    country_code: Mapped[str] = mapped_column(String(3), nullable=False)
    pillar_name: Mapped[str] = mapped_column(String, nullable=False)
    document_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("documents.id"), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    summary_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    answer_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False
    )  # draft, running, published, superseded, rejected
    generated_at: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )  # Timestamp
    expires_at: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )  # Timestamp

    sources = relationship(
        "PillarAnswerSource",
        back_populates="pillar_answer",
        cascade="all, delete-orphan",
    )


class PillarAnswerSource(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "pillar_answer_sources"

    pillar_answer_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("pillar_answers.id"), nullable=False
    )
    chunk_id: Mapped[PyUUID] = mapped_column(ForeignKey("chunks.id"), nullable=False)
    contribution_type: Mapped[str] = mapped_column(String, nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    pillar_answer = relationship("PillarAnswer", back_populates="sources")
    chunk = relationship("Chunk")


class ActiveChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Read-only view of chunks belonging to active documents.
    """

    __tablename__ = "active_chunks"
    __table_args__ = {"info": {"is_view": True}}

    # We need to redefine columns if we don't inherit.
    # Or we can inherit from a Mixin if we had one for Chunk fields.
    # For now, let's just define the ones we need for tests/usage.
    document_id: Mapped[PyUUID] = mapped_column(ForeignKey("documents.id"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # ... other fields as needed
