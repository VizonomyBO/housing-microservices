"""Answer composer implementations backing AnswerSynthesizer nodes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from agent_api.reduced_scope import ReducedScopeFlags
from models.retrieval import AttachmentScope
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
        metadata = {
            "model": "openai",
            "temperature": self.temperature,
            "mode": "reduced_scope_real_tools",
        }
        return AnswerSynthesisResult(
            answer_text=text,
            citations=[],
            chunk_ids=[],
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
        sections: list[str] = []
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
        lines = []
        for doc in scope.documents:
            lines.append(f"- {doc.canonical_name or doc.document_id} ({doc.access_scope})")
        return "\n".join(lines)


__all__ = ["OpenAIAnswerComposer"]
