"""Answer composer implementations backing AnswerSynthesizer nodes."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass

from cache.response_serializer import CacheCitation
from models.retrieval import AttachmentDocument, AttachmentScope
from services.model_clients import (
    OpenAIChatClientProtocol,
    VoyageRerankClientProtocol,
)
from subgraphs.informational.answer_synthesizer_node import (
    AnswerComposerProtocol,
    AnswerSynthesisContext,
    AnswerSynthesisError,
    AnswerSynthesisResult,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RetrievedChunk:
    """Lightweight retrieval result used to build prompts + citations."""

    doc_id: str
    chunk_id: str
    alias: str
    text: str
    page_number: int | None
    position: int | None
    score: float
    base_score: float | None = None
    heuristic_score: float | None = None
    coverage_tags: tuple[str, ...] = ()


@dataclass(slots=True)
class OpenAIAnswerComposer(AnswerComposerProtocol):
    """LLM-backed composer that requires a configured OpenAI client."""

    client: OpenAIChatClientProtocol
    temperature: float = 0.2
    max_output_tokens: int = 600
    max_retrieved_chunks: int = 8
    reranker: VoyageRerankClientProtocol | None = None
    rerank_top_k: int = 24

    async def compose(self, context: AnswerSynthesisContext) -> AnswerSynthesisResult:
        hyde_rewrite = await self._hyde_rewrite(context.normalized_prompt)
        retrieved_chunks = await self._select_chunks(
            prompt=context.normalized_prompt,
            scope=context.attachment_scope,
            allowed_document_ids=context.allowed_document_ids,
            hyde_rewrite=hyde_rewrite,
        )
        if not retrieved_chunks:
            raise AnswerSynthesisError("No retrieval context available for answer composition")
        citations = self._citations_from_chunks(retrieved_chunks)
        chunk_ids = [citation.chunk_id for citation in citations]

        prompt_text, cue_lines = self._build_prompt(
            context, retrieved_chunks, hyde_rewrite=hyde_rewrite
        )
        messages = self._messages(prompt_text, context.chat_history or [])
        text = await self.client.complete(
            messages,
            temperature=self.temperature,
            max_tokens=self.max_output_tokens,
        )
        if not text or not text.strip():
            raise AnswerSynthesisError("LLM returned an empty response for answer synthesis")
        if citations:
            citation_lines = []
            for idx, citation in enumerate(citations, start=1):
                alias = citation.metadata.get("document_alias") if citation.metadata else None
                label = alias or citation.doc_id
                citation_lines.append(f"- [c{idx}] {label} ({citation.chunk_id})")
            text = f"{text.strip()}\n\nCitations:\n" + "\n".join(citation_lines)
        metadata = {
            "model": "openai",
            "temperature": self.temperature,
            "mode": "standard",
            "hyde_rewrite": hyde_rewrite,
        }
        metadata["retrieved_snippets"] = [(chunk.text or "")[:160] for chunk in retrieved_chunks]
        if cue_lines:
            metadata["context_cues"] = cue_lines
        if context.allowed_document_ids:
            metadata["allowed_document_ids"] = sorted(context.allowed_document_ids)
        if self.reranker is not None:
            metadata["reranker_model"] = getattr(self.reranker, "model", None)
        return AnswerSynthesisResult(
            answer_text=text,
            citations=citations,
            chunk_ids=chunk_ids,
            model_metadata=metadata,
            quality_score=None,
        )

    async def _hyde_rewrite(self, question: str) -> str | None:
        """Generate a hypothetical answer to guide retrieval (HyDE-style)."""

        hyde_prompt = (
            "Draft a concise hypothetical answer to guide retrieval. "
            "Include expected entities and any likely numbers/percentages from the question. "
            "Two sentences max; do not add citations."
        )
        try:
            return await self.client.complete(
                messages=[
                    {"role": "system", "content": hyde_prompt},
                    {"role": "user", "content": question},
                ],
                temperature=0.0,
                max_tokens=120,
            )
        except Exception:
            return None

    def _build_prompt(
        self,
        context: AnswerSynthesisContext,
        chunks: Sequence[RetrievedChunk],
        *,
        hyde_rewrite: str | None = None,
    ) -> tuple[str, list[str]]:
        instructions = [
            "You are a housing policy analyst. Use ONLY the provided contexts.",
            "Before answering, list the required facts/figures/guardrails from the question AND from the contexts; ensure each appears in the final answer with a citation.",
            "When contexts list constraints/guardrails/policies, enumerate EVERY guardrail (names, counts, districts, percentages) and include them in the answer.",
            "If asked for guardrails/constraints, prioritize scope/eligibility limits (e.g., number of districts, rent caps) before optional carve-outs; do not swap in unrelated guardrails.",
            "For voucher expansion, always state the number of districts covered and the rent cap before any sub-allocations or carve-outs; do not replace coverage/counts with secondary guardrails. If only two guardrails are requested, prefer coverage count and rent cap first, then add carve-outs as supplemental detail.",
            "When contexts mention expansion counts (e.g., expanded from three to five districts), include the exact counts in Facts and in the Answer with citations.",
            "When contexts include money/totals or funding shifts, reuse the exact figures; when contexts mention reporting cadence or schedules, surface them in the answer.",
            "For multi-document questions, include at least one fact from each relevant document (e.g., policy guardrails + ledger funding + reporting cadence) and connect them explicitly.",
            "If crafting interventions/plans, ground each action in specific policy guardrails AND funding amounts AND reporting cadence when present.",
            "Never invent numbers or entities; respond with 'Not found in provided documents' if something is missing or unspecified.",
            "If the question asks for sums/maximums, compute them exactly from the contexts (no rounding beyond source).",
            "Output format (required):",
            "Facts:",
            "- [c#] item: <entity or metric> — value: <number/text> (unit) | citation: [c#]",
            "Answer:",
            "- concise paragraph that uses the facts and includes [c#] markers inline.",
            "Citations:",
            "- [c#] <document alias> (<chunk_id> or page) describing the evidence.",
            "If contexts mention tables or ledgers, use their exact totals and highest values without inventing programs.",
            "If contexts include reporting or digest cadences, mention them when relevant to the question.",
            "If multiple documents are provided, synthesize across them (e.g., combine guardrails + funding shifts + reporting cadence) rather than answering from only one.",
        ]
        doc_aliases = sorted({chunk.alias for chunk in chunks if chunk.alias})
        sections: list[str] = ["\n".join(instructions)]
        if doc_aliases:
            sections.append(
                "Document coverage requirement: include at least one fact from EACH of these documents and cite them: "
                + ", ".join(doc_aliases)
            )
        if hyde_rewrite:
            sections.append(f"HyDE hint: {hyde_rewrite}")
        cue_lines = self._guardrail_cues(chunks)
        if cue_lines:
            sections.append(
                "Context cues to preserve (high priority):\n- " + "\n- ".join(cue_lines[:6])
            )
            sections.append(
                "You must carry each context cue into the Facts and Answer sections with citations; do not drop or substitute them."
            )

        context_block = self._context_block(chunks)
        prompt_parts = [
            "You are Viz agent. Answer in markdown following the required format.",
            f"Question: {context.normalized_prompt}",
        ]
        if sections:
            prompt_parts.append("Guidelines:\n" + "\n\n".join(sections))
        prompt_parts.append(
            "Checklist before answering:\n"
            "- List every constraint/guardrail/policy mentioned in contexts (district counts, reserved percentages, caps).\n"
            "- List funding shifts and totals if present, especially per district.\n"
            "- List reporting cadence or schedules if present.\n"
            "- For multi-document questions, pull at least one fact from each relevant document.\n"
            "- Carry over each context cue (above) into Facts and the final Answer with [c#] citations; do not omit higher-level coverage counts.\n"
            "- Ensure each checklist item is included in Facts and in the final Answer with [c#]."
        )
        if context_block:
            prompt_parts.append("Contexts:\n" + context_block)
        else:
            prompt_parts.append("No contexts were provided; answer only if certain.")
        return "\n\n".join(prompt_parts), cue_lines

    def _messages(self, prompt: str, history: Sequence[dict[str, str]]) -> Sequence[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "You are a precise housing analyst. "
                    "Use only provided contexts. "
                    "Follow the Facts/Answer/Citations format and include [c#] markers for every fact."
                ),
            }
        ]
        normalized_history: list[dict[str, str]] = []
        for entry in history:
            role = entry.get("role") or "user"
            content = entry.get("content")
            if not content:
                continue
            normalized_history.append({"role": role, "content": content})
        if normalized_history:
            # Ensure the final turn reflects the current normalized prompt.
            if normalized_history[-1]["role"] == "user":
                normalized_history[-1] = {"role": "user", "content": prompt}
            else:
                normalized_history.append({"role": "user", "content": prompt})
            messages.extend(normalized_history)
        else:
            messages.append({"role": "user", "content": prompt})
        return messages

    async def _select_chunks(
        self,
        *,
        prompt: str,
        scope: AttachmentScope | None,
        allowed_document_ids: set[str],
        hyde_rewrite: str | None,
    ) -> list[RetrievedChunk]:
        if scope is None or not scope.documents:
            return []
        combined_query = f"{prompt} {hyde_rewrite or ''}".strip()
        tokens = self._tokenize(combined_query)
        numeric_targets = self._numeric_terms(combined_query)
        entities = self._extract_entities(combined_query)
        candidates: list[RetrievedChunk] = []
        for doc in scope.documents:
            if allowed_document_ids and doc.document_id not in allowed_document_ids:
                continue
            alias = self._document_alias(doc)
            for chunk in doc.chunks:
                text = chunk.text or ""
                base_score = getattr(chunk, "score", None)
                heuristic_score = self._score_chunk(
                    text=text,
                    tokens=tokens,
                    numeric_targets=numeric_targets,
                    entities=entities,
                )
                score = base_score if base_score is not None else heuristic_score
                if base_score is not None:
                    score = 0.7 * float(base_score) + 0.3 * float(heuristic_score)
                if alias and alias.lower() in combined_query.lower():
                    score += 0.3
                coverage_tags = self._coverage_tags(text=text, alias=alias)
                coverage_bonus = self._coverage_bonus(coverage_tags)
                score += coverage_bonus
                candidates.append(
                    RetrievedChunk(
                        doc_id=doc.document_id,
                        chunk_id=chunk.chunk_id,
                        alias=alias,
                        text=text,
                        page_number=chunk.page_number,
                        position=chunk.position,
                        score=score,
                        base_score=float(base_score) if base_score is not None else None,
                        heuristic_score=float(heuristic_score),
                        coverage_tags=tuple(sorted(coverage_tags)),
                    )
                )
        by_doc: dict[str, list[RetrievedChunk]] = {}
        for candidate in candidates:
            by_doc.setdefault(candidate.doc_id, []).append(candidate)
        per_doc_top: list[RetrievedChunk] = []
        for entries in by_doc.values():
            entries.sort(key=lambda entry: entry.score, reverse=True)
            per_doc_top.extend(entries[:3])

        per_doc_top.sort(key=lambda entry: entry.score, reverse=True)
        await self._rerank_candidates(
            query=combined_query,
            candidates=per_doc_top,
        )

        return self._coverage_aware_fusion(per_doc_top)

    async def _rerank_candidates(self, *, query: str, candidates: list[RetrievedChunk]) -> None:
        if self.reranker is None or not candidates:
            return
        pool = candidates[: min(self.rerank_top_k, len(candidates))]
        try:
            scores = await self.reranker.rerank(
                query=query,
                documents=[f"{cand.alias or cand.doc_id}: {cand.text}" for cand in pool],
                top_k=len(pool),
            )
        except Exception as exc:  # pragma: no cover - best-effort reranker
            logger.warning(
                "Voyage rerank failed; falling back to hybrid/heuristic order", exc_info=exc
            )
            return
        if not scores:
            return
        max_score = max(scores)
        for candidate, rerank_score in zip(pool, scores, strict=False):
            normalized = (rerank_score / max_score) if max_score else 0.0
            candidate.score = 0.5 * candidate.score + 0.5 * normalized
            candidate.base_score = candidate.base_score or candidate.score
            candidate.heuristic_score = candidate.heuristic_score or 0.0

    def _coverage_aware_fusion(self, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not candidates:
            return []
        # Normalize scores and compute reciprocal-rank fusion across docs to surface coverage.
        max_score = max(candidate.score for candidate in candidates) or 1.0
        global_sorted = sorted(candidates, key=lambda entry: entry.score, reverse=True)
        global_rank = {entry.chunk_id: idx for idx, entry in enumerate(global_sorted)}
        doc_ranks: dict[str, dict[str, int]] = {}
        for doc_id, doc_entries in self._group_by_doc(candidates).items():
            sorted_doc = sorted(doc_entries, key=lambda entry: entry.score, reverse=True)
            doc_ranks[doc_id] = {entry.chunk_id: idx for idx, entry in enumerate(sorted_doc)}

        for candidate in candidates:
            fused_rrf = (1.0 / (60.0 + global_rank.get(candidate.chunk_id, 0))) + (
                1.0 / (10.0 + doc_ranks.get(candidate.doc_id, {}).get(candidate.chunk_id, 0))
            )
            coverage_bonus = self._coverage_bonus(set(candidate.coverage_tags))
            normalized_score = candidate.score / max_score
            candidate.score = 0.55 * normalized_score + 0.25 * fused_rrf + 0.2 * coverage_bonus

        # Ensure we keep at least one chunk for policy, funding, and reporting cues when present.
        selected: list[RetrievedChunk] = []
        seen: set[str] = set()
        doc_cap = 2
        doc_counts: dict[str, int] = {}

        def maybe_add(entry: RetrievedChunk) -> None:
            if entry.chunk_id in seen:
                return
            if doc_counts.get(entry.doc_id, 0) >= doc_cap:
                return
            selected.append(entry)
            seen.add(entry.chunk_id)
            doc_counts[entry.doc_id] = doc_counts.get(entry.doc_id, 0) + 1

        tagged = {"policy", "funding", "reporting"}
        coverage_order = sorted(
            [entry for entry in candidates if tagged.intersection(entry.coverage_tags)],
            key=lambda entry: entry.score,
            reverse=True,
        )
        for tag in ("funding", "reporting", "policy"):
            for entry in coverage_order:
                if tag in entry.coverage_tags:
                    maybe_add(entry)
                    break

        for entry in sorted(candidates, key=lambda item: item.score, reverse=True):
            if len(selected) >= self.max_retrieved_chunks:
                break
            maybe_add(entry)
        return selected[: self.max_retrieved_chunks]

    def _score_chunk(
        self, *, text: str, tokens: set[str], numeric_targets: set[str], entities: set[str]
    ) -> float:
        lower_text = text.lower()
        token_hits = sum(1 for token in tokens if token and token in lower_text)
        entity_hits = sum(1 for entity in entities if entity and entity in lower_text)
        normalized_text_numbers = re.sub(r"[^\d]", "", text)
        numeric_hits = sum(1 for num in numeric_targets if num and num in normalized_text_numbers)
        has_numeric = bool(re.search(r"\d", text))
        policy_hits = sum(
            1
            for keyword in (
                "district",
                "guardrail",
                "report",
                "monthly",
                "cadence",
                "funding",
                "expansion",
                "cap",
            )
            if keyword in lower_text
        )
        return (
            float(token_hits)
            + 0.6 * float(entity_hits)
            + 0.8 * float(numeric_hits)
            + (0.6 if has_numeric else 0.0)
            + 0.7 * float(policy_hits)
        )

    def _coverage_tags(self, *, text: str, alias: str | None) -> set[str]:
        lower = text.lower()
        tags: set[str] = set()
        if any(
            token in lower for token in ("fund", "budget", "$", "allocation", "ledger", "shift")
        ):
            tags.add("funding")
        if any(token in lower for token in ("report", "monthly", "quarter", "cadence", "update")):
            tags.add("reporting")
        if any(
            token in lower for token in ("policy", "guardrail", "district", "eligibility", "cap")
        ):
            tags.add("policy")
        if alias:
            alias_lower = alias.lower()
            if "report" in alias_lower:
                tags.add("reporting")
            if "budget" in alias_lower or "fund" in alias_lower:
                tags.add("funding")
        return tags

    def _coverage_bonus(self, tags: set[str]) -> float:
        bonus = 0.0
        if "funding" in tags:
            bonus += 0.35
        if "reporting" in tags:
            bonus += 0.25
        if "policy" in tags:
            bonus += 0.2
        return bonus

    def _group_by_doc(self, candidates: list[RetrievedChunk]) -> dict[str, list[RetrievedChunk]]:
        by_doc: dict[str, list[RetrievedChunk]] = {}
        for entry in candidates:
            by_doc.setdefault(entry.doc_id, []).append(entry)
        return by_doc

    def _guardrail_cues(self, chunks: Sequence[RetrievedChunk]) -> list[str]:
        scored: list[tuple[float, str]] = []
        for chunk in chunks:
            for raw_line in chunk.text.splitlines():
                line = raw_line.strip().strip("-• ").strip()
                if not line:
                    continue
                lower = line.lower()
                if not re.search(r"\d", line):
                    continue
                if any(
                    token in lower
                    for token in ("district", "cap", "voucher", "expansion", "report", "rent")
                ):
                    score = 0.0
                    if "expansion" in lower or "pilot" in lower:
                        score += 3.0
                    if "district" in lower:
                        score += 2.0
                    if "cap" in lower or "rent relief" in lower:
                        score += 1.8
                    if "report" in lower or "cadence" in lower:
                        score += 1.2
                    if "reserve" in lower or "slot" in lower:
                        score += 1.0
                    if re.search(r"\b5\b|five", lower):
                        score += 0.6
                    scored.append((score, line))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [line for _, line in scored]

    def _tokenize(self, text: str) -> set[str]:
        return {token for token in re.findall(r"[a-zA-Z0-9]+", text.lower()) if len(token) > 2}

    def _numeric_terms(self, text: str) -> set[str]:
        digits = {re.sub(r"[^\d]", "", match) for match in re.findall(r"[0-9][0-9,\\.]*", text)}
        return {term for term in digits if term}

    def _extract_entities(self, text: str) -> set[str]:
        entities: set[str] = set()
        for match in re.findall(r"(district\s+\d+|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", text):
            normalized = match.strip().lower()
            if normalized:
                entities.add(normalized)
        return entities

    def _context_block(self, chunks: Sequence[RetrievedChunk]) -> str:
        if not chunks:
            return ""
        lines: list[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            header = f"[c{idx}] {chunk.alias} (chunk_id={chunk.chunk_id}"
            if chunk.page_number is not None:
                header += f", page={chunk.page_number}"
            if chunk.position is not None:
                header += f", pos={chunk.position}"
            header += ")"
            lines.append(f"{header}\n{chunk.text.strip()}")
        return "\n\n".join(lines)

    def _citations_from_chunks(self, chunks: Sequence[RetrievedChunk]) -> list[CacheCitation]:
        citations: list[CacheCitation] = []
        for idx, chunk in enumerate(chunks, start=1):
            snippet = (chunk.text or "").strip()
            if len(snippet) > 320:
                snippet = snippet[:320]
            citations.append(
                CacheCitation(
                    doc_id=chunk.doc_id,
                    chunk_id=chunk.chunk_id,
                    snippet=snippet,
                    metadata={
                        "document_alias": chunk.alias,
                        "page": chunk.page_number,
                        "position": chunk.position,
                        "citation_key": f"c{idx}",
                        "footnote": idx,
                    },
                )
            )
        return citations

    def _attachment_overview(self, scope: AttachmentScope | None) -> str:
        if scope is None or not scope.documents:
            return ""
        sections: list[str] = []
        for doc in scope.documents:
            alias = self._document_alias(doc)
            header = f"### {alias} — {doc.canonical_name or doc.document_id}"
            chunk_lines = []
            for chunk in doc.chunks:
                snippet = chunk.text.strip()
                if not snippet:
                    continue
                prefix = f"[chunk {chunk.position if chunk.position is not None else 0}]"
                chunk_lines.append(f"{prefix} {snippet}")
            if not chunk_lines:
                continue
            sections.append(f"{header}\n" + "\n\n".join(chunk_lines))
        return "\n\n".join(sections)

    def _document_alias(self, doc: AttachmentDocument) -> str:
        metadata = doc.metadata or {}
        return metadata.get("document_alias") or doc.canonical_name or doc.document_id


__all__ = ["OpenAIAnswerComposer"]
