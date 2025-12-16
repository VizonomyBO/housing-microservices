from __future__ import annotations

import pytest

from collections.abc import Sequence

from models.retrieval import AttachmentDocument, AttachmentDocumentChunk, AttachmentScope
from services.answer_composer import OpenAIAnswerComposer
from services.model_clients import OpenAIChatClientProtocol, VoyageRerankClientProtocol
from state.agent_state import GraphContext
from subgraphs.informational.answer_synthesizer_node import AnswerSynthesisContext


class _StubChat(OpenAIChatClientProtocol):
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    async def complete(self, messages, *, temperature: float, max_tokens: int) -> str:
        self.calls.append(list(messages))
        if self.responses:
            return self.responses.pop(0)
        return "stub-response"


class _StubReranker(VoyageRerankClientProtocol):
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.calls: list[tuple[str, list[str], int | None]] = []

    async def rerank(
        self, query: str, documents: Sequence[str], *, top_k: int | None = None
    ) -> list[float]:
        self.calls.append((query, list(documents), top_k))
        return self.scores[: len(documents)]


class _FailingReranker(VoyageRerankClientProtocol):
    async def rerank(
        self, query: str, documents: Sequence[str], *, top_k: int | None = None
    ) -> list[float]:
        raise RuntimeError("boom")


def _attachment_scope() -> AttachmentScope:
    doc_a = AttachmentDocument(
        document_id="doc-a",
        access_scope="base",
        chunks=[
            AttachmentDocumentChunk(
                chunk_id="chunk-a",
                text="Policy guardrails and reporting cadence.",
                score=0.8,
            )
        ],
    )
    doc_b = AttachmentDocument(
        document_id="doc-b",
        access_scope="base",
        chunks=[
            AttachmentDocumentChunk(
                chunk_id="chunk-b",
                text="Funding shifted by $1.8M and needs monthly reporting.",
                score=0.8,
            )
        ],
    )
    return AttachmentScope(documents=[doc_a, doc_b])


def _context(scope: AttachmentScope) -> AnswerSynthesisContext:
    return AnswerSynthesisContext(
        normalized_prompt="How did funding change across documents?",
        allowed_document_ids={doc.document_id for doc in scope.documents},
        graph_summary=None,
        graph_context=GraphContext(),
        workflow_plan=None,
        attachment_scope=scope,
        reduced_scope_flags=None,
        chat_history=[],
    )


@pytest.mark.asyncio
async def test_compose_prefers_reranker_signal_and_uses_hyde() -> None:
    chat = _StubChat(responses=["hyde rewrite", "final answer"])
    reranker = _StubReranker(scores=[0.2, 0.9])
    composer = OpenAIAnswerComposer(
        client=chat,
        reranker=reranker,
        max_retrieved_chunks=2,
        rerank_top_k=4,
    )

    scope = _attachment_scope()
    scope.documents[0].chunks[0].score = 0.9
    scope.documents[0].chunks[0].text = "Neutral policy context."
    scope.documents[1].chunks[0].score = 0.1
    scope.documents[1].chunks[0].text = "Neutral funding context."
    context = _context(scope)

    result = await composer.compose(context)

    assert reranker.calls, "reranker should be invoked over hybrid candidates"
    rerank_query, docs, top_k = reranker.calls[0]
    assert "hyde rewrite" in rerank_query
    assert top_k == 2
    doc_labels = {entry.split(":")[0] for entry in docs}
    assert doc_labels == {"doc-a", "doc-b"}
    assert result.citations
    assert result.citations[0].doc_id == "doc-b"
    assert result.chunk_ids[0] == "chunk-b"


@pytest.mark.asyncio
async def test_compose_falls_back_when_reranker_errors() -> None:
    chat = _StubChat(responses=["hyde rewrite", "final answer"])
    reranker = _FailingReranker()
    composer = OpenAIAnswerComposer(
        client=chat,
        reranker=reranker,
        max_retrieved_chunks=2,
    )

    scope = _attachment_scope()
    scope.documents[0].chunks[0].score = 0.95
    scope.documents[0].chunks[0].text = "Plain context."
    scope.documents[1].chunks[0].score = 0.1
    scope.documents[1].chunks[0].text = "Other context."
    context = _context(scope)

    result = await composer.compose(context)

    assert result.citations
    assert result.citations[0].doc_id == "doc-a"


@pytest.mark.asyncio
async def test_fusion_keeps_reporting_and_funding_coverage() -> None:
    chat = _StubChat(responses=["hyde rewrite", "final answer"])
    composer = OpenAIAnswerComposer(
        client=chat,
        reranker=None,
        max_retrieved_chunks=3,
    )

    doc_policy = AttachmentDocument(
        document_id="doc-policy",
        access_scope="base",
        chunks=[
            AttachmentDocumentChunk(
                chunk_id="policy-1",
                text="Policy guardrail for district 9 with eligibility notes.",
                score=0.95,
            ),
            AttachmentDocumentChunk(
                chunk_id="policy-2",
                text="Additional guardrail language and constraints.",
                score=0.9,
            ),
        ],
    )
    doc_reporting = AttachmentDocument(
        document_id="doc-reporting",
        access_scope="base",
        chunks=[
            AttachmentDocumentChunk(
                chunk_id="reporting-1",
                text="Monthly reporting cadence required for all funding.",
                score=0.15,
            )
        ],
    )
    doc_funding = AttachmentDocument(
        document_id="doc-funding",
        access_scope="base",
        chunks=[
            AttachmentDocumentChunk(
                chunk_id="funding-1",
                text="Ledger shows $1.8M funding shift toward district 9.",
                score=0.2,
            )
        ],
    )
    scope = AttachmentScope(documents=[doc_policy, doc_reporting, doc_funding])
    context = AnswerSynthesisContext(
        normalized_prompt="Summarize guardrails with funding shifts and reporting cadence.",
        allowed_document_ids={doc.document_id for doc in scope.documents},
        graph_summary=None,
        graph_context=GraphContext(),
        workflow_plan=None,
        attachment_scope=scope,
        reduced_scope_flags=None,
        chat_history=[],
    )

    result = await composer.compose(context)

    doc_ids = {citation.doc_id for citation in result.citations}
    assert "doc-policy" in doc_ids
    assert "doc-reporting" in doc_ids
    assert "doc-funding" in doc_ids
    # Per-document cap should avoid crowding out coverage.
    assert len([c for c in result.citations if c.doc_id == "doc-policy"]) <= 2
