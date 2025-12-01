"""High-level orchestration helpers around checkpoint persistence."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from repositories.agent_checkpoint_repository import (
    AgentCheckpointRepository,
    CheckpointSaveOptions,
    HydratedCheckpoint,
)
from state.agent_state import AgentState


class CheckpointService:
    """Thin domain wrapper that encodes LangGraph/HITL semantics."""

    def __init__(self, repository: AgentCheckpointRepository):
        self._repository = repository

    async def save_checkpoint(
        self,
        state: AgentState,
        *,
        checkpoint_type: str,
        step_index: int = 0,
        resume_token: str | None = None,
        hitl_operator_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentState:
        """Store a checkpoint without changing any HITL metadata semantics."""

        options = CheckpointSaveOptions(
            checkpoint_type=checkpoint_type,
            step_index=step_index,
            resume_token=resume_token,
            hitl_operator_id=hitl_operator_id,
            metadata=metadata,
        )
        return await self._repository.save_checkpoint(state, options)

    async def pause_for_hitl(
        self,
        state: AgentState,
        *,
        checkpoint_type: str,
        resume_token: str | None = None,
        hitl_operator_id: str | None = None,
        step_index: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[AgentState, str]:
        """Persist a checkpoint specifically for a HITL pause and return the token."""

        if not state.interrupt_reason:
            raise ValueError("HITL pauses require state.interrupt_reason to be set")

        token = resume_token or uuid4().hex
        merged_metadata = dict(metadata or {})
        merged_metadata.setdefault("resume_kind", "hitl")

        options = CheckpointSaveOptions(
            checkpoint_type=checkpoint_type,
            step_index=step_index,
            resume_token=token,
            hitl_operator_id=hitl_operator_id,
            metadata=merged_metadata,
        )
        persisted = await self._repository.save_checkpoint(state, options)
        return persisted, token

    async def load_latest(
        self,
        conversation_id: str,
        *,
        checkpoint_type: str | None = None,
    ) -> HydratedCheckpoint | None:
        return await self._repository.load_latest(conversation_id, checkpoint_type=checkpoint_type)

    async def load_by_id(
        self,
        conversation_id: str,
        checkpoint_id: str,
    ) -> HydratedCheckpoint | None:
        return await self._repository.load_by_checkpoint_id(conversation_id, checkpoint_id)

    async def resume_from_hitl(self, conversation_id: str, resume_token: str) -> HydratedCheckpoint:
        return await self._repository.resume_from_hitl(conversation_id, resume_token)
