"""Demo reset helpers for reduced-profile cleanup endpoints."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from shared_data_layer.db.models.agents import AgentRun
from shared_data_layer.db.models.conversations import AgentStateCheckpoint, Message
from shared_data_layer.db.models.documents import ConversationDocument, Document
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.conversation_service import ConversationService


@dataclass(slots=True)
class ConversationResetResult:
    conversation_id: str
    detached_documents: int
    deleted_messages: int
    deleted_checkpoints: int
    deleted_agent_runs: int


@dataclass(slots=True)
class DocumentPurgeResult:
    purged_documents: int
    document_ids: list[str]
    content_hashes: list[str]


class DemoResetService:
    """Orchestrates conversation cleanup and user document purges."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._conversation_service = ConversationService(session)

    async def reset_conversation(
        self,
        *,
        conversation_id: str,
        owner_user_id: str,
    ) -> ConversationResetResult:
        record = await self._conversation_service.fetch_conversation(
            conversation_id,
            owner_user_id=owner_user_id,
        )
        conversation_uuid = UUID(record.conversation_id)
        detached = await self._soft_delete_attachments(conversation_uuid)
        deleted_messages = await self._delete_messages(conversation_uuid)
        deleted_checkpoints = await self._delete_checkpoints(conversation_uuid)
        deleted_agent_runs = await self._delete_agent_runs(conversation_uuid)
        return ConversationResetResult(
            conversation_id=str(record.conversation_id),
            detached_documents=detached,
            deleted_messages=deleted_messages,
            deleted_checkpoints=deleted_checkpoints,
            deleted_agent_runs=deleted_agent_runs,
        )

    async def purge_documents(
        self,
        *,
        owner_user_id: str,
        document_aliases: Iterable[str] | None = None,
        content_hashes: Iterable[str] | None = None,
    ) -> DocumentPurgeResult:
        owner_uuid = UUID(owner_user_id)
        aliases = {alias.strip().upper() for alias in (document_aliases or []) if alias}
        hashes = {hash_value for hash_value in (content_hashes or []) if hash_value}
        stmt = (
            select(Document.id, Document.content_hash, Document.metadata_)
            .where(Document.owner_user_id == owner_uuid)
            .where(Document.deleted_at.is_(None))
            .where(Document.access_scope != "base")
        )
        rows = await self._session.execute(stmt)
        records = rows.all()
        matches: list[tuple[UUID, str]] = []
        for document_id, content_hash, metadata in records:
            alias_value = None
            if isinstance(metadata, dict):
                alias_value = metadata.get("document_alias") or metadata.get("alias")
            alias_str = str(alias_value).strip().upper() if alias_value else None
            if not aliases and not hashes:
                matches.append((document_id, content_hash))
                continue
            alias_match = alias_str is not None and alias_str in aliases
            hash_match = content_hash in hashes
            if alias_match or hash_match:
                matches.append((document_id, content_hash))
        if not matches:
            return DocumentPurgeResult(purged_documents=0, document_ids=[], content_hashes=[])
        document_ids = [match[0] for match in matches]
        delete_stmt = delete(Document).where(Document.id.in_(document_ids))
        await self._session.execute(delete_stmt)
        return DocumentPurgeResult(
            purged_documents=len(document_ids),
            document_ids=[str(doc_id) for doc_id in document_ids],
            content_hashes=[match[1] for match in matches],
        )

    async def _soft_delete_attachments(self, conversation_id: UUID) -> int:
        now = datetime.now(UTC)
        stmt = (
            update(ConversationDocument)
            .where(ConversationDocument.conversation_id == conversation_id)
            .where(ConversationDocument.deleted_at.is_(None))
            .values(deleted_at=now)
        )
        result = await self._session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    async def _delete_messages(self, conversation_id: UUID) -> int:
        stmt = delete(Message).where(Message.conversation_id == conversation_id)
        result = await self._session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    async def _delete_checkpoints(self, conversation_id: UUID) -> int:
        stmt = delete(AgentStateCheckpoint).where(
            AgentStateCheckpoint.conversation_id == conversation_id
        )
        result = await self._session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    async def _delete_agent_runs(self, conversation_id: UUID) -> int:
        stmt = delete(AgentRun).where(AgentRun.conversation_id == conversation_id)
        result = await self._session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)


__all__ = [
    "ConversationResetResult",
    "DemoResetService",
    "DocumentPurgeResult",
]
