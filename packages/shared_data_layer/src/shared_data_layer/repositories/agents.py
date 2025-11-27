from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from shared_data_layer.db.models.agents import AgentEvent, AgentRun
from shared_data_layer.db.models.conversations import Conversation
from shared_data_layer.repositories.base import BaseRepository
from shared_data_layer.schemas.agents import (
    AgentEventRead,
    AgentRunRead,
    AgentRunWithEventsRead,
)


class AgentTelemetryRepository(BaseRepository[AgentRun]):
    """Repository for managing agent run and event telemetry."""

    def __init__(self, session):
        super().__init__(session, AgentRun)

    async def create_run(
        self,
        *,
        owner_user_id: Optional[UUID],
        conversation_id: Optional[UUID],
        planner_name: str,
        planner_version: Optional[str] = None,
        status: str = "running",
        document_scope: Optional[dict] = None,
        input_prompt: Optional[str] = None,
        country_code: Optional[str] = None,
        result_summary: Optional[str] = None,
        result_payload: Optional[dict] = None,
        metadata: Optional[dict] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> AgentRun:
        resolved_country = country_code
        if resolved_country is None and conversation_id is not None:
            conversation = await self.session.get(Conversation, conversation_id)
            if conversation and conversation.country_code:
                resolved_country = conversation.country_code

        run = AgentRun(
            owner_user_id=owner_user_id,
            conversation_id=conversation_id,
            country_code=resolved_country,
            planner_name=planner_name,
            planner_version=planner_version,
            status=status,
            document_scope=document_scope,
            input_prompt=input_prompt,
            result_summary=result_summary,
            result_payload=result_payload,
            metadata_=metadata,
            started_at=started_at,
            completed_at=completed_at,
        )
        self.session.add(run)
        await self.session.flush()
        await self.session.refresh(run)
        return run

    async def append_event(
        self,
        *,
        run_id: UUID,
        event_type: str,
        payload: dict,
        owner_user_id: Optional[UUID] = None,
        country_code: Optional[str] = None,
        sequence_index: Optional[int] = None,
        error_payload: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> AgentEvent:
        run = await self.session.get(AgentRun, run_id)
        if run is None:
            raise ValueError(f"AgentRun {run_id} not found")

        resolved_owner = owner_user_id or run.owner_user_id
        resolved_country = country_code or run.country_code

        next_index = sequence_index
        if next_index is None:
            stmt = select(
                func.coalesce(func.max(AgentEvent.sequence_index), -1) + 1
            ).where(AgentEvent.run_id == run_id)
            result = await self.session.execute(stmt)
            next_index = result.scalar_one()

        event = AgentEvent(
            run_id=run_id,
            owner_user_id=resolved_owner,
            country_code=resolved_country,
            event_type=event_type,
            sequence_index=next_index,
            payload=payload,
            error_payload=error_payload,
            metadata_=metadata,
        )
        self.session.add(event)
        await self.session.flush()
        await self.session.refresh(event)
        return event

    async def list_runs(
        self,
        *,
        owner_user_id: Optional[UUID] = None,
        conversation_id: Optional[UUID] = None,
        country_code: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[AgentRunRead]:
        stmt = select(AgentRun).order_by(AgentRun.created_at.desc())
        if owner_user_id is not None:
            stmt = stmt.where(AgentRun.owner_user_id == owner_user_id)
        if conversation_id is not None:
            stmt = stmt.where(AgentRun.conversation_id == conversation_id)
        if country_code is not None:
            stmt = stmt.where(AgentRun.country_code == country_code)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        runs = result.scalars().all()
        return [AgentRunRead.model_validate(run) for run in runs]

    async def get_run_with_events(
        self, run_id: UUID
    ) -> Optional[AgentRunWithEventsRead]:
        stmt = (
            select(AgentRun)
            .where(AgentRun.id == run_id)
            .options(selectinload(AgentRun.events))
        )
        result = await self.session.execute(stmt)
        run = result.unique().scalar_one_or_none()
        if run is None:
            return None
        return AgentRunWithEventsRead.model_validate(run)

    async def list_events_for_run(self, run_id: UUID) -> List[AgentEventRead]:
        stmt = (
            select(AgentEvent)
            .where(AgentEvent.run_id == run_id)
            .order_by(AgentEvent.sequence_index)
        )
        result = await self.session.execute(stmt)
        events = result.scalars().all()
        return [AgentEventRead.model_validate(event) for event in events]

    async def list_events(
        self,
        *,
        owner_user_id: Optional[UUID] = None,
        country_code: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[AgentEventRead]:
        stmt = select(AgentEvent).order_by(AgentEvent.created_at.desc())
        if owner_user_id is not None:
            stmt = stmt.where(AgentEvent.owner_user_id == owner_user_id)
        if country_code is not None:
            stmt = stmt.where(AgentEvent.country_code == country_code)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        events = result.scalars().all()
        return [AgentEventRead.model_validate(event) for event in events]
