"""LLM-backed prompt validation helpers for the reduced E2E smoke tests."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, SupportsFloat

from openai import AsyncOpenAI, OpenAIError
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

DEFAULT_JUDGE_MODEL = "gpt-4o-mini"
SYSTEM_PROMPT = (
    "You are a meticulous evaluator for retrieval-augmented answers. "
    "Given a user question, the assistant answer, and the exact documents that were "
    "available, decide whether the answer (a) addresses the user request and "
    "(b) only states facts that can be grounded in the provided documents. "
    "Treat any claim that is not directly supported by the documents as unsupported. "
    "Respond with strict JSON using the schema:\n"
    "{\n"
    '  "addresses_question": true | false,\n'
    '  "grounded_in_documents": true | false,\n'
    '  "unsupported_claims": ["optional narrative strings"],\n'
    '  "score": number between 0 and 1,\n'
    '  "summary": "short explanation"\n'
    "}\n"
    "Only emit JSON—no prose outside the object."
)


@dataclass(slots=True)
class JudgeDocument:
    """Document context passed to the judge."""

    alias: str
    canonical_name: str
    content: str
    description: str | None = None


@dataclass(slots=True)
class JudgeRequest:
    """Structured payload describing the prompt run for LLM judging."""

    prompt_id: str
    question: str
    answer: str
    documents: Sequence[JudgeDocument]
    document_aliases: Sequence[str]
    expected_traits: Sequence[str]
    expected_document_ids: Sequence[str]
    cited_document_ids: Sequence[str]


@dataclass(slots=True)
class JudgeVerdict:
    """Result returned by a prompt judge implementation."""

    passed: bool
    score: float | None = None
    reasons: list[str] = field(default_factory=list)
    raw: str | None = None


class PromptJudge(Protocol):
    """Protocol implemented by prompt judge strategies."""

    name: str

    async def evaluate(self, request: JudgeRequest) -> JudgeVerdict: ...


@dataclass(slots=True)
class LLMPromptJudge(PromptJudge):
    """LLM-backed judge that calls OpenAI's chat completions API."""

    api_key: str
    model: str = DEFAULT_JUDGE_MODEL
    timeout_seconds: float = 30.0
    temperature: float = 0.0
    max_tokens: int = 320
    max_retries: int = 3

    def __post_init__(self) -> None:
        self._client = AsyncOpenAI(api_key=self.api_key, timeout=self.timeout_seconds)

    @property
    def name(self) -> str:  # pragma: no cover - trivial accessor
        return f"llm:{self.model}"

    async def evaluate(self, request: JudgeRequest) -> JudgeVerdict:
        payload = {
            "prompt_id": request.prompt_id,
            "question": request.question,
            "answer": request.answer,
            "document_aliases": list(request.document_aliases),
            "expected_traits": list(request.expected_traits),
            "documents": [
                {
                    "alias": doc.alias,
                    "canonical_name": doc.canonical_name,
                    "description": doc.description,
                    "content": doc.content,
                }
                for doc in request.documents
            ],
            "expected_document_ids": list(request.expected_document_ids),
            "cited_document_ids": list(request.cited_document_ids),
        }
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        ]
        async for attempt in AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
            retry=retry_if_exception_type(OpenAIError),
        ):
            with attempt:
                response = await self._client.chat.completions.create(
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    messages=messages,
                )
                content = (response.choices[0].message.content or "").strip()
                verdict = self._parse_response(content)
                return verdict
        raise RuntimeError("LLM judge failed after retries")  # pragma: no cover - defensive

    def _parse_response(self, content: str) -> JudgeVerdict:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            return JudgeVerdict(
                passed=False,
                reasons=[f"Judge output was not valid JSON: {exc}"],
                raw=content or None,
            )
        addresses = bool(data.get("addresses_question"))
        grounded = bool(
            data.get("grounded_in_documents")
            if "grounded_in_documents" in data
            else data.get("supported_by_documents")
        )
        unsupported_raw = (
            data.get("unsupported_claims") or data.get("issues") or data.get("problems")
        )
        unsupported = _coerce_list(unsupported_raw)
        summary = data.get("summary") or data.get("explanation") or data.get("notes")
        score = _coerce_float(data.get("score"))

        reasons: list[str] = []
        if not addresses:
            reasons.append("Answer does not address the question")
        if not grounded:
            reasons.append("Answer is not grounded in the provided documents")
        reasons.extend(filter(None, unsupported))
        passed = not reasons
        if passed and summary:
            reasons.append(summary)
        return JudgeVerdict(passed=passed, score=score, reasons=reasons, raw=content or None)


def build_prompt_judge_from_env() -> PromptJudge | None:
    """Instantiate the default prompt judge when OpenAI credentials are available."""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    model = (
        os.getenv("REDUCED_E2E_JUDGE_MODEL")
        or os.getenv("OPENAI_CHAT_MODEL")
        or DEFAULT_JUDGE_MODEL
    )
    timeout_env = os.getenv("REDUCED_E2E_JUDGE_TIMEOUT")
    try:
        timeout_seconds = float(timeout_env) if timeout_env else 30.0
    except ValueError:  # pragma: no cover - defensive parsing
        timeout_seconds = 30.0
    return LLMPromptJudge(api_key=api_key, model=model, timeout_seconds=timeout_seconds)


def _coerce_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:  # pragma: no cover - defensive parsing
            return None
    if isinstance(value, SupportsFloat):
        try:
            return float(value)
        except TypeError:  # pragma: no cover - defensive parsing
            return None
    return None


__all__ = [
    "JudgeDocument",
    "JudgeRequest",
    "JudgeVerdict",
    "LLMPromptJudge",
    "PromptJudge",
    "build_prompt_judge_from_env",
]
