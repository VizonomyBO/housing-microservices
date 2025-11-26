from uuid import UUID
from typing import Optional, List, Dict, Any
from pydantic import field_validator
from datetime import datetime

from .common import ORMBaseSchema


class WorkflowNodeRead(ORMBaseSchema):
    id: UUID
    node_id: str
    type: str
    config: Dict[str, Any]
    path: Optional[str] = None

    @field_validator("path", mode="before")
    @classmethod
    def convert_ltree(cls, v):
        if v is not None:
            return str(v)
        return v


class WorkflowEdgeRead(ORMBaseSchema):
    id: UUID
    source_node_id: str
    target_node_id: str
    condition: Optional[str] = None


class WorkflowVersionRead(ORMBaseSchema):
    id: UUID
    version_number: int
    definition: Dict[str, Any]
    is_published: bool
    nodes: List[WorkflowNodeRead] = []
    edges: List[WorkflowEdgeRead] = []


class WorkflowGraphRead(ORMBaseSchema):
    id: UUID
    name: str
    description: Optional[str] = None
    domain: str
    country_code: Optional[str] = None
    is_active: bool
    versions: List[WorkflowVersionRead] = []
