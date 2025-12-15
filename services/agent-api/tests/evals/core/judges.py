from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class JudgeModel(str, Enum):
    """Supported judge models."""

    GPT_5_1_REASONING = "gpt-5.1-reasoning-medium"
    GPT_4O_MINI = "gpt-4o-mini"
    CLAUDE_3_5 = "claude-3-5-sonnet-latest"
    OFFLINE_STUB = "offline-stub"


@dataclass(slots=True)
class JudgeDecision:
    """Result of a judge evaluation."""

    model: str
    score: float
    reasoning: str
    raw: dict[str, Any] | None = None

    def passed(self, threshold: float | None) -> bool:
        if threshold is None:
            return True
        return self.score >= threshold


class JudgeCache:
    """Simple in-memory cache to avoid repeated calls in CI."""

    def __init__(self) -> None:
        self._cache: dict[str, JudgeDecision] = {}

    def get(self, key: str) -> JudgeDecision | None:
        return self._cache.get(key)

    def set(self, key: str, decision: JudgeDecision) -> None:
        self._cache[key] = decision


class JudgeSelector:
    """Resolves the judge to use for a metric."""

    def __init__(
        self,
        *,
        default_model: str = JudgeModel.GPT_5_1_REASONING.value,
        local_default: str = JudgeModel.GPT_4O_MINI.value,
        cache: JudgeCache | None = None,
    ) -> None:
        self.default_model = default_model
        self.local_default = local_default
        self.cache = cache or JudgeCache()

    def resolve(self, override: str | None = None, local: bool = False) -> str:
        if override:
            return override
        return self.local_default if local else self.default_model


def offline_judge_score(
    *, expected: str | None, actual: str, rubric: str, threshold: float | None
) -> JudgeDecision:
    """Deterministic offline judge used when LLM access is unavailable."""

    score = 0.0
    if expected:
        overlap = len(set(actual.lower().split()) & set(expected.lower().split()))
        score = overlap / max(len(expected.split()), 1)
    if rubric and rubric.lower() in actual.lower():
        score = max(score, 0.6)
    reasoning = "offline stub judge"
    return JudgeDecision(
        model=JudgeModel.OFFLINE_STUB.value,
        score=score,
        reasoning=reasoning,
        raw={"rubric": rubric, "expected": expected},
    )
