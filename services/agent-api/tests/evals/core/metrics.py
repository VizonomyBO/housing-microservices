from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from datasets import Dataset
from deepeval.metrics import GEval
from deepeval.models import GPTModel
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from langchain_openai import ChatOpenAI
from ragas import evaluate
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import context_precision, context_recall

from .judges import JudgeDecision, JudgeSelector
from .scenarios import EvalScenario, Expectation, MetricName, MetricSpec
from .telemetry import EvalTelemetrySink


@dataclass(slots=True)
class MetricResult:
    """Result for a single metric evaluation."""

    name: str
    score: float | None
    threshold: float | None
    passed: bool
    status: str = "ok"
    details: dict[str, Any] = field(default_factory=dict)
    decision: JudgeDecision | None = None


class MetricEngine:
    """Runs metric specs against a model response."""

    def __init__(self, *, judge_selector: JudgeSelector | None = None) -> None:
        self.judge_selector = judge_selector or JudgeSelector()

    def evaluate(
        self,
        *,
        scenario: EvalScenario,
        response_text: str,
        expectation: Expectation,
        telemetry: EvalTelemetrySink,
        latency_ms: float | None,
        specs: Iterable[MetricSpec] | None = None,
        contexts: list[str] | None = None,
        question: str | None = None,
    ) -> list[MetricResult]:
        metric_specs = list(specs) if specs is not None else list(scenario.metrics)
        if not metric_specs:
            metric_specs = [MetricSpec(name=MetricName.FAITHFULNESS, threshold=0.5)]

        results: list[MetricResult] = []
        for spec in metric_specs:
            metric_name = spec.name.value if isinstance(spec.name, MetricName) else str(spec.name)
            handler = getattr(self, f"_evaluate_{metric_name}", self._evaluate_unknown)
            result = handler(
                spec=spec,
                response_text=response_text,
                expectation=expectation,
                telemetry=telemetry,
                latency_ms=latency_ms,
                contexts=contexts or [],
                question=question or "",
            )
            result.name = metric_name
            result.details.setdefault("expectation", expectation.label)
            results.append(result)
        return results

    def _evaluate_faithfulness(
        self,
        *,
        spec: MetricSpec,
        response_text: str,
        expectation: Expectation,
        telemetry: EvalTelemetrySink,
        latency_ms: float | None,
        contexts: list[str],
        question: str,
    ) -> MetricResult:
        judge_model = self.judge_selector.resolve(spec.judge, local=False)
        metric = GEval(
            name="faithfulness",
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.CONTEXT,
            ],
            criteria=expectation.rubric,
            model=self._build_deepeval_model(judge_model),
            threshold=spec.threshold or 0.5,
        )
        test_case = LLMTestCase(
            input=question,
            actual_output=response_text,
            expected_output=expectation.expected_answer,
            context=contexts,
            retrieval_context=contexts,
        )
        metric.measure(test_case)
        decision = JudgeDecision(
            model=judge_model,
            score=float(metric.score),
            reasoning=getattr(metric, "reason", "") or "",
            raw={"criteria": expectation.rubric},
        )
        return MetricResult(
            name=MetricName.FAITHFULNESS.value,
            score=decision.score,
            threshold=spec.threshold,
            passed=decision.passed(spec.threshold),
            decision=decision,
            details={"judge_model": judge_model},
        )

    def _evaluate_answer_relevance(
        self,
        *,
        spec: MetricSpec,
        response_text: str,
        expectation: Expectation,
        telemetry: EvalTelemetrySink,
        latency_ms: float | None,
        contexts: list[str],
        question: str,
    ) -> MetricResult:
        judge_model = self.judge_selector.resolve(spec.judge, local=False)
        metric = GEval(
            name="answer_relevance",
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.CONTEXT,
            ],
            criteria=expectation.rubric,
            model=self._build_deepeval_model(judge_model),
            threshold=spec.threshold or 0.5,
        )
        test_case = LLMTestCase(
            input=question,
            actual_output=response_text,
            expected_output=expectation.expected_answer,
            context=contexts,
            retrieval_context=contexts,
        )
        metric.measure(test_case)
        decision = JudgeDecision(
            model=judge_model,
            score=float(metric.score),
            reasoning=getattr(metric, "reason", "") or "",
            raw={"criteria": expectation.rubric},
        )
        return MetricResult(
            name=MetricName.ANSWER_RELEVANCE.value,
            score=decision.score,
            threshold=spec.threshold,
            passed=decision.passed(spec.threshold),
            decision=decision,
            details={"judge_model": judge_model},
        )

    def _evaluate_context_precision(
        self,
        *,
        spec: MetricSpec,
        response_text: str,
        expectation: Expectation,
        telemetry: EvalTelemetrySink,
        latency_ms: float | None,
        contexts: list[str],
        question: str,
    ) -> MetricResult:
        score = self._run_ragas_metric(
            metric=context_precision,
            question=question,
            answer=response_text,
            contexts=contexts,
            reference=expectation.expected_answer or expectation.rubric,
        )
        return MetricResult(
            name=MetricName.CONTEXT_PRECISION.value,
            score=score,
            threshold=spec.threshold,
            passed=(spec.threshold is None) or (score is not None and score >= spec.threshold),
            details={"contexts_used": len(contexts)},
        )

    def _evaluate_context_recall(
        self,
        *,
        spec: MetricSpec,
        response_text: str,
        expectation: Expectation,
        telemetry: EvalTelemetrySink,
        latency_ms: float | None,
        contexts: list[str],
        question: str,
    ) -> MetricResult:
        score = self._run_ragas_metric(
            metric=context_recall,
            question=question,
            answer=response_text,
            contexts=contexts,
            reference=expectation.expected_answer or expectation.rubric,
        )
        return MetricResult(
            name=MetricName.CONTEXT_RECALL.value,
            score=score,
            threshold=spec.threshold,
            passed=(spec.threshold is None) or (score is not None and score >= spec.threshold),
            details={"contexts_used": len(contexts)},
        )

    def _evaluate_citation_coverage(
        self,
        *,
        spec: MetricSpec,
        response_text: str,
        expectation: Expectation,
        telemetry: EvalTelemetrySink,
        latency_ms: float | None,
        contexts: list[str],
        question: str,
    ) -> MetricResult:
        if not expectation.citations_required:
            return MetricResult(
                name=MetricName.CITATION_COVERAGE,
                score=1.0,
                threshold=spec.threshold,
                passed=True,
                details={"reason": "Citations not required for this expectation."},
            )
        has_citation = "[" in response_text and "]" in response_text
        score = 1.0 if has_citation else 0.0
        return MetricResult(
            name=MetricName.CITATION_COVERAGE.value,
            score=score,
            threshold=spec.threshold,
            passed=(spec.threshold is None) or has_citation,
            details={"detected_citation": has_citation},
        )

    def _evaluate_latency(
        self,
        *,
        spec: MetricSpec,
        response_text: str,
        expectation: Expectation,
        telemetry: EvalTelemetrySink,
        latency_ms: float | None,
        contexts: list[str],
        question: str,
    ) -> MetricResult:
        if latency_ms is None:
            return MetricResult(
                name=MetricName.LATENCY.value,
                score=None,
                threshold=spec.threshold,
                passed=True,
                status="skipped",
                details={"reason": "Latency unavailable for this run."},
            )
        score = max(0.0, 1.0 - (latency_ms / 5000.0))
        passed = spec.threshold is None or latency_ms <= (spec.threshold * 1000)
        return MetricResult(
            name=MetricName.LATENCY.value,
            score=score,
            threshold=spec.threshold,
            passed=passed,
            details={"latency_ms": latency_ms},
        )

    def _evaluate_toxicity(
        self,
        *,
        spec: MetricSpec,
        response_text: str,
        expectation: Expectation,
        telemetry: EvalTelemetrySink,
        latency_ms: float | None,
        contexts: list[str],
        question: str,
    ) -> MetricResult:
        toxic_keywords = ("hate", "violent", "toxic")
        score = 1.0 if not any(word in response_text.lower() for word in toxic_keywords) else 0.0
        return MetricResult(
            name=MetricName.TOXICITY.value,
            score=score,
            threshold=spec.threshold,
            passed=spec.threshold is None or score >= spec.threshold,
            details={"keywords_checked": toxic_keywords},
        )

    def _evaluate_unknown(
        self,
        *,
        spec: MetricSpec,
        response_text: str,
        expectation: Expectation,
        telemetry: EvalTelemetrySink,
        latency_ms: float | None,
        contexts: list[str],
        question: str,
    ) -> MetricResult:
        return MetricResult(
            name=str(spec.name),
            score=None,
            threshold=spec.threshold,
            passed=True,
            status="skipped",
            details={"reason": "Metric type not yet implemented."},
        )

    def _run_ragas_metric(
        self,
        *,
        metric,
        question: str,
        answer: str,
        contexts: list[str],
        reference: str | None,
    ) -> float | None:
        if not contexts:
            return 0.0
        llm = LangchainLLMWrapper(ChatOpenAI(model=self.judge_selector.default_model))
        dataset = Dataset.from_dict(
            {
                "question": [question],
                "answer": [answer],
                "contexts": [contexts],
                "ground_truth": [reference or ""],
            }
        )
        result = evaluate(
            dataset=dataset,
            metrics=[metric],
            llm=llm,
            column_map={
                "question": "question",
                "answer": "answer",
                "contexts": "contexts",
                "ground_truth": "ground_truth",
            },
        )
        return float(result[metric.name]) if metric.name in result else None

    def _build_deepeval_model(self, model_name: str) -> GPTModel:
        api_key = os.environ.get("OPENAI_API_KEY") or self._env_value_from_root("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for eval metrics.")
        normalized = model_name
        return GPTModel(model=normalized, api_key=api_key)

    def _env_value_from_root(self, key: str) -> str | None:
        env_path = Path(__file__).resolve().parents[5] / ".env.prod"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if not line or line.strip().startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                if name.strip() == key:
                    return value.strip().strip('"').strip("'")
        return None
