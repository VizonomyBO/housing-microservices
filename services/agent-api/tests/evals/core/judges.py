from __future__ import annotations

import json
from typing import Iterable, List, Optional

import openai

from .results import MetricResult
from .scenarios import DocumentRef, MetricName


class LLMJudge:
    def __init__(self, model: str = "gpt-5.1", reasoning_effort: str = "high") -> None:
        self.client = openai.OpenAI()
        self.model = model
        self.reasoning_effort = reasoning_effort

    def score_rubric(
        self,
        metric_name: str,
        question: str,
        answer: str,
        contexts: Iterable[DocumentRef],
        rubric: str,
        threshold: float,
        citation_snippets: Optional[List[str]] = None,
    ) -> MetricResult:
        doc_lines: List[str] = []
        for doc in contexts:
            doc_lines.append(
                f"- {doc.canonical_name or doc.document_id} (doc_id={doc.document_id}, country={doc.country_code})"
            )
        context_block = "\n".join(doc_lines) or "None provided"
        snippet_block = ""
        if citation_snippets:
            formatted = "\n".join(citation_snippets)
            snippet_block = f"\nCited snippets:\n{formatted}"
        prompt = (
            "You are an LLM judge for RAG evaluations.\n"
            "Return JSON with fields: score (0-1) and explanation (short, 1-2 sentences).\n"
            f"Metric: {metric_name}\n"
            f"Rubric: {rubric}\n"
            f"Question: {question}\n"
            f"Answer: {answer}\n"
            f"Documents:\n{context_block}"
            f"{snippet_block}"
        )
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": "You grade answers for RAG quality (grounding, precision, recall, truthfulness, bias).",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        score = float(parsed.get("score", 0))
        explanation = parsed.get("explanation") or parsed.get("reason") or ""
        passed = score >= threshold
        return MetricResult(
            name=metric_name,
            passed=passed,
            score=score,
            detail=explanation,
        )
