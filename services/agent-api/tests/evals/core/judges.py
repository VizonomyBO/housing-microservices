from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any


class JudgeModel(str, Enum):
    """Supported judge models."""

    GPT_51_REASONING_MEDIUM = "gpt-5.1-reasoning-medium"


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
        default_model: str = os.getenv("EVAL_JUDGE_MODEL", JudgeModel.GPT_51_REASONING_MEDIUM.value),
        cache: JudgeCache | None = None,
    ) -> None:
        self.default_model = default_model
        self.cache = cache or JudgeCache()

    def resolve(self, override: str | None = None, local: bool = False) -> str:
        if override:
            return override
        return self.default_model
