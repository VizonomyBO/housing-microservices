from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from shared_data_layer.config import SYSTEM_OWNER_SENTINEL
from shared_data_layer.db.models.documents import Document
from shared_data_layer.db.models.retrieval import PillarAnswer
from shared_data_layer.repositories.base import BaseRepository


class PillarAnswerRepository(BaseRepository[PillarAnswer]):
    """Repository helpers for pillar answers and their identity contract."""

    def __init__(self, session):
        super().__init__(session, PillarAnswer)

    async def create_pillar_answer(
        self,
        *,
        owner_user_id: Optional[UUID],
        document_id: UUID,
        country_code: str,
        pillar_name: str,
        content_hash: str,
        summary_markdown: str,
        answer_json: dict,
        status: str,
        score: Optional[float] = None,
        generated_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
    ) -> PillarAnswer:
        document = await self.session.get(Document, document_id)
        if document is None:
            raise ValueError(f"Document {document_id} not found")

        self._validate_owner_scope(document, owner_user_id)

        answer = PillarAnswer(
            owner_user_id=owner_user_id,
            document_id=document_id,
            country_code=country_code,
            pillar_name=pillar_name,
            content_hash=content_hash,
            summary_markdown=summary_markdown,
            answer_json=answer_json,
            status=status,
            score=score,
            generated_at=generated_at,
            expires_at=expires_at,
        )
        self.session.add(answer)
        await self.session.flush()
        await self.session.refresh(answer)
        return answer

    @staticmethod
    def _validate_owner_scope(
        document: Document, owner_user_id: Optional[UUID]
    ) -> None:
        """Ensure non-base pillar answers always carry an owner identity."""

        if document.access_scope == "base":
            return

        if document.owner_user_id in (None, SYSTEM_OWNER_SENTINEL):
            return

        if owner_user_id is None:
            raise ValueError("owner_user_id is required for non-base pillar answers")

        if document.owner_user_id not in (owner_user_id, SYSTEM_OWNER_SENTINEL):
            raise ValueError(
                "owner_user_id must match the document owner for non-base answers"
            )
