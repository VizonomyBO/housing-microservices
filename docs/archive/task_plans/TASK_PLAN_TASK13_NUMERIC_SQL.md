# Task Plan – Task 13: Enforce SQL/Polars for Numeric Reasoning
_Plan auto-approved per AGENTS.md; keep plan/tracker files in place after completion so the next session can resume quickly._

## Summary
Ensure all numeric reasoning routes through the SQL/Polars path by adding an LLM-backed numeric fact extractor for prose attachments, forcing the router to set `requires_sql=true` on numeric cues, and wiring synthesized tables into the Text→SQL→Polars pipeline with citation preservation. Aligns with `task_prompts/13_numerical_sql_enforcement.md`.

## Impacted files (initial)
- `services/agent-api` router/graph (numeric routing, SQL hints)
- `services/agent-api` ingestion/table builder for attached docs (LLM fact extraction, table preference order)
- `services/agent-api` tests (router heuristics, extractor/table pipeline)
- `scripts/prod_smoke_check.sh`, related fixtures/logs for numerical prompts

## Risks / Watchouts
- Over-broad `requires_sql` heuristics could force SQL on non-numeric chats and degrade quality/perf.
- Fact extractor must preserve citations and avoid hallucinated values; needs fallback when no numeric rows are found.
- Table merge order could regress existing markdown-table parsing if not carefully prioritized.

## Research (sources)
- Polars DataFrame creation from dictionaries and SQLContext registration patterns (Context7 Polars docs: /pola-rs/polars DataFrame reference, examples for `pl.DataFrame` creation)
- Structured LLM output for JSON extraction from unstructured text (OpenAI structured outputs guide: https://platform.openai.com/docs/guides/structured-outputs)
- Patterns for instructing LLMs to emit JSON from prose (Simon Willison on structured data extraction: https://simonw.substack.com/p/structured-data-extraction-from-unstructured)

## Ordered Steps (auto-approved)
1. Inspect current numeric pipeline: router intent handling, Text→SQL builder, attachment parsing, and citation flow; note existing tests/fixtures.
2. Research numeric extraction + SQL routing cues (Polars/LLM refs) and finalize detection heuristics and table schema (label, value, unit, source fields).
3. Implement numeric fact extractor for prose attachments (LLM call) producing structured rows with source doc/chunk, and integrate into table-building preference (use markdown tables when present, otherwise LLM facts); ensure citation metadata is retained.
4. Update router to auto-set `requires_sql=true` on numeric cues (digits/arithmetic/threshold/KPI/ledger language) without manual hints; adjust SQL generation fallback if needed.
5. Extend tests for extractor outputs and router `requires_sql` decisions on numeric prompts without markdown tables; add coverage for citation preservation/fail-gracefully when no rows.
6. Run quality gates/tests; run AWS smoke (ledger/KPI prompts) to verify `requires_sql:true` and capture evidence; update tracker.
