# Task 13 Plan – Enforce SQL/Polars for Numeric Reasoning
_Plan auto-approved per AGENTS.md; per root session constraints keep plan/tracker after completion for continuity._

## Summary
Implement numeric fact extraction and routing so all numeric reasoning flows through the SQL/Polars path. Add an LLM-backed fact extractor for prose attachments, prefer synthesized tables when markdown tables are absent, and have the router auto-set `requires_sql` on numeric cues (digits/arithmetic/KPI/ledger language). Preserve citations and ensure `/scripts/prod_smoke_check.sh` shows `requires_sql:true` for numeric prompts. Scope from `task_prompts/13_numerical_sql_enforcement.md`.

## Impacted files (initial)
- `src/services/langgraph_runner.py` (table builder/fact extraction integration, Polars table wiring)
- `src/nodes/router/router_node.py` (numeric detection + requires_sql behavior)
- `src/subgraphs/numerical/*` (table specs/citations, fallback behavior)
- `tests/*` (router heuristics, fact extractor/table builder tests)
- `scripts/prod_smoke_check.sh` or fixtures if smoke expectations change

## Risks / Watchouts
- Over-eager numeric heuristics could force SQL on non-numeric prompts and degrade answers/perf.
- Fact extractor must retain provenance (doc/chunk) to keep citations intact; avoid hallucinated numbers.
- Table preference changes could regress existing markdown parsing or fail when no numeric rows exist.

## Research (sources)
- Polars DataFrame creation + SQLContext registration for dynamic tables (Context7 Polars docs: /pola-rs/polars DataFrame reference)
- Structured JSON extraction from unstructured text via LLMs (OpenAI structured outputs guide: https://platform.openai.com/docs/guides/structured-outputs)
- Examples of prompting LLMs for structured fact extraction from prose (Simon Willison, 2025-02: https://simonw.substack.com/p/structured-data-extraction-from-unstructured)

## Ordered Steps (auto-approved)
1. Inspect current numeric pipeline: router heuristics, table builder/markdown parsing, numerical subgraph data flow + citations/tests.
2. Research numeric extraction + routing cues; finalize schema (label, value, unit, source_doc, source_chunk/raw) and heuristics for `requires_sql`.
3. Implement LLM-backed numeric fact extractor for prose attachments and integrate into table building (prefer markdown when present, otherwise synthesized facts) with citation metadata.
4. Update router to auto-set `requires_sql` for numeric cues (digits, arithmetic/threshold/KPI/ledger language) and adjust numerical fallback behavior as needed.
5. Extend tests for extractor outputs, router decisions on numeric prompts without tables, and citation/fail-graceful cases.
6. Run quality gates/tests and AWS smoke for numeric prompts; capture evidence and update tracker.
