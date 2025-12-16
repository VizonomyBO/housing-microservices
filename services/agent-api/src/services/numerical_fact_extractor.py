"""LLM-backed numeric fact extractor for prose attachments."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from models.retrieval import AttachmentDocument, AttachmentDocumentChunk
from services.model_clients import OpenAIChatClientProtocol


@dataclass(slots=True)
class NumericFact:
    """Structured numeric fact emitted by the extractor."""

    label: str
    value: float
    unit: str
    source_doc: str
    source_chunk: str | None
    raw: str

    def to_row(self) -> dict[str, Any]:
        """Return a table-friendly row representation."""

        unit = self.unit or ""
        return {
            "label": self.label,
            "value": self.value,
            "unit": unit,
            "source_doc": self.source_doc,
            "source_chunk": self.source_chunk or "",
            "raw": self.raw,
        }


@dataclass(slots=True)
class NumericFactExtractor:
    """Extracts numeric facts from unstructured text using an LLM."""

    client: OpenAIChatClientProtocol
    temperature: float = 0.0
    max_tokens: int = 300
    max_chunks: int = 4
    max_facts: int = 20

    async def extract(self, document: AttachmentDocument) -> list[NumericFact]:
        """Return numeric facts for the provided document.

        Requires an OpenAI client; no regex fallback is performed when the LLM is
        unavailable or returns an empty result.
        """

        if self.client is None:
            raise RuntimeError("OpenAI client is required for numeric fact extraction")
        facts: list[NumericFact] = []
        chunks = (document.chunks or [])[: self.max_chunks]
        for chunk in chunks:
            text = (chunk.text or "").strip()
            if not text:
                continue
            if not self._has_numeric_signal(text):
                continue
            llm_facts: list[NumericFact] = await self._extract_with_llm(document, chunk, text)
            facts.extend(llm_facts)
            if len(facts) >= self.max_facts:
                return facts[: self.max_facts]

        if not facts:
            raise RuntimeError("LLM returned no numeric facts for the provided document")

        return facts[: self.max_facts]

    async def _extract_with_llm(
        self,
        document: AttachmentDocument,
        chunk: AttachmentDocumentChunk,
        text: str,
    ) -> list[NumericFact]:
        messages: Sequence[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "Extract numeric facts (metrics, percentages, monetary amounts, counts,"
                    " ratios, thresholds) from the provided text. Return ONLY valid JSON"
                    " without commentary. The JSON must be a list of objects with keys:"
                    " label (short title), value (number), unit (string or empty), raw"
                    " (the exact snippet containing the number). Skip dates/IDs unless"
                    " clearly used as KPIs."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Document: {document.canonical_name or document.document_id}\n"
                    f"Chunk ID: {chunk.chunk_id}\n"
                    "Text:\n" + text[:2000]
                ),
            },
        ]
        content = await self.client.complete(
            messages, temperature=self.temperature, max_tokens=self.max_tokens
        )
        return self._parse_llm_response(content, document, chunk)

    def _parse_llm_response(
        self, response: str, document: AttachmentDocument, chunk: AttachmentDocumentChunk
    ) -> list[NumericFact]:
        cleaned = response.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
        if fenced:
            cleaned = fenced.group(1).strip()
        # Attempt to isolate the first JSON payload
        if cleaned and not cleaned.startswith("[") and not cleaned.startswith("{"):
            match = re.search(r"(\[.*\]|\{.*\})", cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1)
        parsed = json.loads(cleaned)

        items: list[Any]
        if isinstance(parsed, dict) and isinstance(parsed.get("facts"), list):
            items = parsed["facts"]
        elif isinstance(parsed, list):
            items = parsed
        else:
            raise ValueError("Unexpected LLM numeric fact payload structure")

        facts: list[NumericFact] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            value = self._coerce_number(item.get("value"))
            if value is None:
                continue
            label = str(item.get("label") or "value").strip()[:120]
            unit = str(item.get("unit") or "").strip()[:32]
            raw = str(item.get("raw") or item.get("source") or "").strip()
            if not raw:
                raw = (item.get("text") or "") if isinstance(item.get("text"), str) else ""
            if not raw:
                raw = (chunk.text or "")[:240]
            facts.append(
                NumericFact(
                    label=label or "value",
                    value=value,
                    unit=unit,
                    source_doc=document.document_id,
                    source_chunk=chunk.chunk_id,
                    raw=raw[:240],
                )
            )
        return facts

    def _has_numeric_signal(self, text: str) -> bool:
        lowered = text.lower()
        digit_count = len(re.findall(r"\d", lowered))
        numeric_tokens = {
            "percent",
            "%",
            "kpi",
            "score",
            "utilization",
            "threshold",
            "rate",
            "budget",
            "ledger",
            "balance",
            "revenue",
            "cost",
            "expense",
            "total",
            "sum",
            "average",
            "median",
        }
        return digit_count >= 1 or any(token in lowered for token in numeric_tokens)

    def _coerce_number(self, value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if not isinstance(value, str):
            return None
        cleaned = value.strip().replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            match = re.search(r"([-+]?[0-9]+(?:\.[0-9]+)?)", cleaned)
            if not match:
                return None
            try:
                return float(match.group(1))
            except ValueError:
                return None


__all__ = ["NumericFact", "NumericFactExtractor"]
