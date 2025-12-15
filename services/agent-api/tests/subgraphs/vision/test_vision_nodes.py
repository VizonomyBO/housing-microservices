from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from cache import CacheCitation, CacheWriter, InMemoryValkeyClient
from models.retrieval import AttachmentDocument, AttachmentScope, NormalizedInput, TenantScope
from state.agent_state import AgentState, CacheMetadata, MessageSnapshot, VisionFinding
from subgraphs.vision.image_reasoner_node import (
    ImageReasonerNode,
    VisionAnalysisContext,
    VisionAnalysisResult,
    VisionAnalyzerProtocol,
)
from subgraphs.vision.multimodal_responder_node import (
    MultimodalResponderNode,
    VisionResponseComposer,
    VisionResponseContext,
    VisionResponseResult,
)
from subgraphs.vision.vision_router_node import VisionRouterNode


def _normalized_input(prompt: str) -> NormalizedInput:
    return NormalizedInput(
        normalized_prompt=prompt,
        raw_prompt=prompt,
        tenant_scope=TenantScope(conversation_id="conv-vision", thread_id="thr-vision"),
        attachment_refs=[],
        scope_hash="scope-vision",
    )


def _vision_document(
    *, document_id: str, caption: str | None, mime_type: str, **metadata
) -> AttachmentDocument:
    meta = {"mime_type": mime_type, "image_caption": caption}
    meta.update(metadata)
    return AttachmentDocument(
        document_id=document_id,
        canonical_name=metadata.get("canonical_name"),
        access_scope="user_private",
        metadata=meta,
    )


def _base_state(prompt: str, *, documents: list[AttachmentDocument]) -> AgentState:
    return AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="please review"))],
        conversation_id="conv-vision",
        normalized_input=_normalized_input(prompt),
        attachment_scope=AttachmentScope(documents=documents),
        cache_metadata=CacheMetadata(cache_key="vision-cache"),
    )


class StubAnalyzer(VisionAnalyzerProtocol):
    def __init__(self) -> None:
        self.contexts: list[VisionAnalysisContext] = []

    async def analyze(self, context: VisionAnalysisContext) -> VisionAnalysisResult:  # type: ignore[override]
        self.contexts.append(context)
        return VisionAnalysisResult(
            findings=[
                VisionFinding(
                    chunk_id="chunk-img",
                    figure_id="fig-1",
                    summary="Detected structural damage",
                    confidence=0.91,
                    model="stub-vision",
                )
            ],
            warnings=[],
            guardrail_violations=[],
            model_metadata={"model": "stub-vision"},
        )


class StubComposer(VisionResponseComposer):
    def __init__(self) -> None:
        self.contexts: list[VisionResponseContext] = []

    async def compose(self, context: VisionResponseContext) -> VisionResponseResult:  # type: ignore[override]
        self.contexts.append(context)
        citation = CacheCitation(doc_id="doc-1", chunk_id="chunk-img")
        return VisionResponseResult(
            answer_text="Figure fig-1 shows cracks; documentation confirms the same issue.",
            citations=[citation],
            chunk_ids=["chunk-img"],
            quality_score=0.88,
            model_metadata={"model": "vision-synth"},
            attachments=[{"figure_id": "fig-1", "document_id": "doc-1"}],
        )


@pytest.mark.asyncio
async def test_vision_router_marks_image_only_and_warns_on_missing_caption() -> None:
    documents = [
        _vision_document(document_id="doc-1", caption=None, mime_type="image/png"),
    ]
    state = _base_state("", documents=documents)
    router = VisionRouterNode()

    updates = await router(state)
    routed = state.model_copy(update=updates)

    assert routed.vision_context is not None
    assert routed.vision_context.mode == "image_only"
    assert routed.guardrails_passed is True
    assert routed.subgraph_metrics["vision.router.attachments"] == 1
    assert routed.subgraph_metrics["vision.router.warnings"] == 1


@pytest.mark.asyncio
async def test_image_reasoner_uses_captions_and_emits_findings() -> None:
    documents = [
        _vision_document(
            document_id="doc-vision",
            caption="Satellite photo of the site",
            mime_type="image/png",
            figure_id="fig-42",
            image_caption_chunk_id="chunk-vision",
        )
    ]
    state = _base_state("describe this image", documents=documents)
    router = VisionRouterNode()
    analyzer = StubAnalyzer()
    reasoner = ImageReasonerNode(analyzer=analyzer)

    routed = state.model_copy(update=await router(state))
    reasoned = routed.model_copy(update=await reasoner(routed))

    assert len(reasoned.vision_findings) == 1
    assert analyzer.contexts[0].attachments[0].caption == "Satellite photo of the site"
    assert reasoned.subgraph_metrics["vision.reasoner.findings"] == 1


@pytest.mark.asyncio
async def test_multimodal_responder_composes_answer_and_writes_cache() -> None:
    documents = [
        _vision_document(
            document_id="doc-1",
            caption="Damage to beam",
            mime_type="image/png",
            figure_id="fig-1",
            image_caption_chunk_id="chunk-img",
        )
    ]
    state = _base_state("combine with report findings", documents=documents)
    router = VisionRouterNode()
    analyzer = StubAnalyzer()
    reasoner = ImageReasonerNode(analyzer=analyzer)
    composer = StubComposer()
    cache_writer = CacheWriter(client=InMemoryValkeyClient())
    responder = MultimodalResponderNode(composer=composer, cache_writer=cache_writer)

    routed = state.model_copy(update=await router(state))
    reasoned = routed.model_copy(update=await reasoner(routed))
    responded = reasoned.model_copy(update=await responder(reasoned))

    assert responded.answer is not None
    assert responded.answer.startswith("Figure fig-1")
    assert responded.answer_metadata["vision_attachments"][0]["figure_id"] == "fig-1"
    assert responded.cache_metadata.written_at is not None
    assert responded.subgraph_metrics["vision.responder.attachments"] == 1


@pytest.mark.asyncio
async def test_guardrail_violation_routes_to_human_gate() -> None:
    documents = [
        _vision_document(
            document_id="doc-unsafe",
            caption="Sensitive attachment",
            mime_type="image/png",
            content_flags=["violence"],
        )
    ]
    state = _base_state("analyze image", documents=documents)
    router = VisionRouterNode()
    analyzer = StubAnalyzer()
    reasoner = ImageReasonerNode(analyzer=analyzer)
    responder = MultimodalResponderNode(
        composer=StubComposer(),
        cache_writer=CacheWriter(client=InMemoryValkeyClient()),
    )

    routed = state.model_copy(update=await router(state))
    # Guardrails should already fail before responder; ensure reasoner still runs to populate findings.
    reasoned = routed.model_copy(update=await reasoner(routed))
    response = await responder(reasoned)

    assert response["next_subgraph"] == "human_gate"
    assert response["interrupt_reason"] == "guardrail_violation"
