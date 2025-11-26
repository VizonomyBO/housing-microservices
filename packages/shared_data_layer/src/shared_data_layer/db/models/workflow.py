from typing import Optional
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text, JSON, Boolean
from sqlalchemy_utils import LtreeType
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared_data_layer.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WorkflowGraph(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "workflow_graphs"

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    domain: Mapped[str] = mapped_column(String, nullable=False) # e.g. "policy_analysis"
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_depth: Mapped[int] = mapped_column(Integer, default=10)
    
    versions = relationship("WorkflowVersion", back_populates="graph")


class WorkflowVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "workflow_versions"

    graph_id: Mapped[UUID] = mapped_column(ForeignKey("workflow_graphs.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False) # The full graph definition
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)

    graph = relationship("WorkflowGraph", back_populates="versions")
    nodes = relationship("WorkflowNode", back_populates="version")
    edges = relationship("WorkflowEdge", back_populates="version")


class WorkflowNode(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "workflow_nodes"

    version_id: Mapped[UUID] = mapped_column(ForeignKey("workflow_versions.id"), nullable=False)
    node_id: Mapped[str] = mapped_column(String, nullable=False) # The ID within the graph (e.g. "node_1")
    type: Mapped[str] = mapped_column(String, nullable=False) # e.g. "retriever", "llm"
    config: Mapped[dict] = mapped_column(JSON, default={})
    
    # Ltree path for hierarchical execution or organization if needed
    path: Mapped[Optional[LtreeType]] = mapped_column(LtreeType, nullable=True)

    version = relationship("WorkflowVersion", back_populates="nodes")


class WorkflowEdge(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "workflow_edges"

    version_id: Mapped[UUID] = mapped_column(ForeignKey("workflow_versions.id"), nullable=False)
    source_node_id: Mapped[str] = mapped_column(String, nullable=False)
    target_node_id: Mapped[str] = mapped_column(String, nullable=False)
    transition_type: Mapped[str] = mapped_column(String, nullable=False, default="success") # success, failure, clarification, repair
    condition: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    version = relationship("WorkflowVersion", back_populates="edges")
