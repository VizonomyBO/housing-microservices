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

    def score_grounding(
        self,
        question: str,
        answer: str,
        contexts: Iterable[DocumentRef],
        threshold: float,
    ) -> MetricResult:
        doc_lines: List[str] = []
        for doc in contexts:
            doc_lines.append(
                f"- {doc.canonical_name or doc.document_id} (doc_id={doc.document_id}, country={doc.country_code})"
            )
        context_block = "\n".join(doc_lines)
        prompt = (
            "You are an LLM judge scoring how well an answer is grounded in the provided documents.\n"
            "Score from 0 to 1 where 1 is fully grounded and faithful. Respond with JSON: "
            '{"score": <0-1 number>, "explanation": "<short reason>"}.\n'
            f"Question: {question}\n"
            f"Answer: {answer}\n"
            f"Documents:\n{context_block}"
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": "You grade answers for grounding and citation faithfulness.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                extra_body={"reasoning": {"effort": self.reasoning_effort}},
            )
            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)
            score = float(parsed.get("score", 0))
            explanation = parsed.get("explanation") or parsed.get("reason") or ""
            passed = score >= threshold
            return MetricResult(
                name=MetricName.LLM_GROUNDING,
                passed=passed,
                score=score,
                detail=explanation,
            )
        except Exception as error:  # noqa: BLE001
            return MetricResult(
                name=MetricName.LLM_GROUNDING,
                passed=False,
                score=None,
                detail=f"LLM judge failed: {error}",
            )
