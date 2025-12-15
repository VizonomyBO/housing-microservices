from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class GraphRefreshSettings:
    """Knobs controlling GraphRetriever refresh + query bounds."""

    ttl_seconds: int = 900
    max_entities: int = 8
    max_relations: int = 12
    max_relation_hops: int = 2
    require_document_overlap: bool = False


@dataclass(slots=True)
class GraphSummarySettings:
    """Token budgeting parameters for GraphSummarizer."""

    max_total_tokens: int = 400
    max_entity_tokens: int = 240
    max_relation_tokens: int = 160
    fallback_headline: str = "Graph context unavailable"
    entity_section_title: str = "Key entities"
    relation_section_title: str = "Key relations"
