from typing import Optional
from uuid import UUID as PyUUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared_data_layer.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class GraphEntity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "graph_entities"

    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # e.g. "Person", "Organization"
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding: Mapped[Optional[Vector]] = mapped_column(
        Vector(512), nullable=True
    )  # Per docs

    # Provenance
    document_id: Mapped[Optional[PyUUID]] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    chunk_id: Mapped[Optional[PyUUID]] = mapped_column(
        ForeignKey("chunks.id"), nullable=True
    )
    algo_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    first_seen_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Metadata
    labels: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    properties: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    score: Mapped[float] = mapped_column(Float, default=1.0)

    # Scope
    country_code: Mapped[Optional[str]] = mapped_column(
        String(2), nullable=True, index=True
    )
    owner_user_id: Mapped[Optional[PyUUID]] = mapped_column(
        nullable=True
    )  # No FK to users

    # Relationships
    # Edges where this entity is source or target
    edges_out = relationship(
        "GraphEdge", foreign_keys="GraphEdge.source_id", back_populates="source"
    )
    edges_in = relationship(
        "GraphEdge", foreign_keys="GraphEdge.target_id", back_populates="target"
    )


class GraphEdge(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "graph_edges"

    source_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("graph_entities.id"), nullable=False
    )
    target_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("graph_entities.id"), nullable=False
    )
    relation: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "WORKS_FOR"
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    evidence_span: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    directional: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    first_seen_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    algo_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    source = relationship(
        "GraphEntity", foreign_keys=[source_id], back_populates="edges_out"
    )
    target = relationship(
        "GraphEntity", foreign_keys=[target_id], back_populates="edges_in"
    )
    evidence = relationship("GraphEvidence", back_populates="edge")


class GraphEvidence(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "graph_evidence"

    edge_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("graph_edges.id"), nullable=False
    )
    chunk_id: Mapped[Optional[PyUUID]] = mapped_column(
        ForeignKey("chunks.id"), nullable=True
    )
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=1.0)

    edge = relationship("GraphEdge", back_populates="evidence")
    chunk = relationship("Chunk")


class GraphCommunity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "graph_communities"

    community_key: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=0)  # Hierarchical level

    entity_ids: Mapped[list[PyUUID]] = mapped_column(ARRAY(PG_UUID), nullable=True)
    metrics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    algo_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class GraphEdgeEvidenceRollup(Base):
    """
    Materialized view for edge evidence aggregation.
    """

    __tablename__ = "graph_edge_evidence_rollup"
    __table_args__ = {"info": {"is_view": True}}

    edge_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("graph_edges.id"), primary_key=True
    )
    evidence_chunk_ids: Mapped[list[PyUUID]] = mapped_column(ARRAY(PG_UUID))
    evidence_count: Mapped[int] = mapped_column(Integer)
    last_refreshed_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True))


class GraphHotEntity(Base):
    """
    Materialized view for hot entities.
    """

    __tablename__ = "graph_hot_entities"
    __table_args__ = {"info": {"is_view": True}}

    id: Mapped[PyUUID] = mapped_column(PG_UUID, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    country_code: Mapped[Optional[str]] = mapped_column(String(2))
    edge_count: Mapped[int] = mapped_column(Integer)
