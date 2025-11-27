from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared_data_layer.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from shared_data_layer.db.ltree import LtreeType


class WorkflowGraph(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "workflow_graphs"

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    country_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    status: Mapped[str] = mapped_column(String, default="draft", nullable=False)
    version: Mapped[str] = mapped_column(String, default="0.1.0", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_depth: Mapped[int] = mapped_column(default=6, nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    versions: Mapped[list["WorkflowVersion"]] = relationship(
        "WorkflowVersion", back_populates="graph", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "domain", "country_code", "version", name="uq_workflow_graphs_scope_version"
        ),
    )


class WorkflowVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "workflow_versions"

    graph_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_graphs.id", ondelete="CASCADE"), nullable=False
    )
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    from_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    to_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    change_log: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    approved_by: Mapped[Optional[UUID]] = mapped_column(nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    graph: Mapped["WorkflowGraph"] = relationship(
        "WorkflowGraph", back_populates="versions"
    )
    nodes: Mapped[list["WorkflowNode"]] = relationship(
        "WorkflowNode", back_populates="version", cascade="all, delete-orphan"
    )
    edges: Mapped[list["WorkflowEdge"]] = relationship(
        "WorkflowEdge", back_populates="version", cascade="all, delete-orphan"
    )


class WorkflowNode(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "workflow_nodes"

    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="CASCADE"), nullable=False
    )
    node_key: Mapped[str] = mapped_column(String, nullable=False)
    level: Mapped[str] = mapped_column(String, nullable=False, default="coarse")
    path: Mapped[str] = mapped_column(LtreeType, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preconditions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    tool_hints: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )
    artifacts: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    version: Mapped["WorkflowVersion"] = relationship(
        "WorkflowVersion", back_populates="nodes"
    )

    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "node_key",
            name="uq_workflow_nodes_version_node_key",
        ),
    )


class WorkflowEdge(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "workflow_edges"

    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="CASCADE"), nullable=False
    )
    source_node_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_nodes.id", ondelete="CASCADE"), nullable=False
    )
    target_node_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_nodes.id", ondelete="CASCADE"), nullable=False
    )
    transition_type: Mapped[str] = mapped_column(
        Text, default="success", nullable=False
    )
    condition: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), default=1.0)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    version: Mapped["WorkflowVersion"] = relationship(
        "WorkflowVersion", back_populates="edges"
    )
    source: Mapped["WorkflowNode"] = relationship(
        "WorkflowNode", foreign_keys=[source_node_id]
    )
    target: Mapped["WorkflowNode"] = relationship(
        "WorkflowNode", foreign_keys=[target_node_id]
    )


Index(
    "ix_workflow_nodes_version_path",
    WorkflowNode.version_id,
    WorkflowNode.path,
)

Index(
    "ix_workflow_nodes_path_gist",
    WorkflowNode.path,
    postgresql_using="gist",
)

Index(
    "ix_workflow_edges_version_source",
    WorkflowEdge.version_id,
    WorkflowEdge.source_node_id,
)

Index(
    "ix_workflow_edges_version_target",
    WorkflowEdge.version_id,
    WorkflowEdge.target_node_id,
)
