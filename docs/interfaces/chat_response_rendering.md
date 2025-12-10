# Chat Response Parsing & Citation Rendering (Frontend Guide)

This guide explains how clients should parse chat responses (blocking or SSE `done` payloads) and render citations. It complements the `/v1/chat` contracts in `api_contracts.md` and focuses on the `done` envelope seen in blocking responses or the final SSE frame.

## What to Display
- Use `done.answer` as the primary user-facing text. It may contain inline markers like `[SQL_ROWS]` where structured evidence should be inserted, but inline SQL row dumps are stripped server-side. `DOC_*` markers from the model are normalized to numeric footnotes aligned to `citations`.
- Citations should be rendered from `done.citations` (authoritative list) and, when present, `done.table_results` for numeric/table evidence.
- Inline mapping: when `DOC_*` markers appear, the agent replaces them with numeric footnotes and publishes `done.answer_metadata.inline_citations` (array of `{placeholder, citation_index, citation_key, footnote}`) so clients can deterministically map footnotes to `citations[]`. The mapping is built server-side by aligning placeholders to document aliases/IDs (not LLM order), and each citation carries `metadata.citation_key` (e.g., `c1`) and `metadata.footnote` (numeric). You’ll see this in blocking responses under `done.answer_metadata.inline_citations`; for SSE, the same field is present on the final `done` frame.

## Citation Fields (authoritative list)
Each `done.citations[]` entry includes:
- `doc_id`: source document identifier.
- `chunk_id`: specific chunk identifier.
- `snippet`: short preview text to show in hover/tooltip.
- `metadata.document_alias`: human-friendly document name (fallback to `doc_id` if missing).
- `metadata.page`: page number when available; omit page text when `null`.
- `metadata.citation_key`: stable key assigned server-side (e.g., `c1`, `c2`), matching `inline_citations[].citation_key`.
- `metadata.footnote`: numeric position used in the rendered footnotes (1-based, excludes SQL pseudo-citations).
- `source_page`/`score`: often `null`; safe to ignore in UI.

## SQL/Numeric Evidence
- When `requires_sql=true`, numeric evidence is returned in `done.table_results` (and echoed inside `numerical_trace.table_results`).
- The `[SQL_ROWS]` marker inside `answer` is a hint to replace or augment with a rendered table built from `table_results`. Inline bullet dumps are removed by the agent; rely on the structured table instead. `DOC_*` placeholders are converted to numbered footnotes server-side; render them using `citations[]` ordering.
- `sql_queries` show the executed SQL; they are useful for debugging but typically hidden from end users. Raw chunk IDs should not appear in user-facing text; use the structured fields only.

## Rendering Rules
- Main text: render `answer`, removing or replacing the `[SQL_ROWS]` marker with your table UI. Do not expect inline row dumps after the marker.
- Footnotes: render the numeric markers already present in `answer` and map them to `citations[]` using `answer_metadata.inline_citations` (preferred). Each `inline_citations[]` entry gives you the placeholder (`DOC_*`), the `citation_index` into `citations[]`, a `citation_key`, and the rendered `footnote` number. Citations themselves also include `metadata.citation_key`/`metadata.footnote` for direct lookup.
- Hover/tooltip: show `snippet` plus alias/page; include `doc_id` only when alias is missing.
- Table evidence: render `table_results` as a compact table with columns `label`, `value`, `unit`, `source_doc` (or alias if you map IDs to names). Keep the association to the same footnote index used for the citation that produced the table when applicable.
- Logging only (not user-facing): `thread_id`, `request_id`, `route`, `numerical_trace` internals, `sql_row_count`, `execution_ms`, `validator`.

## Inline `[SQL_ROWS]` behavior
Inline bullet dumps after `[SQL_ROWS]` are suppressed by the agent. Clients should:
- Detect `[SQL_ROWS]` in `answer` and replace/remove the marker with a rendered table built from `table_results`.
- If `table_results` is empty, simply drop the marker; do not render raw chunk IDs or row dumps inside `answer`.

## Example Raw Response (all citation types)
Below is a blocking response example showing textual and SQL-derived citations.

```json
{
  "thread_id": "thr_demo_123",
  "request_id": "viz-abc123",
  "done": {
    "status": "COMPLETED",
    "answer": "Housing subsidies tightened after 1988 reforms [1]. The KPI table shows District 9 stability at 88 and arrears of 118 households [2]. [SQL_ROWS]",
    "route": "numerical",
    "requires_sql": true,
    "citations": [
      {
        "doc_id": "8b72ef40-39eb-4871-a115-e3085f3cf5e0",
        "chunk_id": "7d507d06-7b20-4dc1-a2ac-a680ec89ee90",
        "snippet": "The Measurement, Control and Targeting of Housing Finance Subsidies: The Case of Argentina...",
        "source_page": null,
        "score": null,
        "metadata": {
          "document_alias": "ARG Housing Subsidies 1988",
          "page": 1
        }
      },
      {
        "doc_id": "f16d97ae-6423-4497-8185-86e86874603e",
        "chunk_id": "12d0ac9d-e977-470c-9d4b-03847074d61a",
        "snippet": "118 renter households carry >$1,200 in arrears; District 9 stability score is 88...",
        "source_page": null,
        "score": null,
        "metadata": {
          "document_alias": "District 9 Relief Ledger",
          "page": 1
        }
      }
    ],
    "sql_queries": [
      "SELECT label, value, unit, source_doc, source_chunk, raw FROM arg_prod_smoke_demo"
    ],
    "table_results": [
      {
        "label": "Housing Stability Score",
        "value": 88,
        "unit": "",
        "source_doc": "f16d97ae-6423-4497-8185-86e86874603e",
        "source_chunk": "12d0ac9d-e977-470c-9d4b-03847074d61a",
        "raw": "Housing Stability Score | 88"
      },
      {
        "label": "Households in arrears > $1,200",
        "value": 118,
        "unit": "",
        "source_doc": "f16d97ae-6423-4497-8185-86e86874603e",
        "source_chunk": "12d0ac9d-e977-470c-9d4b-03847074d61a",
        "raw": "Households in arrears > $1,200 | 118"
      }
    ],
    "sql_row_count": 2
  },
  "messages": [
    {
      "role": "assistant",
      "content": "Housing subsidies tightened after 1988 reforms [1]. The KPI table shows District 9 stability at 88 and arrears of 118 households [2]. [SQL_ROWS]"
    }
  ]
}
```

### How to Render the Example
- **Answer text:** Display the `answer` string; replace `[SQL_ROWS]` with a small table built from `table_results`.
- **Citations:** Render two footnotes. Footnote 1 → alias “ARG Housing Subsidies 1988” (page 1) with the provided snippet. Footnote 2 → alias “District 9 Relief Ledger” (page 1) with its snippet. Use superscripts inline `[1] [2]` in the answer.
- **Table:** Show a two-row table labeled “Evidence” with columns `label`, `value`, `unit` (optional), and a source indicator pointing to citation [2] (since both rows come from the same chunk).
- **Hide from users:** `route`, `sql_queries` (unless showing a debug toggle), `sql_row_count`, and any `numerical_trace` fields if present.
