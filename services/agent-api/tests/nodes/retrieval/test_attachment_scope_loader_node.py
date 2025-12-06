from __future__ import annotations

from typing import cast

import pytest
from langchain_core.messages import HumanMessage

from models.retrieval import (
    AttachmentReference,
    AttachmentScope,
    AttachmentType,
    NormalizedInput,
    TenantScope,
)
from nodes.retrieval.attachment_scope_loader_node import (
    AttachmentScopeLoaderNode,
    WorkflowRepositoryProtocol,
)
from nodes.retrieval.exceptions import InputNormalizationError
from repositories.conversation_scope_repository import (
    ConversationScopePort,
    DocumentChunkPreview,
    DocumentSummary,
)
from state.agent_state import AgentState, MessageSnapshot


class FakeScopeRepository:
    def __init__(
        self,
        summaries: dict[str, DocumentSummary],
        previews: dict[str, list[DocumentChunkPreview]] | None = None,
    ):
        self._summaries = summaries
        self._previews = previews or {}

    async def hydrate_documents(self, document_ids):
        return {
            doc_id: self._summaries[doc_id] for doc_id in document_ids if doc_id in self._summaries
        }

    async def list_conversation_documents(self, conversation_id: str):
        return []

    async def list_base_documents_for_country(
        self, country_code: str, *, status_allowlist=("active",)
    ):
        return []

    async def ensure_attachment(self, **kwargs):  # pragma: no cover - not used in tests
        raise NotImplementedError

    async def load_document_chunk_previews(
        self,
        document_ids,
        *,
        chunk_types=("text",),
        max_chars_per_doc=1600,
        max_chunks_per_doc=5,
    ):
        return self._previews


class FakeWorkflowRepo:
    def __init__(self, workflows: dict[str, FakeWorkflow]):
        self._workflows = workflows

    async def get(self, workflow_id):
        return self._workflows.get(str(workflow_id))


class FakeWorkflow:
    def __init__(self, workflow_id: str):
        self.id = workflow_id
        self.name = "Troubleshooting"
        self.domain = "ops"
        self.version = "v1"
        self.status = "published"
        self.country_code = "USA"
        self.metadata_ = {"nodes": 10}


@pytest.mark.asyncio
async def test_hydrates_documents_and_workflows():
    summaries = {
        DOC_ID: DocumentSummary(
            document_id=DOC_ID,
            canonical_name="Budget",
            access_scope="user_private",
            country_code="USA",
            language="en",
            status="active",
            tags=["finance"],
            metadata={"auto_attach_enabled": True},
        )
    }
    repo = cast(ConversationScopePort, FakeScopeRepository(summaries))
    workflow_repo = cast(
        WorkflowRepositoryProtocol,
        FakeWorkflowRepo({WORKFLOW_ID: FakeWorkflow(WORKFLOW_ID)}),
    )
    normalized_input = NormalizedInput(
        normalized_prompt="hello",
        raw_prompt="hello",
        language_code="en",
        intent_tags=[],
        tenant_scope=TenantScope(conversation_id="conv-1", thread_id="thr-1"),
        attachment_refs=[
            AttachmentReference(
                asset_type=AttachmentType.DOCUMENT,
                asset_id=DOC_ID,
                document_id=DOC_ID,
                attach_source="user_upload",
                visibility="visible",
                provided_in_request=True,
            ),
            AttachmentReference(
                asset_type=AttachmentType.WORKFLOW,
                asset_id=WORKFLOW_ID,
                workflow_id=WORKFLOW_ID,
                attach_source="user_request",
                provided_in_request=True,
            ),
        ],
        scope_hash="hash",
    )
    state = AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hi"))],
        conversation_id="conv-1",
        normalized_input=normalized_input,
    )
    node = AttachmentScopeLoaderNode(scope_repository=repo, workflow_repository=workflow_repo)

    result = await node(state)
    scope: AttachmentScope = result["attachment_scope"]
    assert scope.documents[0].document_id == DOC_ID
    assert scope.workflows[0].workflow_id == WORKFLOW_ID
    assert scope.warnings == []


@pytest.mark.asyncio
async def test_missing_normalized_input_raises():
    repo = cast(ConversationScopePort, FakeScopeRepository({}))
    state = AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hi"))],
        conversation_id="conv-1",
    )
    node = AttachmentScopeLoaderNode(scope_repository=repo)
    with pytest.raises(InputNormalizationError):
        await node(state)


@pytest.mark.asyncio
async def test_missing_documents_and_workflows_marked():
    repo = cast(ConversationScopePort, FakeScopeRepository({}))
    normalized_input = NormalizedInput(
        normalized_prompt="hello",
        raw_prompt="hello",
        language_code="en",
        intent_tags=[],
        tenant_scope=TenantScope(conversation_id="conv-1", thread_id="thr-1"),
        attachment_refs=[
            AttachmentReference(
                asset_type=AttachmentType.DOCUMENT,
                asset_id=DOC_ID,
                document_id=DOC_ID,
                attach_source="user_upload",
                visibility="visible",
                provided_in_request=True,
            ),
            AttachmentReference(
                asset_type=AttachmentType.WORKFLOW,
                asset_id=MISSING_WORKFLOW_ID,
                workflow_id=MISSING_WORKFLOW_ID,
                attach_source="user_request",
                provided_in_request=True,
            ),
        ],
        scope_hash="hash",
    )
    state = AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hi"))],
        conversation_id="conv-1",
        normalized_input=normalized_input,
    )
    node = AttachmentScopeLoaderNode(
        scope_repository=repo,
        workflow_repository=cast(WorkflowRepositoryProtocol, FakeWorkflowRepo({})),
    )

    result = await node(state)
    scope: AttachmentScope = result["attachment_scope"]
    assert DOC_ID in scope.missing_assets
    assert MISSING_WORKFLOW_ID in scope.missing_assets
    assert len(scope.warnings) == 2


@pytest.mark.asyncio
async def test_includes_chunk_previews():
    summaries = {
        DOC_ID: DocumentSummary(
            document_id=DOC_ID,
            canonical_name="Budget",
            access_scope="user_private",
            country_code="USA",
            language="en",
            status="active",
            tags=["finance"],
            metadata={"document_alias": "DOC_LEDGER"},
        )
    }
    previews = {
        DOC_ID: [
            DocumentChunkPreview(
                document_id=DOC_ID,
                chunk_id="chunk-1",
                text="District 9 received $1.8M in Rapid Relief Pool funds.",
                page_number=1,
                position=0,
            )
        ]
    }
    repo = cast(ConversationScopePort, FakeScopeRepository(summaries, previews))
    normalized_input = NormalizedInput(
        normalized_prompt="hello",
        raw_prompt="hello",
        language_code="en",
        intent_tags=[],
        tenant_scope=TenantScope(conversation_id="conv-1", thread_id="thr-1"),
        attachment_refs=[
            AttachmentReference(
                asset_type=AttachmentType.DOCUMENT,
                asset_id=DOC_ID,
                document_id=DOC_ID,
                attach_source="user_upload",
                visibility="visible",
                provided_in_request=True,
            )
        ],
        scope_hash="hash",
    )
    state = AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hi"))],
        conversation_id="conv-1",
        normalized_input=normalized_input,
    )
    node = AttachmentScopeLoaderNode(scope_repository=repo)

    result = await node(state)
    scope: AttachmentScope = result["attachment_scope"]
    assert scope.documents[0].chunks[0].text.startswith("District 9")


DOC_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
WORKFLOW_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
MISSING_WORKFLOW_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
