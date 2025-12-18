from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional


CITATION_PATTERN = re.compile(r"\[c\d+]", flags=re.IGNORECASE)


@dataclass
class Citation:
    doc_id: str
    chunk_id: Optional[str] = None
    canonical_name: Optional[str] = None
    score: Optional[float] = None
    text: Optional[str] = None


@dataclass
class ChatResult:
    answer: str
    citations: List[Citation] = field(default_factory=list)
    response_mode: str = "blocking"
    status_code: int = 200
    duration_ms: float = 0.0
    raw: Any = None
    request_id: Optional[str] = None
    tool_calls: Optional[List[dict]] = None


def parse_citations(raw: Iterable[dict[str, Any]]) -> List[Citation]:
    citations: List[Citation] = []
    for item in raw:
        citations.append(
            Citation(
                doc_id=item.get("doc_id") or "",
                chunk_id=item.get("chunk_id"),
                canonical_name=item.get("canonical_name"),
                score=item.get("score"),
                text=item.get("text"),
            )
        )
    return citations


def parse_standard_response(
    payload: dict[str, Any],
    status_code: int,
    response_mode: str,
    duration_ms: float,
) -> ChatResult:
    done_section = payload.get("done") or payload
    answer = done_section.get("answer") or done_section.get("message") or ""
    citations_raw = done_section.get("citations") or []
    citations = parse_citations(citations_raw)
    request_id = payload.get("request_id") or done_section.get("request_id")
    tool_calls = done_section.get("tool_calls")
    return ChatResult(
        answer=answer,
        citations=citations,
        response_mode=response_mode,
        status_code=status_code,
        duration_ms=duration_ms,
        raw=payload,
        request_id=request_id,
        tool_calls=tool_calls,
    )


def parse_sse_stream(
    status_code: int,
    response_mode: str,
    duration_ms: float,
    lines: Iterable[str],
) -> ChatResult:
    done_payload: Optional[dict[str, Any]] = None
    request_id: Optional[str] = None
    for line in lines:
        if not line or not line.startswith("data:"):
            continue
        data_section = line[len("data:") :].strip()
        if not data_section:
            continue
        try:
            parsed = json.loads(data_section)
        except json.JSONDecodeError:
            continue
        request_id = parsed.get("request_id") or request_id
        if parsed.get("event") == "done":
            done_payload = parsed.get("payload") or {}
            request_id = parsed.get("request_id") or request_id
            break
    if not done_payload:
        return ChatResult(
            answer="",
            citations=[],
            response_mode=response_mode,
            status_code=status_code,
            duration_ms=duration_ms,
            raw={"error": "stream ended without done event"},
            request_id=request_id,
        )
    citations = parse_citations(done_payload.get("citations") or [])
    return ChatResult(
        answer=done_payload.get("answer") or "",
        citations=citations,
        response_mode=response_mode,
        status_code=status_code,
        duration_ms=duration_ms,
        raw=done_payload,
        request_id=request_id,
    )


def citation_coverage(answer: str) -> float:
    sentences = [segment.strip() for segment in re.split(r"[.?!]\\s+", answer) if segment.strip()]
    if not sentences:
        return 0.0
    cited = [segment for segment in sentences if CITATION_PATTERN.search(segment)]
    return len(cited) / len(sentences)


def citation_doc_ids(result: ChatResult) -> List[str]:
    return [citation.doc_id for citation in result.citations if citation.doc_id]
