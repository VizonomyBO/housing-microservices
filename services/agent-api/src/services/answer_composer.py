"""Answer composer implementations backing AnswerSynthesizer nodes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from agent_api.reduced_scope import ReducedScopeFlags
from cache.response_serializer import CacheCitation
from models.retrieval import AttachmentDocument, AttachmentScope
from services.model_clients import OpenAIChatClientProtocol
from subgraphs.informational.answer_synthesizer_node import (
    AnswerComposerProtocol,
    AnswerSynthesisContext,
    AnswerSynthesisResult,
)


@dataclass(slots=True)
class OpenAIAnswerComposer(AnswerComposerProtocol):
    """LLM-backed composer with reduced-scope fallback."""

    client: OpenAIChatClientProtocol | None
    temperature: float = 0.2
    max_output_tokens: int = 400

    async def compose(self, context: AnswerSynthesisContext) -> AnswerSynthesisResult:
        flags: ReducedScopeFlags | None = context.reduced_scope_flags
        if self.client is None or (flags and not flags.use_real_tools):
            return self._fallback_response(context)

        prompt = self._build_prompt(context)
        messages = self._messages(prompt)
        text = await self.client.complete(
            messages,
            temperature=self.temperature,
            max_tokens=self.max_output_tokens,
        )
        citations = self._default_citations(context.attachment_scope)
        chunk_ids = [citation.chunk_id for citation in citations]
        metadata = {
            "model": "openai",
            "temperature": self.temperature,
            "mode": "reduced_scope_real_tools",
        }
        return AnswerSynthesisResult(
            answer_text=text,
            citations=citations,
            chunk_ids=chunk_ids,
            model_metadata=metadata,
            quality_score=None,
        )

    def _fallback_response(self, context: AnswerSynthesisContext) -> AnswerSynthesisResult:
        summary = context.graph_summary.headline if context.graph_summary else None
        answer_lines = [
            "Text-only mode is active, so the assistant can only summarize uploaded documents.",
            context.normalized_prompt,
        ]
        if summary:
            answer_lines.append(f"Context summary: {summary}")
        answer = "\n\n".join(answer_lines)
        metadata = {"mode": "text_only"}
        return AnswerSynthesisResult(
            answer_text=answer,
            citations=[],
            chunk_ids=[],
            model_metadata=metadata,
            quality_score=0.1,
        )

    def _build_prompt(self, context: AnswerSynthesisContext) -> str:
        instructions = [
            "You are a housing policy analyst.",
            "Use only the reference excerpts to answer the question.",
            "Quote concrete figures and cite the document alias in square brackets (e.g., [DOC_POLICY]).",
            "If a detail is missing from the references, say so explicitly instead of guessing.",
        ]
        sections: list[str] = ["\n".join(instructions)]
        if context.graph_summary and context.graph_summary.sections:
            for section in context.graph_summary.sections:
                sections.append(f"## {section.title}\n{section.body}")
        attachment_overview = self._attachment_overview(context.attachment_scope)
        prompt_parts = [
            "You are Viz agent. Answer in markdown with concise paragraphs.",
            f"Question: {context.normalized_prompt}",
        ]
        if sections:
            prompt_parts.append("Graph Summary:\n" + "\n\n".join(sections))
        if attachment_overview:
            prompt_parts.append("References:\n" + attachment_overview)
        return "\n\n".join(prompt_parts)

    def _messages(self, prompt: str) -> Sequence[dict[str, str]]:
        return [
            {"role": "system", "content": "You are a helpful analyst."},
            {"role": "user", "content": prompt},
        ]

    def _attachment_overview(self, scope: AttachmentScope | None) -> str:
        if scope is None or not scope.documents:
            return ""
        sections: list[str] = []
        for doc in scope.documents:
            alias = self._document_alias(doc)
            header = f"### {alias} — {doc.canonical_name or doc.document_id}"
            chunk_lines = []
            for chunk in doc.chunks:
                snippet = chunk.text.strip()
                if not snippet:
                    continue
                prefix = f"[chunk {chunk.position if chunk.position is not None else 0}]"
                chunk_lines.append(f"{prefix} {snippet}")
            if not chunk_lines:
                continue
            sections.append(f"{header}\n" + "\n\n".join(chunk_lines))
        return "\n\n".join(sections)

    def _document_alias(self, doc: AttachmentDocument) -> str:
        metadata = doc.metadata or {}
        return metadata.get("document_alias") or doc.canonical_name or doc.document_id

    def _default_citations(self, scope: AttachmentScope | None) -> list[CacheCitation]:
        if scope is None:
            return []
        citations: list[CacheCitation] = []
        for doc in scope.documents:
            alias = self._document_alias(doc)
            if doc.chunks:
                chunk = doc.chunks[0]
                chunk_id = chunk.chunk_id
                snippet = chunk.text[:300]
                page = chunk.page_number
            else:
                chunk_id = doc.document_id
                snippet = f"See document {alias}"
                page = None
            citations.append(
                CacheCitation(
                    doc_id=doc.document_id,
                    chunk_id=chunk_id,
                    snippet=snippet,
                    metadata={
                        "document_alias": alias,
                        "page": page,
                    },
                )
            )
        return citations


__all__ = ["OpenAIAnswerComposer"]
