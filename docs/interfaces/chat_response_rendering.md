# Chat Response Parsing & Citation Rendering (Frontend Guide)

This guide explains how to parse the final chat payload (blocking response or the final SSE `done` frame) and render citations or numeric evidence. Fields may appear at the top level (blocking) or under `done` (streaming); treat the references below as `response.<field>` either way.

## Final Payload Shape (authoritative fields)
- `status`: lifecycle of the run (`COMPLETED`, `FAILED`, `INTERRUPTED`, etc.).
- `answer`: user-facing text, possibly containing `[SQL_ROWS]` placeholders and numbered footnotes.
- `thread_id` / `request_id`: identifiers for logging/analytics.
- `route`: execution path (e.g., `escalate`, `numerical`, `informational`); not user-facing.
- `requires_sql`: whether the answer came from SQL/numeric retrieval.
- `citations[]`: authoritative source list for text references (see "Citation Fields").
- `answer_metadata.inline_citations[]`: mapping from inline placeholders/footnotes to `citations[]` (see "Inline Citation Mapping"). Additional metadata (model, temperature, mode) may be present; keep those for diagnostics only.
- `table_results[]`: structured numeric/table evidence; mirrors `numerical_trace.table_results` when SQL is involved.
- `sql_queries[]`: executed SQL statements (top-level) and/or under `numerical_trace.sql_queries` / `answer_metadata.sql_trace.sql_queries` for debugging.
- `sql_row_count`: total rows returned for `table_results`.
- `numerical_trace`: detailed execution trace (table specs, executor timings, validator results, etc.); debugging only.
- `messages`: echoed conversation turns; do not render.

## What to Display
- Main text: render `answer`. Detect `[SQL_ROWS]` and replace it with your table UI built from `table_results`; if no rows, drop the marker.
- Citations: render from `citations[]`, using `inline_citations` to map footnotes to entries. Footnote numbers are already embedded in `answer`.
- Table evidence: render `table_results` as a compact table (label/value/unit). Tie the source to the same footnote when the source chunk matches a citation.
- Hide from end users: `route`, `thread_id`, `request_id`, `sql_queries`, `sql_row_count`, `numerical_trace`, and other `answer_metadata` internals; surface them only behind a debug toggle.

## Citation Fields
Each `citations[]` entry includes:
- `doc_id`, `chunk_id`, `snippet`.
- `metadata.document_alias` (fallback: `doc_id`) and `metadata.page` when available.
- `metadata.citation_key` (e.g., `c1`) and `metadata.footnote` (numeric position). Use these to align with inline markers.
- `source_page` / `score`: optional; safe to ignore for rendering.

## Inline Citation Mapping
`answer_metadata.inline_citations[]` provides deterministic mapping between inline markers and `citations[]`:
- Fields: `{placeholder: "DOC_POLICY", citation_index: 0, citation_key: "c1", footnote: 1}` (indices are 0-based into `citations[]`; `footnote` is the rendered number).
- Use this mapping to place superscripts in the UI and to associate table sources with the right citation. When the mapping is absent, fall back to `metadata.footnote`/`citation_key` on `citations[]`.

## SQL / Numeric Evidence
- When `requires_sql=true`, expect `table_results` plus SQL traces. The agent strips inline row dumps after `[SQL_ROWS]`; always render the structured table instead.
- `table_results` rows include `label`, `value`, `unit`, `source_doc`, `source_chunk`, and `raw`. They are duplicated under `numerical_trace.table_results` for debugging.
- `sql_queries` (and the copies under `numerical_trace` or `answer_metadata.sql_trace`) are for developer inspection only; keep them out of the user-facing view unless a debug toggle is active.

## Debugging Fields (do not render by default)
- `numerical_trace` internals (table specs, executor timings, validator output).
- `sql_row_count`, `execution_ms`, planner/executor metadata.
- `route`, `thread_id`, `request_id`, `requires_sql`, model/temperature/mode inside `answer_metadata`.

## Minimal Example (shape only)
```json
{
  "status": "COMPLETED",
  "answer": "The voucher program expanded to five districts [1]. [SQL_ROWS]",
  "thread_id": "thr_x",
  "route": "numerical",
  "requires_sql": true,
  "citations": [
    {
      "doc_id": "...",
      "metadata": {
        "document_alias": "Prod Smoke",
        "page": 1,
        "citation_key": "c1",
        "footnote": 1
      }
    }
  ],
  "answer_metadata": {
    "inline_citations": [
      {
        "placeholder": "DOC_POLICY",
        "citation_index": 0,
        "citation_key": "c1",
        "footnote": 1
      }
    ],
    "sql_trace": {
      "sql_queries": [
        "SELECT ..."
      ]
    }
  },
  "table_results": [
    {
      "label": "Expanded Districts",
      "value": 5,
      "unit": "districts",
      "source_doc": "..."
    }
  ],
  "sql_queries": [
    "SELECT label, value FROM ..."
  ],
  "sql_row_count": 1,
  "numerical_trace": {
    "table_results": [
      {
        "label": "Expanded Districts",
        "value": 5
      }
    ],
    "sql_queries": [
      "SELECT ..."
    ]
  }
}
```

## Rendered Output Walkthrough
- Replace `[SQL_ROWS]` with a rendered table built from `table_results`.
- Keep the numeric footnotes already present in `answer`; map them to `citations[]` via `answer_metadata.inline_citations`. Each superscript should open a hover card (alias + snippet + page) and link to the matching footnote list.
- Table rows should reference the same citation footnotes when `source_doc`/`source_chunk` align with a citation entry.

A concrete, fully rendered example (using the JSON shape above) is shown in [`chat_response_rendering.html`](./chat_response_rendering.html) in this folder. Open it in a browser to see:
- The final `answer` string after substitutions (footnote superscripts, `[SQL_ROWS]` replaced by the evidence table).
- Hoverable citation cards for each footnote.
- A compact evidence table sourced from `table_results`.
 - An accordion that keeps evidence optional, mirroring a chat message with expandable details.
