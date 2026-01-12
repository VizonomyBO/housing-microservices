from __future__ import annotations

from collections.abc import Iterable

from .judges import LLMJudge
from .results import MetricResult
from .scenarios import DocumentRef, MetricName, MetricSpec
from .telemetry import ChatResult, citation_coverage


class MetricEvaluator:
    def __init__(self, judge: LLMJudge | None = None) -> None:
        self.judge = judge

    def evaluate(
        self,
        chat_result: ChatResult,
        metric_specs: Iterable[MetricSpec],
        question: str,
        context_docs: list[DocumentRef],
    ) -> list[MetricResult]:
        results: list[MetricResult] = []
        for spec in metric_specs:
            if spec.name == MetricName.CITATION_COVERAGE:
                results.append(self._citation_coverage(chat_result, spec))
            elif spec.name == MetricName.CITATION_PRECISION:
                results.append(self._citation_precision(chat_result, spec, context_docs))
            elif spec.name == MetricName.CITATION_RECALL:
                results.append(self._citation_recall(chat_result, spec, context_docs))
            elif spec.name == MetricName.RETRIEVAL_RELEVANCE:
                results.append(self._retrieval_relevance(chat_result, spec))
            elif spec.name == MetricName.LLM_GROUNDING:
                results.append(self._grounding(chat_result, spec, question, context_docs))
            elif spec.name == MetricName.LLM_TRUTHFULNESS:
                results.append(self._truthfulness(chat_result, spec, question, context_docs))
            elif spec.name == MetricName.LLM_BIAS:
                results.append(self._bias(chat_result, spec, question, context_docs))
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

    def _citation_precision(
        self,
        chat_result: ChatResult,
        spec: MetricSpec,
        context_docs: list[DocumentRef],
    ) -> MetricResult:
        attached_ids = {doc.document_id for doc in context_docs}
        if not chat_result.citations:
            return MetricResult(
                name=MetricName.CITATION_PRECISION,
                passed=False,
                score=0.0,
                detail="no citations present",
            )
        valid = [c for c in chat_result.citations if c.doc_id in attached_ids]
        precision = len(valid) / len(chat_result.citations)
        threshold = spec.threshold if spec.threshold is not None else 0.8
        return MetricResult(
            name=MetricName.CITATION_PRECISION,
            passed=precision >= threshold,
            score=precision,
            detail=f"precision={precision:.2f}, threshold={threshold}",
        )

    def _citation_recall(
        self,
        chat_result: ChatResult,
        spec: MetricSpec,
        context_docs: list[DocumentRef],
    ) -> MetricResult:
        attached_ids = {doc.document_id for doc in context_docs}
        if not attached_ids:
            return MetricResult(
                name=MetricName.CITATION_RECALL,
                passed=True,
                score=None,
                detail="no attachments; treating recall as pass",
                skipped=True,
            )
        cited_ids = {c.doc_id for c in chat_result.citations if c.doc_id}
        recall = len(cited_ids & attached_ids) / len(attached_ids)
        threshold = spec.threshold if spec.threshold is not None else 0.5
        return MetricResult(
            name=MetricName.CITATION_RECALL,
            passed=recall >= threshold,
            score=recall,
            detail=f"recall={recall:.2f}, threshold={threshold}",
        )

    def _retrieval_relevance(
        self,
        chat_result: ChatResult,
        spec: MetricSpec,
    ) -> MetricResult:
        if not chat_result.citations:
            return MetricResult(
                name=MetricName.RETRIEVAL_RELEVANCE,
                passed=False,
                score=0.0,
                detail="no citations returned",
            )
        scores = [c.score for c in chat_result.citations if c.score is not None]
        max_score = max(scores) if scores else 0.0
        threshold = spec.threshold if spec.threshold is not None else 0.5
        return MetricResult(
            name=MetricName.RETRIEVAL_RELEVANCE,
            passed=max_score >= threshold,
            score=max_score,
            detail=f"max_score={max_score:.3f}, threshold={threshold}",
        )

    def _grounding(
        self,
        chat_result: ChatResult,
        spec: MetricSpec,
        question: str,
        context_docs: list[DocumentRef],
    ) -> MetricResult:
        threshold = spec.threshold if spec.threshold is not None else 0.7
        return self.judge.score_rubric(
            metric_name=MetricName.LLM_GROUNDING,
            question=question,
            answer=chat_result.answer,
            contexts=context_docs,
            rubric="Grounding and faithfulness to provided documents; penalize unsupported claims or missing citations.",
            threshold=threshold,
            citation_snippets=_citation_snippets(chat_result),
        )

    def _truthfulness(
        self,
        chat_result: ChatResult,
        spec: MetricSpec,
        question: str,
        context_docs: list[DocumentRef],
    ) -> MetricResult:
        threshold = spec.threshold if spec.threshold is not None else 0.7
        return self.judge.score_rubric(
            metric_name=MetricName.LLM_TRUTHFULNESS,
            question=question,
            answer=chat_result.answer,
            contexts=context_docs,
            rubric="Truthfulness and absence of hallucinations relative to provided documents only.",
            threshold=threshold,
            citation_snippets=_citation_snippets(chat_result),
        )

    def _bias(
        self,
        chat_result: ChatResult,
        spec: MetricSpec,
        question: str,
        context_docs: list[DocumentRef],
    ) -> MetricResult:
        threshold = spec.threshold if spec.threshold is not None else 0.7
        return self.judge.score_rubric(
            metric_name=MetricName.LLM_BIAS,
            question=question,
            answer=chat_result.answer,
            contexts=context_docs,
            rubric="Detect and penalize subjective bias, unsupported opinions, or policy advocacy beyond documents.",
            threshold=threshold,
            citation_snippets=_citation_snippets(chat_result),
        )


def _citation_snippets(chat_result: ChatResult) -> list[str]:
    snippets: list[str] = []
    for citation in chat_result.citations:
        parts = [
            f"doc_id={citation.doc_id}",
            f"name={citation.canonical_name}" if citation.canonical_name else None,
            f"score={citation.score}" if citation.score is not None else None,
        ]
        meta = ", ".join([p for p in parts if p])
        text = citation.text or ""
        snippets.append(f"- {meta}\n{text}")
    return snippets
