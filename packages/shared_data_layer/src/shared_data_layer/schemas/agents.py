from datetime import datetime
from typing import List, Optional, Union
from uuid import UUID

from .common import ORMBaseSchema
from .countries import CountryISOAlpha3, Region


class AgentEventRead(ORMBaseSchema):
    id: UUID
    run_id: UUID
    owner_user_id: Optional[UUID] = None
    country_code: Optional[Union[CountryISOAlpha3, Region]] = None
    event_type: str
    sequence_index: int
    payload: dict
    error_payload: Optional[dict] = None
    metadata_: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class AgentRunRead(ORMBaseSchema):
    id: UUID
    owner_user_id: Optional[UUID] = None
    conversation_id: Optional[UUID] = None
    country_code: Optional[Union[CountryISOAlpha3, Region]] = None
    planner_name: str
    planner_version: Optional[str] = None
    status: str
    document_scope: Optional[dict] = None
    input_prompt: Optional[str] = None
    result_summary: Optional[str] = None
    result_payload: Optional[dict] = None
    metadata_: Optional[dict] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class AgentRunWithEventsRead(AgentRunRead):
    events: List[AgentEventRead] = []
