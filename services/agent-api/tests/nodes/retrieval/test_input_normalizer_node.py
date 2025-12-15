from __future__ import annotations

from typing import cast

import pytest
from langchain_core.messages import HumanMessage

from models.retrieval import (
    AttachmentType,
    ChatConstraints,
    ChatMessagePayload,
    ChatRequestContext,
    IncomingAttachment,
)
from nodes.retrieval.exceptions import AttachmentValidationError
from nodes.retrieval.input_normalizer_node import InputNormalizerNode
from nodes.retrieval.utils.language import StubLanguageDetector
from repositories.conversation_scope_repository import (
    ConversationDocumentRecord,
    ConversationScopePort,
    DocumentSummary,
)
from state.agent_state import AgentState, MessageSnapshot

DOC_ID = "11111111-1111-1111-1111-111111111111"
BASE_DOC_ID = "22222222-2222-2222-2222-222222222222"
MISSING_DOC_ID = "33333333-3333-3333-3333-333333333333"


class FakeScopeRepository:
    def __init__(self, documents: list[ConversationDocumentRecord]):
        self._documents = documents
        self.auto_attached: list[str] = []

    async def list_conversation_documents(self, conversation_id: str):
        return list(self._documents)

    async def list_base_documents_for_country(self, country_code: str):
        return [
            DocumentSummary(
                document_id=BASE_DOC_ID,
                canonical_name="Base Catalog",
                access_scope="base",
                country_code=country_code,
                language="en",
                status="active",
                tags=["baseline"],
                metadata={"auto_attach_enabled": True},
            )
        ]

    async def ensure_attachment(
        self, *, conversation_id: str, document_id: str, attach_source: str, **_
    ):
        record = ConversationDocumentRecord(
            document_id=document_id,
            attach_source=attach_source,
            role="primary",
            visibility="visible",
            canonical_name="Base Catalog",
            access_scope="base",
            country_code="USA",
            metadata={"auto_attach_enabled": True},
        )
        self._documents.append(record)
        self.auto_attached.append(document_id)
        return record

    async def hydrate_documents(self, document_ids):
        return {}


@pytest.mark.asyncio
async def test_normalizes_prompt_and_tags_intent():
    repo = cast(
        ConversationScopePort,
        FakeScopeRepository(
            [
                ConversationDocumentRecord(
                    document_id=DOC_ID,
                    attach_source="user_upload",
                    role="primary",
                    visibility="visible",
                    canonical_name="Budget",
                    access_scope="user_private",
                    country_code="USA",
                    metadata=None,
                )
            ]
        ),
    )
    request = ChatRequestContext(
        conversation_id="conv-1",
        thread_id="thr-1",
        message=ChatMessagePayload(content="  hello   world  ", attachments=[]),
        hints={"route": "informational"},
        constraints=ChatConstraints(country_code="USA"),
    )
    state = AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hi"))],
        conversation_id="conv-1",
    )

    node = InputNormalizerNode(
        request=request,
        scope_repository=repo,
        language_detector=StubLanguageDetector(language_code="en", confidence=0.91),
    )

    result = await node(state)
    normalized = result["normalized_input"]
    assert normalized.normalized_prompt == "hello world"
    assert normalized.language_code == "en"
    assert normalized.intent_tags == ["route:informational"]
    assert normalized.scope_hash
    assert any(ref.document_id == DOC_ID for ref in normalized.attachment_refs)


@pytest.mark.asyncio
async def test_missing_attachment_raises_error():
    repo = cast(ConversationScopePort, FakeScopeRepository([]))
    request = ChatRequestContext(
        conversation_id="conv-1",
        thread_id="thr-1",
        message=ChatMessagePayload(
            content="hello",
            attachments=[IncomingAttachment(type="document_reference", document_id=MISSING_DOC_ID)],
        ),
        constraints=ChatConstraints(country_code="USA"),
    )
    state = AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hi"))],
        conversation_id="conv-1",
    )
    node = InputNormalizerNode(
        request=request,
        scope_repository=repo,
        language_detector=StubLanguageDetector(language_code="en"),
    )

    with pytest.raises(AttachmentValidationError):
        await node(state)


@pytest.mark.asyncio
async def test_auto_attaches_base_documents():
    fake_repo = FakeScopeRepository([])
    repo = cast(ConversationScopePort, fake_repo)
    request = ChatRequestContext(
        conversation_id="conv-1",
        thread_id="thr-1",
        message=ChatMessagePayload(content="hello", attachments=[]),
        constraints=ChatConstraints(country_code="USA", auto_attach_base_docs=True),
    )
    state = AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hi"))],
        conversation_id="conv-1",
    )
    node = InputNormalizerNode(
        request=request,
        scope_repository=repo,
        language_detector=StubLanguageDetector(language_code="en"),
    )

    result = await node(state)
    normalized = result["normalized_input"]
    doc_ids = {
        ref.document_id
        for ref in normalized.attachment_refs
        if ref.asset_type == AttachmentType.DOCUMENT
    }
    assert BASE_DOC_ID in fake_repo.auto_attached
    assert BASE_DOC_ID in doc_ids
    assert any("Auto-attached" in warning for warning in normalized.warnings)
