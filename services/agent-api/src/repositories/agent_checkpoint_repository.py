"""Repository adapter for persisting LangGraph checkpoints via the shared data layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from shared_data_layer.db.models.conversations import AgentStateCheckpoint, Message
from shared_data_layer.db.models.documents import ConversationDocument, Document
from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from state.agent_state import (
    AgentState,
    MessageSnapshot,
    agent_state_from_persistence,
    agent_state_to_persistence,
)


@dataclass(slots=True)
class CheckpointSaveOptions:
    """Options controlling how a checkpoint row is stored."""

    checkpoint_type: str
    step_index: int = 0
    resume_token: str | None = None
    hitl_operator_id: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class ConversationDocumentView:
    """Visible conversation attachment that downstream nodes may need."""

    document_id: str
    attach_source: str
    role: str
    visibility: str
    canonical_name: str | None
    access_scope: str
    country_code: str | None
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class CheckpointMetadata:
    """HITL / resume metadata extracted from the checkpoint row."""

    resume_token: str | None = None
    hitl_operator_id: str | None = None
    status: str = "active"
    resumed_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    consumed_resume_token: str | None = None


@dataclass(slots=True)
class HydratedCheckpoint:
    """Checkpoint row plus hydrated LangGraph state and attachment context."""

    checkpoint_id: str
    state: AgentState
    documents: list[ConversationDocumentView]
    metadata: CheckpointMetadata


class AgentCheckpointRepository:
    """Adapter around shared data layer tables for checkpoint persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save_checkpoint(
        self,
        state: AgentState,
        options: CheckpointSaveOptions,
    ) -> AgentState:
        """Persist the serialized AgentState payload and return the updated state."""

        metadata = dict(options.metadata or {})
        if options.resume_token:
            metadata["resume_token"] = options.resume_token
            metadata.setdefault("resume_status", "paused")
        else:
            metadata.setdefault("resume_status", "active")
        if options.hitl_operator_id:
            metadata["hitl_operator_id"] = options.hitl_operator_id
        if state.interrupt_reason:
            metadata.setdefault("interrupt_reason", state.interrupt_reason)

        payload = agent_state_to_persistence(state)
        row = AgentStateCheckpoint(
            conversation_id=_as_uuid(state.conversation_id),
            checkpoint_type=options.checkpoint_type,
            step_index=options.step_index,
            state=payload,
            metadata_=metadata or None,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)

        # Align identifiers/timestamps with the row that was just committed.
        state_with_ids = state.model_copy(
            deep=True,
            update={
                "checkpoint_id": str(row.id),
                "created_at": row.created_at or state.created_at,
            },
        )
        return state_with_ids

    async def load_latest(
        self,
        conversation_id: UUID | str,
        *,
        checkpoint_type: str | None = None,
    ) -> HydratedCheckpoint | None:
        """Return the most recent checkpoint for a conversation (optionally filtered by type)."""

        stmt = (
            select(AgentStateCheckpoint)
            .where(AgentStateCheckpoint.conversation_id == _as_uuid(conversation_id))
            .order_by(AgentStateCheckpoint.created_at.desc())
            .limit(1)
        )
        if checkpoint_type:
            stmt = stmt.where(AgentStateCheckpoint.checkpoint_type == checkpoint_type)

        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return await self._hydrate_checkpoint(row)

    async def load_by_checkpoint_id(
        self,
        conversation_id: UUID | str,
        checkpoint_id: UUID | str,
    ) -> HydratedCheckpoint | None:
        """Load a specific checkpoint row if it belongs to the conversation."""

        stmt = select(AgentStateCheckpoint).where(
            AgentStateCheckpoint.conversation_id == _as_uuid(conversation_id),
            AgentStateCheckpoint.id == _as_uuid(checkpoint_id),
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return await self._hydrate_checkpoint(row)

    async def resume_from_hitl(
        self,
        conversation_id: UUID | str,
        resume_token: str,
    ) -> HydratedCheckpoint:
        """Claim a paused checkpoint by resume token and mark it as resumed."""

        metadata_expr = AgentStateCheckpoint.metadata_
        stmt = (
            select(AgentStateCheckpoint)
            .where(AgentStateCheckpoint.conversation_id == _as_uuid(conversation_id))
            .where(metadata_expr.isnot(None))
            .where(metadata_expr["resume_token"].astext == resume_token)
            .order_by(AgentStateCheckpoint.created_at.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise LookupError("No HITL checkpoint found for resume token")

        consumed = (row.metadata_ or {}).get("resume_token")
        updated_metadata = dict(row.metadata_ or {})
        updated_metadata["resume_token"] = None
        updated_metadata["resume_status"] = "resumed"
        updated_metadata["resumed_at"] = datetime.now(UTC).isoformat()
        row.metadata_ = updated_metadata
        await self._session.flush()

        hydrated = await self._hydrate_checkpoint(row)
        hydrated.metadata.consumed_resume_token = consumed
        return hydrated

    async def _hydrate_checkpoint(self, row: AgentStateCheckpoint) -> HydratedCheckpoint:
        payload = dict(row.state or {})
        payload.setdefault("conversation_id", str(row.conversation_id))
        payload["checkpoint_id"] = str(row.id)
        state = agent_state_from_persistence(payload)

        messages = await self._load_messages(row.conversation_id)
        if messages:
            state = state.model_copy(deep=True, update={"messages": messages})

        documents = await self._load_visible_documents(row.conversation_id)
        metadata = self._parse_metadata(row.metadata_)
        return HydratedCheckpoint(
            checkpoint_id=str(row.id),
            state=state,
            documents=documents,
            metadata=metadata,
        )

    async def _load_messages(self, conversation_id: UUID) -> list[MessageSnapshot]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.ordinal.asc(), Message.created_at.asc(), Message.id.asc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        snapshots: list[MessageSnapshot] = []
        for row in rows:
            lc_message = self._message_from_row(row)
            snapshots.append(
                MessageSnapshot(
                    message=lc_message,
                    stored_at=row.created_at or datetime.now(UTC),
                    metadata={
                        "message_id": str(row.id),
                        "ordinal": row.ordinal,
                        "role": row.role,
                        "status": row.status,
                    },
                )
            )
        return snapshots

    async def _load_visible_documents(
        self, conversation_id: UUID
    ) -> list[ConversationDocumentView]:
        stmt = (
            select(
                ConversationDocument.document_id,
                ConversationDocument.attach_source,
                ConversationDocument.role,
                ConversationDocument.visibility_override,
                Document.canonical_name,
                Document.access_scope,
                Document.country_code,
                Document.metadata_,
            )
            .join(Document, Document.id == ConversationDocument.document_id)
            .where(ConversationDocument.conversation_id == conversation_id)
            .where(ConversationDocument.deleted_at.is_(None))
        )
        visible_status = func.coalesce(ConversationDocument.visibility_override, literal("visible"))
        stmt = stmt.where(visible_status != "hidden")
        rows = await self._session.execute(stmt)
        documents: list[ConversationDocumentView] = []
        for row in rows:
            documents.append(
                ConversationDocumentView(
                    document_id=str(row.document_id),
                    attach_source=row.attach_source,
                    role=row.role,
                    visibility=row.visibility_override or "visible",
                    canonical_name=row.canonical_name,
                    access_scope=row.access_scope,
                    country_code=row.country_code,
                    metadata=row.metadata_,
                )
            )
        return documents

    def _parse_metadata(self, metadata: dict[str, Any] | None) -> CheckpointMetadata:
        data: dict[str, Any] = dict(metadata or {})
        resumed_at_raw = data.get("resumed_at")
        resumed_at: datetime | None
        if isinstance(resumed_at_raw, datetime):
            resumed_at = resumed_at_raw
        elif isinstance(resumed_at_raw, str):
            try:
                resumed_at = datetime.fromisoformat(resumed_at_raw)
            except ValueError:
                resumed_at = None
        else:
            resumed_at = None
        return CheckpointMetadata(
            resume_token=data.get("resume_token"),
            hitl_operator_id=data.get("hitl_operator_id"),
            status=data.get("resume_status", "active"),
            resumed_at=resumed_at,
            raw=data,
        )

    def _message_from_row(self, row: Message) -> BaseMessage:
        content = _normalize_message_content(row.content)
        base_kwargs: dict[str, Any] = {
            "content": content,
            "id": str(row.id),
        }
        additional = dict(row.metadata_ or {})
        if additional:
            base_kwargs["additional_kwargs"] = additional

        role_map = {
            "user": HumanMessage,
            "assistant": AIMessage,
            "system": SystemMessage,
            "tool": ToolMessage,
        }
        cls = role_map.get(row.role, HumanMessage)
        if cls is ToolMessage:
            tool_call_id = additional.get("tool_call_id") if additional else None
            if tool_call_id:
                base_kwargs["tool_call_id"] = tool_call_id
            name = additional.get("name") if additional else None
            if name:
                base_kwargs["name"] = name
        return cls(**base_kwargs)


def _normalize_message_content(content: Any) -> Any:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return content
    if isinstance(content, dict):
        if "text" in content and len(content) == 1:
            return content["text"]
        if "content" in content:
            return content["content"]
    if content is None:
        return ""
    return str(content)


def _as_uuid(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))
