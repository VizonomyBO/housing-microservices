from __future__ import annotations

import os
from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import yaml
from pydantic import BaseModel, Field, model_validator


class MetricName(str, Enum):
    """Supported metric identifiers for eval scenarios."""

    FAITHFULNESS = "faithfulness"
    ANSWER_RELEVANCE = "answer_relevance"
    CONTEXT_PRECISION = "context_precision"
    CONTEXT_RECALL = "context_recall"
    CITATION_COVERAGE = "citation_coverage"
    TOXICITY = "toxicity"
    LATENCY = "latency"


class MetricSpec(BaseModel):
    """Configuration for a single metric invocation."""

    name: MetricName
    threshold: float | None = Field(
        default=None,
        description="Minimum passing score for the metric (0-1 for similarity metrics).",
    )
    judge: str | None = Field(
        default=None,
        description="Optional override for the judge model (defaults to gpt-5.1).",
    )
    weight: float = Field(default=1.0, ge=0.0)
    timeout_seconds: float | None = Field(default=None, ge=0.0)


class DocRef(BaseModel):
    """Reference to an existing document already ingested in the system."""

    document_id: str
    version_id: str | None = None
    title: str | None = None
    content_path: str | None = Field(
        default=None,
        description="Optional local file containing the document content for metrics.",
    )

    @model_validator(mode="after")
    def _coerce_document_id(self) -> DocRef:
        self.document_id = str(self.document_id)
        return self

    def as_attachment(self) -> dict[str, Any]:
        return {
            "type": "document_reference",
            "document_id": self.document_id,
            "version_id": self.version_id,
            "visibility": "read_only",
            "attach_source": "eval_harness",
            "role": "reference",
        }


class Turn(BaseModel):
    """Single conversational turn."""

    role: Literal["user", "assistant"]
    content: str
    attachments: list[DocRef] = Field(default_factory=list)

    def as_message_payload(self) -> dict[str, Any]:
        if self.role != "user":
            raise ValueError("Eval harness only sends user turns to /v1/chat")
        return {
            "type": "user",
            "content": self.content,
            "attachments": [doc.as_attachment() for doc in self.attachments],
        }


class Expectation(BaseModel):
    """Expected behavior for a scenario."""

    label: str
    rubric: str
    expected_answer: str | None = None
    citations_required: bool = False


class EvalRunConfig(BaseModel):
    """Defaults for how an eval should be executed."""

    judge_model_default: str = Field(
        default_factory=lambda: os.environ.get("EVAL_JUDGE_MODEL", "gpt-5.1"),
        description="Used for gating metrics (defaults to gpt-5.1 unless overridden).",
    )
    judge_model_local: str = Field(
        default_factory=lambda: os.environ.get("EVAL_JUDGE_MODEL", "gpt-5.1"),
        description="Used for local iterations; matches judge_model_default.",
    )
    base_url: str | None = Field(
        default_factory=lambda: os.environ.get("EVAL_BASE_URL") or os.environ.get("AGENT_BASE_URL"),
        description="Target Agent API base URL.",
    )
    auth_shared_secret: str | None = Field(
        default_factory=lambda: os.environ.get("EVAL_AUTH_SECRET")
        or os.environ.get("AUTH_SHARED_SECRET"),
        description="HS256 secret for minting access tokens.",
    )
    user_id: str = Field(
        default_factory=lambda: os.environ.get("EVAL_USER_ID")
        or "11111111-2222-3333-4444-555555555555"
    )
    allow_stateless: bool = True
    response_mode: Literal["blocking", "stream"] = "blocking"
    tenant_id: str | None = None
    workspace_id: str | None = None


class EvalScenario(BaseModel):
    """Complete eval scenario definition loaded from YAML."""

    name: str
    description: str | None = None
    dataset: str | None = None
    turns: list[Turn]
    expectations: list[Expectation]
    metrics: list[MetricSpec] = Field(default_factory=list)
    doc_refs: list[DocRef] = Field(default_factory=list)
    run_config: EvalRunConfig = Field(default_factory=EvalRunConfig)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_turns(self) -> EvalScenario:
        if not self.turns:
            raise ValueError("At least one turn is required")
        if self.turns[-1].role != "user":
            raise ValueError("Last turn must be a user prompt for /v1/chat")
        return self

    def attachments_for_message(self) -> list[dict[str, Any]]:
        """Merge shared doc refs with the final user turn attachments."""

        merged: list[DocRef] = []
        merged.extend(self.doc_refs)
        merged.extend(self.turns[-1].attachments)
        seen: set[str] = set()
        attachments: list[dict[str, Any]] = []
        for doc in merged:
            if doc.document_id in seen:
                continue
            seen.add(doc.document_id)
            attachments.append(doc.as_attachment())
        return attachments

    def to_chat_payload(self) -> dict[str, Any]:
        """Render the scenario into a POST /v1/chat payload."""

        message_turn = self.turns[-1]
        thread_id = None if self.run_config.allow_stateless else str(uuid4())
        payload = {
            "thread_id": thread_id,
            "session_id": self.run_config.workspace_id,
            "allow_stateless": bool(self.run_config.allow_stateless),
            "response_mode": self.run_config.response_mode,
            "message": {
                **message_turn.as_message_payload(),
                "attachments": self.attachments_for_message(),
            },
            "hints": {"dataset": self.dataset, "tags": self.tags},
            "prompt_overrides": {},
            "constraints": {"auto_attach_base_docs": False},
        }
        return payload

    def document_contexts(self) -> list[str]:
        """Load document contents from local paths for metric evaluation."""

        contexts: list[str] = []
        for ref in self.doc_refs:
            if ref.content_path:
                path = Path(ref.content_path)
                if not path.is_absolute():
                    path = Path(__file__).resolve().parents[2] / path
                if path.exists():
                    contexts.append(path.read_text())
        return contexts


def load_scenarios(path: str | Path) -> list[EvalScenario]:
    """Load scenario YAML from disk."""

    location = Path(path)
    if not location.is_absolute():
        location = Path(__file__).resolve().parents[1] / location
    data = yaml.safe_load(location.read_text())
    raw_scenarios: Iterable[dict[str, Any]] = data.get("scenarios", [])
    return [EvalScenario.model_validate(item) for item in raw_scenarios]
