from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from shared_data_layer.db.models.documents import Document

from agent_api.agent.runner import ChatRunResult
from agent_api.services.reports import ReportService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session():
    return AsyncMock()


@pytest.fixture
def mock_runner():
    runner = MagicMock()
    runner.run_chat = AsyncMock(
        return_value=ChatRunResult(
            done_payload={"answer": "## Mocked content for section"}, messages=[], tool_calls=[]
        )
    )
    return runner


@pytest.fixture
def mock_auth_context():
    auth = MagicMock()
    auth.user_id = "test-user-id"
    auth.tenant_id = "test-tenant-id"
    return auth


@pytest.fixture
def mock_request_context():
    req = MagicMock()
    req.request_id = "test-req-id"
    return req


async def test_generate_housing_report_logic(
    mock_db_session,
    mock_runner,
    mock_auth_context,
    mock_request_context,
):
    # Mock DocumentRepository and ConversationService
    with (
        patch("agent_api.services.reports.DocumentRepository") as mock_doc_repo,
        patch("agent_api.services.reports.ConversationService") as mock_convo_service,
    ):
        # Setup DB mocks
        doc_repo = mock_doc_repo.return_value
        convo_service = mock_convo_service.return_value

        # Mock list_documents_for_country
        mock_doc = MagicMock(spec=Document)
        mock_doc.id = "doc-123"
        doc_repo.list_documents_for_country = AsyncMock(return_value=[mock_doc])

        # Mock ensure_conversation
        mock_convo = MagicMock()
        mock_convo.id = "convo-123"
        convo_service.ensure_conversation = AsyncMock(return_value=mock_convo)

        # Mock attach_to_conversation
        doc_repo.attach_to_conversation = AsyncMock()

        # Initialize Service
        settings = MagicMock()
        settings.s3_housing_pdf_bucket = None
        service = ReportService(mock_db_session, mock_runner, settings)

        # Run method
        pdf_bytes = await service.generate_housing_report(
            country_code="USA",
            user_id="test-user-id",
            request_context=mock_request_context,
            auth_context=mock_auth_context,
        )

        # Assertions
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        assert b"%PDF" in pdf_bytes

        # Verify interactions
        doc_repo.list_documents_for_country.assert_called_once_with("USA")
        convo_service.ensure_conversation.assert_called_once()
        doc_repo.attach_to_conversation.assert_called_once()

        # Verify runner called 11 times (once per section)
        assert mock_runner.run_chat.call_count == 11

        # Check first call arguments to ensure context is correct
        first_call = mock_runner.run_chat.call_args_list[0]
        _, kwargs = first_call
        assert kwargs["request"].conversation_id == "convo-123"
        assert kwargs["request"].hints["country_code"] == "USA"
