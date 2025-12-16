# Plan for llm_eval_quality_improvements.md update
*(Auto-approved per AGENTS.md — proceeding immediately.)*

## Summary
- Harden eval + production behavior without shortcuts: no preview-only retrieval or baked eval cases; require real retrieval (vector + BM25/FTS hybrid) with deep citation checks and structured answers.
- Implement retrieval/prompt improvements (HyDE rewrite, numeric-aware rerank, hybrid search) so evals pass at stricter thresholds using `tests/evals/datasets/reduced_e2e_smoke.yaml`.
- Update governance/docs/memory to capture the “no shortcuts, no prompt-embedded evals” rule and hybrid retrieval plan. Keep plan/tracker per AGENTS instructions.

## Potential Impacted Files
- `services/agent-api/src/services/answer_composer.py`
- `services/agent-api/src/nodes/retrieval/*` and related repositories (for hybrid retrieval wiring)
- `services/agent-api/tests/evals/core/*`, `tests/evals/datasets/reduced_e2e_smoke.yaml`
- `docs/testing/llm_eval_quality_improvements.md`, `AGENTS.md`, `.kilocode/rules/memory-bank/context.md`

## Risks / Open Questions
- Need to design hybrid vector + BM25/FTS without disrupting existing DB schema; may require migrations or new index usage.
- Citation validation must remain compatible with frontend rendering (`[id]`, `[SQL_ROWS]`) while tightening checks.
- Ensure changes don’t conflict with ongoing AWS verification tasks.

## References / Research Targets
- HyDE retrieval (Hypothetical Document Embeddings): https://arxiv.org/abs/2212.10496
- Rerankers overview for RAG (Pinecone two-stage retrieval): https://www.pinecone.io/learn/series/rag/rerankers/
- Reciprocal Rank Fusion for hybrid retrieval: https://www.assembled.com/blog/better-rag-results-with-reciprocal-rank-fusion-and-hybrid-search
- Structured outputs / JSON schema guidance: https://medium.com/@deolesopan/structured-outputs-json-schemas-make-your-llms-speak-api-4f22eb5bf3ac
- Postgres hybrid search (pgvector + BM25/FTS/pg_trgm): https://www.postgresql.org/docs/current/textsearch-tables.html
- Internal docs: `docs/testing/llm_eval_suite_proposal.md`, `docs/testing/reduced_e2e_smoke*.md`, `docs/interfaces/chat_response_rendering.html`.
- Voyage reranker API + models: https://docs.voyageai.com/docs/reranker

## Steps (tracker mirrored in TASK_PLAN_PROGRESS.md)
- [x] Governance/docs alignment: update AGENTS/task docs/memory bank + plan/tracker to forbid baked evals and retrieval-lite; require full retrieval + deep citation checks and hybrid plan.
- [x] Replace preview-only retrieval with production retrieval path using hybrid vector + BM25/FTS (schema/index + wiring; avoid eval-side shortcuts).
- [x] Upgrade retrieval models: switch embeddings to `voyage-3-large` and add a Voyage reranker (latest available, e.g., rerank-2.5) over hybrid candidates; re-embed existing chunks via batch utility (no re-upload) and refresh dependent views.
- [x] Diversified fusion: apply coverage-aware fusion (e.g., RRF/MMR with per-document caps and funding/reporting cue boosts) so policy + ledger/reporting chunks surface together without doc hardcoding.
- [ ] Implement HyDE-style rewrite + numeric-aware rerank on top of the real retrieval results (no hardcoded keywords; balanced scoring).
- [ ] Harden citation validation (align markers to retrieved chunk IDs/text; preserve `[id]` and `[SQL_ROWS]`).
- [ ] Improve prompt composition and checklist validation to force inclusion of funding shift + reporting cadence when present (content-based, no doc-name hardcoding).
- [ ] Run/describe `uv run pytest tests/evals -m eval` and document outcomes.
