from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_api.agent.runner import ChatRunResult
from agent_api.services import preprocessing as preprocessing_module

pytestmark = pytest.mark.asyncio

_VALID_ANSWER = (
    "This is a sufficiently detailed answer for cache generation that stays well above "
    "the minimum character threshold and cites retrieved evidence inline [c1]."
)


@pytest.fixture
def mock_db_session():
    return AsyncMock()


async def test_preprocess_cache_for_country_continues_after_failed_question(
    monkeypatch,
    mock_db_session,
):
    monkeypatch.setattr(preprocessing_module, "PILLAR_QUESTIONS", {"Test Pillar": ["Q1", "Q2"]})

    runner = MagicMock()
    runner.run_chat = AsyncMock(
        side_effect=[
            ChatRunResult(
                done_payload={
                    "answer": "Too short [c1]",
                    "citations": [{"doc_id": "doc-1"}],
                },
                messages=[],
                tool_calls=[],
            ),
            ChatRunResult(
                done_payload={
                    "answer": "Still short [c1]",
                    "citations": [{"doc_id": "doc-1"}],
                },
                messages=[],
                tool_calls=[],
            ),
            RuntimeError("runner exploded"),
            ChatRunResult(
                done_payload={
                    "answer": _VALID_ANSWER,
                    "citations": [{"doc_id": "doc-1"}],
                },
                messages=[],
                tool_calls=[],
            ),
        ]
    )

    with (
        patch("agent_api.services.preprocessing.ConversationService") as mock_convo_service,
        patch("agent_api.services.preprocessing.DocumentRepository") as mock_doc_repo,
        patch("agent_api.services.preprocessing.ChatCacheService") as mock_cache_service,
    ):
        convo_service = mock_convo_service.return_value
        doc_repo = mock_doc_repo.return_value
        cache_service = mock_cache_service.return_value

        mock_convo = MagicMock()
        mock_convo.id = "convo-123"
        convo_service.ensure_conversation = AsyncMock(return_value=mock_convo)

        mock_doc = MagicMock()
        mock_doc.id = "doc-123"
        doc_repo.list_documents_for_country = AsyncMock(return_value=[mock_doc])
        doc_repo.attach_to_conversation = AsyncMock()

        cache_service.get_cached_response = AsyncMock(return_value=None)
        cache_service.store_response = AsyncMock()

        stats = await preprocessing_module.preprocess_cache_for_country(
            "USA",
            runner,
            mock_db_session,
            force_regenerate=True,
        )

    assert stats["total_questions"] == 2
    assert stats["cache_generated"] == 1
    assert stats["errors"] == 1
    assert stats["failed_questions"] == ["Q1"]
    assert runner.run_chat.call_count == 4
    assert cache_service.store_response.call_count == 1
