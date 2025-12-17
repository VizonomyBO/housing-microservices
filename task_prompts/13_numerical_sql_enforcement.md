# Task 13 – Enforce SQL/Polars for all numeric reasoning

> **Revamp note:** Use the ReAct agent stack (BM25 + pgvector with voyage-context-3, `rerank-2.5`, Pyodide tool for calculations) and the ingestion-first flow. Graph/planner/cache/Step Functions/reduced-scope features are deprecated; keep grounding/citations strict.

## Objective
Force the agent to route any numeric reasoning through the SQL/Polars toolchain, even when the source is prose rather than a formal table. Add an LLM-backed numeric fact extractor that lifts numbers from attached documents into an ephemeral table and have the router treat any numeric signal as `requires_sql=true` so Polars executes all arithmetic/aggregations. No manual hints; behavior must mirror production.

## Requirements
- Add a numeric fact extraction step (LLM) that produces a structured table (label, value, unit, source_doc, source_chunk/raw) from attached document text when no markdown table is present.
- Router: automatically set `requires_sql=true` for numeric queries (digits, arithmetic language, thresholds, KPI/ledger cues), regardless of manual hints.
- Numerical pipeline: use the extracted table(s) (or parsed markdown tables when present) for Text→SQL→Polars execution; fail gracefully if no table rows are available.
- Preserve citations: answers must still cite originating docs/chunks, even when using synthesized tables.
- Smoke coverage: `/scripts/prod_smoke_check.sh` should show `requires_sql:true` for ledger/KPI-style prompts with the new PDFs.

## Deliverables
- Code: numeric fact extractor node/function; router updates; table builder preference for LLM facts; enhanced heuristic SQL generation if needed.
- Tests: add/extend unit coverage for the extractor and router deciding `requires_sql` on numeric prompts without tables.
- Validation: rerun AWS smoke to prove `requires_sql:true` for numerical questions; capture logs/IDs in tracker.

## Notes
- No manual hints/flags in requests—detection must be automatic.
- Keep existing attachment safety and ingestion paths untouched; this change only affects the reasoning route once docs are attached.
