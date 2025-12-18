from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .telemetry import ChatResult


@dataclass
class MetricResult:
    name: str
    passed: bool
    score: Optional[float] = None
    detail: str = ""
    skipped: bool = False


@dataclass
class EvalResult:
    scenario_name: str
    chat_result: ChatResult
    metrics: List[MetricResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(metric.passed or metric.skipped for metric in self.metrics)
