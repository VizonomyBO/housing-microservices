"""GraphSummarizer LangGraph node."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from nodes.retrieval.graph.config import GraphSummarySettings
from state.agent_state import AgentState, GraphSummary, GraphSummarySection


def _estimate_tokens(text: str) -> int:
    # Rough heuristic: ~4 characters per token.
    return max(1, len(text) // 4)


@dataclass(slots=True)
class GraphSummarizerNode:
    """Deterministically compresses graph context into prompt-ready sections."""

    settings: GraphSummarySettings = field(default_factory=GraphSummarySettings)
    token_estimator: Callable[[str], int] = field(default=_estimate_tokens)

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        graph_context = state.graph_context
        if not graph_context or (not graph_context.clusters and not graph_context.relations):
            summary = self._fallback_summary(graph_context)
            return {"graph_summary": summary}

        entity_section = self._build_entity_section(graph_context)
        relation_section = self._build_relation_section(graph_context)
        sections = [
            section for section in [entity_section, relation_section] if section and section.body
        ]
        total_tokens = sum(section.tokens for section in sections)
        sections, total_tokens = self._enforce_budget(sections, total_tokens)
        if not sections:
            summary = self._fallback_summary(graph_context)
            return {"graph_summary": summary}

        headline = self._build_headline(graph_context)
        summary = GraphSummary(
            headline=headline,
            sections=sections,
            total_tokens=total_tokens,
            budget_tokens=self.settings.max_total_tokens,
            fallback_used=False,
            scope_hash=graph_context.scope_hash,
        )
        return {"graph_summary": summary}

    def _build_entity_section(self, graph_context) -> GraphSummarySection | None:
        if not graph_context.clusters:
            return None
        lines: list[str] = []
        tokens = 0
        sorted_entities = sorted(
            graph_context.clusters,
            key=lambda entity: (
                -(entity.score if entity.score is not None else 0.0),
                entity.hot_rank or 0,
                entity.label,
            ),
        )
        for entity in sorted_entities:
            line = self._format_entity_line(entity)
            line_tokens = self.token_estimator(line)
            if tokens + line_tokens > self.settings.max_entity_tokens:
                break
            tokens += line_tokens
            lines.append(line)
        if not lines:
            return None
        body = "\n".join(lines)
        return GraphSummarySection(
            title=self.settings.entity_section_title,
            body=body,
            tokens=tokens,
        )

    def _build_relation_section(self, graph_context) -> GraphSummarySection | None:
        if not graph_context.relations:
            return None
        lines: list[str] = []
        tokens = 0

        def _relation_key(relation):
            seen_at = relation.last_refreshed_at.timestamp() if relation.last_refreshed_at else 0.0
            return (seen_at, relation.weight or 0.0, relation.relation_type)

        sorted_relations = sorted(graph_context.relations, key=_relation_key, reverse=True)
        for relation in sorted_relations:
            line = self._format_relation_line(relation)
            line_tokens = self.token_estimator(line)
            if tokens + line_tokens > self.settings.max_relation_tokens:
                break
            tokens += line_tokens
            lines.append(line)
        if not lines:
            return None
        body = "\n".join(lines)
        return GraphSummarySection(
            title=self.settings.relation_section_title,
            body=body,
            tokens=tokens,
        )

    def _enforce_budget(
        self,
        sections: list[GraphSummarySection],
        total_tokens: int,
    ) -> tuple[list[GraphSummarySection], int]:
        if total_tokens <= self.settings.max_total_tokens:
            return sections, total_tokens
        trimmed = list(sections)
        tokens = total_tokens
        while trimmed and tokens > self.settings.max_total_tokens:
            removed = trimmed.pop()
            tokens -= removed.tokens
        return trimmed, tokens

    def _fallback_summary(self, graph_context) -> GraphSummary:
        return GraphSummary(
            headline=self.settings.fallback_headline,
            sections=[],
            total_tokens=0,
            budget_tokens=self.settings.max_total_tokens,
            fallback_used=True,
            scope_hash=getattr(graph_context, "scope_hash", None),
        )

    def _build_headline(self, graph_context) -> str:
        entity_count = len(graph_context.clusters)
        relation_count = len(graph_context.relations)
        return f"{entity_count} entities linked via {relation_count} relations"

    def _format_entity_line(self, entity) -> str:
        sources = ",".join(entity.document_ids) if entity.document_ids else "unknown sources"
        summary = entity.summary or "No summary available"
        return f"- {entity.label}: {summary} (sources: {sources})"

    def _format_relation_line(self, relation) -> str:
        chunks = (
            ",".join(relation.evidence_chunk_ids)
            if relation.evidence_chunk_ids
            else "unknown evidence"
        )
        return (
            f"- {relation.source_entity_id} -> {relation.target_entity_id} "
            f"[{relation.relation_type}] ({chunks})"
        )
