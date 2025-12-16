from __future__ import annotations

import json
import re
from typing import Any


def render_answer_with_citations(response_body: dict[str, Any]) -> str:
    """Render a text-only answer that preserves citations and SQL rows for eval metrics."""

    done = response_body.get("done") or {}
    answer = str(done.get("answer") or "")
    citations = done.get("citations") or []

    footnotes: list[str] = []
    for idx, citation in enumerate(citations, start=1):
        metadata = citation.get("metadata") or {}
        alias = (
            metadata.get("document_alias")
            or metadata.get("document_title")
            or citation.get("doc_id")
        )
        chunk_id = citation.get("chunk_id") or ""
        snippet = citation.get("snippet") or metadata.get("snippet") or ""
        page = metadata.get("page")
        meta = f"page {page}" if page is not None else ""
        parts = [f"[{idx}] {alias} ({chunk_id})"]
        if meta:
            parts.append(meta)
        if snippet:
            parts.append(snippet)
        footnotes.append(" — ".join(parts))

    sql_rows_text = ""
    table_results = done.get("table_results") or done.get("numerical_trace", {}).get(
        "table_results"
    )
    if table_results:
        sql_rows_text = "SQL_ROWS:\n" + "\n".join(
            f"- {json.dumps(row, ensure_ascii=False)}" for row in table_results
        )

    body_parts = [answer]
    if sql_rows_text:
        body_parts.append(sql_rows_text)
    if footnotes:
        body_parts.append("Sources:\n" + "\n".join(footnotes))
    processed = "\n\n".join(part for part in body_parts if part)

    # Preserve [c#] markers by ensuring they remain untouched; also keep DOC_* markers if present.
    placeholder_pattern = re.compile(r"\[(DOC_[^\]]+|c\d+|\d+)\]")
    processed = placeholder_pattern.sub(lambda m: m.group(0), processed)
    return processed


__all__ = ["render_answer_with_citations"]
