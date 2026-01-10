from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import field_validator

from .common import ORMBaseSchema
from .countries import CountryISOAlpha3, Region


class WorkflowNodeRead(ORMBaseSchema):
    id: UUID
    node_key: str
    type: str
    level: str
    path: str
    config: Dict[str, Any]
    description: Optional[str] = None
    preconditions: Optional[Dict[str, Any]] = None
    tool_hints: Optional[List[str]] = None
    artifacts: Optional[Dict[str, Any]] = None

    @field_validator("path", mode="before")
    @classmethod
    def convert_ltree(cls, value):
        if value is not None:
            return str(value)
        return value


class WorkflowEdgeRead(ORMBaseSchema):
    id: UUID
    source_node_id: UUID
    target_node_id: UUID
    transition_type: str
    condition: Optional[str] = None
    confidence: Optional[float] = None
    metadata_: Optional[dict] = None


class WorkflowVersionRead(ORMBaseSchema):
    id: UUID
    from_version: Optional[str] = None
    to_version: Optional[str] = None
    definition: Dict[str, Any]
    change_log: Optional[Dict[str, Any]] = None
    approved_by: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    nodes: List[WorkflowNodeRead] = []
    edges: List[WorkflowEdgeRead] = []


class WorkflowGraphRead(ORMBaseSchema):
    id: UUID
    name: str
    description: Optional[str] = None
    domain: str
    country_code: Optional[Union[CountryISOAlpha3, Region]] = None
    status: str
    version: str
    max_depth: int
    metadata_: Optional[dict] = None
    published_at: Optional[datetime] = None
    versions: List[WorkflowVersionRead] = []
