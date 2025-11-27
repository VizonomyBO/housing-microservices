from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from uuid import UUID as PyUUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, INT4RANGE, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared_data_layer.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from shared_data_layer.db.models.retrieval import Chunk


class GraphEntity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "graph_entities"
    __table_args__ = (
        CheckConstraint(
            "(owner_user_id IS NOT NULL) OR country_code IS NOT NULL",
            name="ck_graph_entities_country_or_owner",
        ),
        CheckConstraint(
            "country_code IS NULL OR country_code ~ '^[A-Z]{3}$'",
            name="ck_graph_entities_country_code_format",
        ),
        CheckConstraint(
            "(chunk_id IS NULL AND chunk_country_code IS NULL)"
            " OR (chunk_id IS NOT NULL AND chunk_country_code IS NOT NULL)",
            name="ck_graph_entities_chunk_country_pair",
        ),
        ForeignKeyConstraint(
            ["chunk_id", "chunk_country_code"],
            ["chunks.id", "chunks.country_code"],
            ondelete="SET NULL",
            name="fk_graph_entities_chunk",
        ),
    )

    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_key: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding: Mapped[Optional[Vector]] = mapped_column(Vector(512), nullable=True)
    document_id: Mapped[Optional[PyUUID]] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    chunk_id: Mapped[Optional[PyUUID]] = mapped_column(nullable=True)
    chunk_country_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    algo_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    labels: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    properties: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    owner_user_id: Mapped[Optional[PyUUID]] = mapped_column(nullable=True)

    edges_out: Mapped[list["GraphEdge"]] = relationship(
        "GraphEdge", foreign_keys="GraphEdge.source_entity_id", back_populates="source"
    )
    edges_in: Mapped[list["GraphEdge"]] = relationship(
        "GraphEdge", foreign_keys="GraphEdge.target_entity_id", back_populates="target"
    )


class GraphEdge(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "graph_edges"
    __table_args__ = (
        UniqueConstraint(
            "source_entity_id",
            "target_entity_id",
            "edge_type",
            name="uq_graph_edges_source_target_type",
        ),
    )

    source_entity_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("graph_entities.id", ondelete="CASCADE"), nullable=False
    )
    target_entity_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("graph_entities.id", ondelete="CASCADE"), nullable=False
    )
    edge_type: Mapped[str] = mapped_column(String, nullable=False)
    weight: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), default=1.0)
    directional: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    evidence_span: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    algo_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    source: Mapped["GraphEntity"] = relationship(
        "GraphEntity", foreign_keys=[source_entity_id], back_populates="edges_out"
    )
    target: Mapped["GraphEntity"] = relationship(
        "GraphEntity", foreign_keys=[target_entity_id], back_populates="edges_in"
    )
    evidence: Mapped[list["GraphEvidence"]] = relationship(
        "GraphEvidence", back_populates="edge", cascade="all, delete-orphan"
    )


class GraphEvidence(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "graph_evidence"

    edge_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("graph_edges.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[Optional[PyUUID]] = mapped_column(nullable=True)
    chunk_country_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    offsets: Mapped[Optional[tuple[int, int]]] = mapped_column(INT4RANGE, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    edge: Mapped["GraphEdge"] = relationship("GraphEdge", back_populates="evidence")
    chunk: Mapped[Optional["Chunk"]] = relationship("Chunk")

    __table_args__ = (
        ForeignKeyConstraint(
            ["chunk_id", "chunk_country_code"],
            ["chunks.id", "chunks.country_code"],
            ondelete="SET NULL",
            name="fk_graph_evidence_chunk",
        ),
        CheckConstraint(
            "(chunk_id IS NULL AND chunk_country_code IS NULL)"
            " OR (chunk_id IS NOT NULL AND chunk_country_code IS NOT NULL)",
            name="ck_graph_evidence_chunk_pair",
        ),
    )


class GraphCommunity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "graph_communities"

    community_key: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    level: Mapped[int] = mapped_column(nullable=False, default=0)
    entity_ids: Mapped[Optional[list[PyUUID]]] = mapped_column(
        ARRAY(PG_UUID), nullable=True
    )
    metrics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    algo_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "community_key",
            "algo_version",
            name="uq_graph_communities_key_algo",
        ),
    )


class GraphEdgeEvidenceRollup(Base):
    __tablename__ = "graph_edge_evidence_rollup"
    __table_args__ = {"info": {"is_view": True}}

    edge_id: Mapped[PyUUID] = mapped_column(
        ForeignKey("graph_edges.id"), primary_key=True
    )
    evidence_chunk_ids: Mapped[list[PyUUID]] = mapped_column(ARRAY(PG_UUID))
    evidence_count: Mapped[int] = mapped_column()
    last_refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GraphHotEntity(Base):
    __tablename__ = "graph_hot_entities"
    __table_args__ = {"info": {"is_view": True}}

    id: Mapped[PyUUID] = mapped_column(PG_UUID, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    entity_type: Mapped[str] = mapped_column(String)
    country_code: Mapped[Optional[str]] = mapped_column(String(3))
    edge_count: Mapped[int] = mapped_column()
    hot_rank: Mapped[int] = mapped_column()


Index(
    "ix_graph_entities_name",
    GraphEntity.name,
)

Index(
    "ix_graph_entities_document_id",
    GraphEntity.document_id,
)

Index(
    "ix_graph_entities_labels_gin",
    GraphEntity.labels,
    postgresql_using="gin",
)

Index(
    "ix_graph_entities_embedding_hnsw",
    GraphEntity.embedding,
    postgresql_using="hnsw",
    postgresql_with={"m": 8, "ef_construction": 64},
)

Index(
    "uq_graph_entities_base_scope",
    GraphEntity.entity_type,
    GraphEntity.entity_key,
    GraphEntity.country_code,
    unique=True,
    postgresql_where=GraphEntity.owner_user_id.is_(None),
)

Index(
    "uq_graph_entities_user_scope",
    GraphEntity.entity_type,
    GraphEntity.entity_key,
    GraphEntity.owner_user_id,
    unique=True,
    postgresql_where=GraphEntity.owner_user_id.isnot(None),
)

Index(
    "ix_graph_edges_source_type",
    GraphEdge.source_entity_id,
    GraphEdge.edge_type,
)

Index(
    "ix_graph_edges_target_type",
    GraphEdge.target_entity_id,
    GraphEdge.edge_type,
)

Index(
    "ix_graph_edges_seen_brin",
    GraphEdge.first_seen_at,
    GraphEdge.last_seen_at,
    postgresql_using="brin",
)

Index(
    "ix_graph_communities_country_level",
    GraphCommunity.country_code,
    GraphCommunity.level,
)

Index(
    "ix_graph_communities_entity_ids_gin",
    GraphCommunity.entity_ids,
    postgresql_using="gin",
)
