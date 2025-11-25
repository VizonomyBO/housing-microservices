from typing import Optional
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared_data_layer.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class GraphEntity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "graph_entities"

    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String, nullable=False) # e.g. "Person", "Organization"
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Scope
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True, index=True)
    owner_user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Relationships
    owner = relationship("User")
    # Edges where this entity is source or target
    edges_out = relationship("GraphEdge", foreign_keys="GraphEdge.source_id", back_populates="source")
    edges_in = relationship("GraphEdge", foreign_keys="GraphEdge.target_id", back_populates="target")


class GraphEdge(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "graph_edges"

    source_id: Mapped[UUID] = mapped_column(ForeignKey("graph_entities.id"), nullable=False)
    target_id: Mapped[UUID] = mapped_column(ForeignKey("graph_entities.id"), nullable=False)
    relation: Mapped[str] = mapped_column(String, nullable=False) # e.g. "WORKS_FOR"
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    
    source = relationship("GraphEntity", foreign_keys=[source_id], back_populates="edges_out")
    target = relationship("GraphEntity", foreign_keys=[target_id], back_populates="edges_in")
    evidence = relationship("GraphEvidence", back_populates="edge")


class GraphEvidence(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "graph_evidence"

    edge_id: Mapped[UUID] = mapped_column(ForeignKey("graph_edges.id"), nullable=False)
    chunk_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("chunks.id"), nullable=True)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=1.0)

    edge = relationship("GraphEdge", back_populates="evidence")
    chunk = relationship("Chunk")


class GraphCommunity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "graph_communities"

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=0) # Hierarchical level
    
    # We might want a many-to-many with entities, but for now let's keep it simple or follow specific design if detailed.
    # The prompt didn't specify exact fields for community, so this is a reasonable start.
