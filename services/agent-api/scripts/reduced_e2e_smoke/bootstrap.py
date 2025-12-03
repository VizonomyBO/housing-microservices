"""Conversation bootstrap helpers for the smoke workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from shared_data_layer.db.models.conversations import Conversation
from shared_data_layer.db.session import DatabaseSessionManager

from .errors import SmokeError


class ConversationBootstrapper(Protocol):
    async def ensure_conversation(self, *, owner_user_id: str, country_code: str) -> str: ...


@dataclass(slots=True)
class DatabaseConversationBootstrapper:
    """Creates or reuses conversations directly via the shared data layer."""

    database_url: str
    namespace: str = "reduced-e2e"

    def _ensure_session_manager(self) -> None:
        if DatabaseSessionManager._engine is not None:  # type: ignore[attr-defined]
            return
        DatabaseSessionManager.init(self.database_url)

    async def ensure_conversation(self, *, owner_user_id: str, country_code: str) -> str:
        if not self.database_url:
            raise SmokeError("DATABASE_URL is required to bootstrap conversations")
        self._ensure_session_manager()
        try:
            owner_uuid = UUID(str(owner_user_id))
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise SmokeError("owner_user_id must be a valid UUID") from exc
        conversation_id = uuid5(NAMESPACE_URL, f"{self.namespace}-{owner_uuid}")
        async with DatabaseSessionManager.session() as session:
            conversation = await session.get(Conversation, conversation_id)
            if conversation is None:
                conversation = Conversation(
                    id=conversation_id,
                    owner_user_id=owner_uuid,
                    country_code=country_code.upper() if country_code else None,
                    status="active",
                    title="Reduced E2E Smoke Session",
                    metadata_={
                        "scenario": "reduced_e2e",
                        "created_by": "reduced_e2e_smoke_cli",
                    },
                )
                session.add(conversation)
            else:
                conversation.country_code = conversation.country_code or country_code.upper()
            await session.commit()
        return str(conversation_id)


__all__ = ["ConversationBootstrapper", "DatabaseConversationBootstrapper"]
