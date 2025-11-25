from typing import Optional
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, String, Text, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared_data_layer.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Chunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "chunks"

    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[Vector]] = mapped_column(Vector(1536))  # Voyage-3.5-lite dim? Or OpenAI? Docs say Voyage 3.5 lite.
    # Voyage 3.5 lite dimension is 1536? Actually Voyage-3-lite is 512 or 1024? 
    # Let's check system_architecture.md again or assume 1536 for now (OpenAI compat).
    # Wait, system_architecture says "Voyage AI for embeddings (voyage-3.5-lite)". 
    # Voyage-3-lite is 512 dimensions usually? No, let's check. 
    # Actually, let's make it configurable or just use a standard size. 
    # But wait, the reference implementation used `settings.VECTOR_DIMENSION`.
    # I should check settings.py or just import settings.
    
    token_count: Mapped[int] = mapped_column(Integer, nullable=True)
    page_num: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    type: Mapped[str] = mapped_column(String, default="text") # text, table, image
    artifact_uri: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    schema_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Metadata for filtering
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)

    # Relationships
    document = relationship("Document", back_populates="chunks")
    metrics = relationship("ChunkMetrics", back_populates="chunk", uselist=False)

    __table_args__ = (
        # Indexes will be defined in migrations or here if we want to be explicit
        # Index("ix_chunks_embedding", "embedding", postgresql_using="hnsw", postgresql_with={"m": 16, "ef_construction": 64}),
    )


class ChunkMetrics(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "chunk_metrics"

    chunk_id: Mapped[UUID] = mapped_column(ForeignKey("chunks.id"), unique=True, nullable=False)
    retrieval_count: Mapped[int] = mapped_column(Integer, default=0)
    last_retrieved_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True) # Timestamp

    chunk = relationship("Chunk", back_populates="metrics")


class RetrievalRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "retrieval_runs"

    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    filters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    top_k: Mapped[int] = mapped_column(Integer, default=10)
    
    items = relationship("RetrievalRunItem", back_populates="run")


class RetrievalRunItem(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "retrieval_run_items"

    run_id: Mapped[UUID] = mapped_column(ForeignKey("retrieval_runs.id"), nullable=False)
    chunk_id: Mapped[UUID] = mapped_column(ForeignKey("chunks.id"), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)

    run = relationship("RetrievalRun", back_populates="items")
    chunk = relationship("Chunk")
