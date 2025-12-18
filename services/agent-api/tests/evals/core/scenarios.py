from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field


class MetricName:
    CITATION_COVERAGE = "citation_coverage"
    LATENCY_MS = "latency_ms"
    LLM_GROUNDING = "llm_grounding"


class MetricSpec(BaseModel):
    name: str
    threshold: Optional[float] = None


class Turn(BaseModel):
    role: str = "user"
    content: str
    response_mode: str = "blocking"
    metrics: List[MetricSpec] = Field(default_factory=list)


class EvalScenario(BaseModel):
    name: str
    description: str
    tags: List[str] = Field(default_factory=list)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    attachments: List[str] = Field(default_factory=list)
    turns: List[Turn]


class DocumentRef(BaseModel):
    document_id: str
    canonical_name: Optional[str] = None
    country_code: Optional[str] = None
    access_scope: Optional[str] = None
    content_hash: Optional[str] = None


class Dataset(BaseModel):
    documents: List[DocumentRef]
    scenarios: List[EvalScenario]


def load_dataset(path: pathlib.Path) -> Dataset:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    documents = [DocumentRef.model_validate(item) for item in payload.get("documents", [])]
    scenarios = [EvalScenario.model_validate(item) for item in payload.get("scenarios", [])]
    return Dataset(documents=documents, scenarios=scenarios)


@dataclass
class ResolvedScenario:
    scenario: EvalScenario
    documents: List[DocumentRef]


def resolve_scenario(dataset: Dataset, scenario: EvalScenario) -> ResolvedScenario:
    document_map = {doc.document_id: doc for doc in dataset.documents}
    resolved: List[DocumentRef] = []
    for doc_id in scenario.attachments:
        if doc_id not in document_map:
            msg = f"Scenario {scenario.name} references unknown document_id {doc_id}"
            raise ValueError(msg)
        resolved.append(document_map[doc_id])
    return ResolvedScenario(scenario=scenario, documents=resolved)
