from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Any

import yaml
from pydantic import BaseModel, Field


class MetricName:
    CITATION_COVERAGE = "citation_coverage"
    CITATION_PRECISION = "citation_precision"
    CITATION_RECALL = "citation_recall"
    RETRIEVAL_RELEVANCE = "retrieval_relevance"
    LLM_GROUNDING = "llm_grounding"
    LLM_TRUTHFULNESS = "llm_truthfulness"
    LLM_BIAS = "llm_bias"


class MetricSpec(BaseModel):
    name: str
    threshold: float | None = None


class Turn(BaseModel):
    role: str = "user"
    content: str
    response_mode: str = "blocking"
    metrics: list[MetricSpec] = Field(default_factory=list)


class EvalScenario(BaseModel):
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    attachments: list[str] = Field(default_factory=list)
    turns: list[Turn]


class DocumentRef(BaseModel):
    document_id: str
    canonical_name: str | None = None
    country_code: str | None = None
    access_scope: str | None = None
    content_hash: str | None = None


class Dataset(BaseModel):
    documents: list[DocumentRef]
    scenarios: list[EvalScenario]


def load_dataset(path: pathlib.Path) -> Dataset:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    documents = [DocumentRef.model_validate(item) for item in payload.get("documents", [])]
    scenarios = [EvalScenario.model_validate(item) for item in payload.get("scenarios", [])]
    return Dataset(documents=documents, scenarios=scenarios)


@dataclass
class ResolvedScenario:
    scenario: EvalScenario
    documents: list[DocumentRef]


def resolve_scenario(dataset: Dataset, scenario: EvalScenario) -> ResolvedScenario:
    document_map = {doc.document_id: doc for doc in dataset.documents}
    resolved: list[DocumentRef] = []
    for doc_id in scenario.attachments:
        if doc_id not in document_map:
            msg = f"Scenario {scenario.name} references unknown document_id {doc_id}"
            raise ValueError(msg)
        resolved.append(document_map[doc_id])
    return ResolvedScenario(scenario=scenario, documents=resolved)
