from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from shared_data_layer.db.models.conversations import Conversation, Message
from shared_data_layer.db.models.documents import ConversationDocument, Document
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.agent_checkpoint_repository import (
    AgentCheckpointRepository,
    CheckpointSaveOptions,
)
from state.agent_state import AgentState, MessageSnapshot

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_save_and_load_latest_round_trip(db_session: AsyncSession) -> None:
    conversation = await _create_conversation(db_session)
    await _create_message(db_session, conversation, role="user", ordinal=0, content="hello world")

    repository = AgentCheckpointRepository(db_session)
    state = AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hello world"))],
        conversation_id=str(conversation.id),
        created_at=datetime.now(UTC),
    )

    saved = await repository.save_checkpoint(
        state,
        CheckpointSaveOptions(checkpoint_type="router", step_index=1),
    )
    assert saved.checkpoint_id is not None

    hydrated = await repository.load_latest(conversation.id)
    assert hydrated is not None
    assert hydrated.state.checkpoint_id == saved.checkpoint_id
    assert hydrated.state.conversation_id == str(conversation.id)
    assert [snap.message.content for snap in hydrated.state.messages] == ["hello world"]


async def test_resume_from_hitl_clears_token(db_session: AsyncSession) -> None:
    conversation = await _create_conversation(db_session)
    await _create_message(
        db_session, conversation, role="assistant", ordinal=0, content="Need clarification"
    )

    repository = AgentCheckpointRepository(db_session)
    state = AgentState(
        messages=[MessageSnapshot(message=AIMessage(content="Need clarification"))],
        conversation_id=str(conversation.id),
        interrupt_reason="awaiting HITL",
        created_at=datetime.now(UTC),
    )

    await repository.save_checkpoint(
        state,
        CheckpointSaveOptions(
            checkpoint_type="human_gate",
            step_index=2,
            resume_token="resume-123",
            hitl_operator_id="operator-7",
            metadata={"foo": "bar"},
        ),
    )

    hydrated = await repository.resume_from_hitl(conversation.id, "resume-123")
    assert hydrated.metadata.resume_token is None
    assert hydrated.metadata.status == "resumed"
    assert hydrated.metadata.consumed_resume_token == "resume-123"
    assert hydrated.metadata.raw["hitl_operator_id"] == "operator-7"
    assert hydrated.metadata.raw["resume_status"] == "resumed"


async def test_visibility_enforcement_filters_hidden_docs(db_session: AsyncSession) -> None:
    conversation = await _create_conversation(db_session)
    visible = await _attach_document(
        db_session, conversation, canonical_name="Visible Doc", visibility_override=None
    )
    await _attach_document(
        db_session, conversation, canonical_name="Hidden Doc", visibility_override="hidden"
    )
    await _create_message(
        db_session, conversation, role="user", ordinal=0, content="Summarize docs"
    )

    repository = AgentCheckpointRepository(db_session)
    state = AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="Summarize docs"))],
        conversation_id=str(conversation.id),
        created_at=datetime.now(UTC),
    )
    await repository.save_checkpoint(state, CheckpointSaveOptions(checkpoint_type="router"))

    hydrated = await repository.load_latest(conversation.id)
    assert hydrated is not None
    assert [doc.document_id for doc in hydrated.documents] == [str(visible.id)]
    assert hydrated.documents[0].visibility == "visible"


async def _create_conversation(session: AsyncSession) -> Conversation:
    conversation = Conversation(
        owner_user_id=uuid4(),
        country_code="USA",
        status="active",
        title="Test convo",
        document_scope={"base": []},
    )
    session.add(conversation)
    await session.flush()
    await session.refresh(conversation)
    return conversation


async def _create_message(
    session: AsyncSession,
    conversation: Conversation,
    *,
    role: str,
    ordinal: int,
    content: str,
) -> Message:
    message = Message(
        conversation_id=conversation.id,
        role=role,
        ordinal=ordinal,
        content=content,
        status="final",
        metadata_={"source": "test"},
    )
    session.add(message)
    await session.flush()
    await session.refresh(message)
    return message


async def _attach_document(
    session: AsyncSession,
    conversation: Conversation,
    *,
    canonical_name: str,
    visibility_override: str | None,
) -> Document:
    document = Document(
        owner_user_id=None,
        access_scope="base",
        canonical_name=canonical_name,
        country_code="USA",
        language="en",
        status="active",
        content_hash=f"hash-{uuid4()}",
        active_chat_refs=0,
    )
    session.add(document)
    await session.flush()
    await session.refresh(document)

    attachment = ConversationDocument(
        conversation_id=conversation.id,
        document_id=document.id,
        attach_source="manual",
        role="primary",
        visibility_override=visibility_override,
    )
    session.add(attachment)
    await session.flush()
    return document
