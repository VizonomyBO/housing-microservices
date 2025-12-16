# Progress Tracker — LLM eval quality improvements
Steps mirror TASK_PLAN.md; keep in sync.

- [x] Governance/docs alignment: update AGENTS/task docs/memory bank + plan/tracker to forbid baked evals and retrieval-lite; require full retrieval + deep citation checks and hybrid plan.
- [x] Replace preview-only retrieval with production retrieval path using hybrid vector + BM25/FTS (schema/index + wiring; avoid eval-side shortcuts).
- [x] Upgrade retrieval models: switch embeddings to `voyage-3-large` and add a Voyage reranker (latest available, e.g., rerank-2.5) over hybrid candidates; re-embed existing chunks via batch utility (no re-upload) and refresh dependent views.
- [x] Diversified fusion: apply coverage-aware fusion (e.g., RRF/MMR with per-document caps and funding/reporting cue boosts) so policy + ledger/reporting chunks surface together without doc hardcoding.
- [ ] Implement HyDE-style rewrite + numeric-aware rerank on top of the real retrieval results (no hardcoded keywords; balanced scoring).
- [ ] Harden citation validation (align markers to retrieved chunk IDs/text; preserve `[id]` and `[SQL_ROWS]`).
- [ ] Improve prompt composition and checklist validation to force inclusion of funding shift + reporting cadence when present (content-based, no doc-name hardcoding).
- [ ] Run/describe `uv run pytest tests/evals -m eval` and document outcomes.
