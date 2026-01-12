from __future__ import annotations

from dataclasses import dataclass, field

from .telemetry import ChatResult


@dataclass
class MetricResult:
    name: str
    passed: bool
    score: float | None = None
    detail: str = ""
    skipped: bool = False


@dataclass
class EvalResult:
    scenario_name: str
    chat_result: ChatResult
    metrics: list[MetricResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(metric.passed or metric.skipped for metric in self.metrics)
