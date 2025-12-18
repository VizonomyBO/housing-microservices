from __future__ import annotations

from typing import Iterable, List, Optional

from .judges import LLMJudge
from .results import MetricResult
from .scenarios import DocumentRef, MetricName, MetricSpec
from .telemetry import ChatResult, citation_coverage


class MetricEvaluator:
    def __init__(self, judge: Optional[LLMJudge] = None) -> None:
        self.judge = judge

    def evaluate(
        self,
        chat_result: ChatResult,
        metric_specs: Iterable[MetricSpec],
        question: str,
        context_docs: List[DocumentRef],
    ) -> List[MetricResult]:
        results: List[MetricResult] = []
        for spec in metric_specs:
            if spec.name == MetricName.CITATION_COVERAGE:
                results.append(self._citation_coverage(chat_result, spec))
            elif spec.name == MetricName.LATENCY_MS:
                results.append(self._latency(chat_result, spec))
            elif spec.name == MetricName.LLM_GROUNDING:
                results.append(self._grounding(chat_result, spec, question, context_docs))
        return results

    @staticmethod
    def _citation_coverage(chat_result: ChatResult, spec: MetricSpec) -> MetricResult:
        coverage = citation_coverage(chat_result.answer)
        threshold = spec.threshold if spec.threshold is not None else 0.0
        return MetricResult(
            name=MetricName.CITATION_COVERAGE,
            passed=coverage >= threshold,
            score=coverage,
            detail=f"coverage={coverage:.2f}, threshold={threshold}",
        )

    @staticmethod
    def _latency(chat_result: ChatResult, spec: MetricSpec) -> MetricResult:
        if spec.threshold is None:
            return MetricResult(
                name=MetricName.LATENCY_MS,
                passed=True,
                score=chat_result.duration_ms,
                detail="no threshold provided; treating as pass",
                skipped=True,
            )
        budget = spec.threshold
        duration = chat_result.duration_ms
        return MetricResult(
            name=MetricName.LATENCY_MS,
            passed=duration <= budget,
            score=duration,
            detail=f"latency_ms={duration:.2f}, budget={budget}",
        )

    def _grounding(
        self,
        chat_result: ChatResult,
        spec: MetricSpec,
        question: str,
        context_docs: List[DocumentRef],
    ) -> MetricResult:
        if not self.judge:
            return MetricResult(
                name=MetricName.LLM_GROUNDING,
                passed=False,
                score=None,
                detail="LLM judge not configured (missing OPENAI_API_KEY?)",
                skipped=True,
            )
        threshold = spec.threshold if spec.threshold is not None else 0.7
        return self.judge.score_grounding(
            question=question,
            answer=chat_result.answer,
            contexts=context_docs,
            threshold=threshold,
        )
