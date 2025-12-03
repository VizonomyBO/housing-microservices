# Task 11 Tracker — LangGraph Runner & Ingestion Integration

(Tracker created 2025-12-03 immediately after plan auto-approval. Update after each sub-step; delete when task exits review.)

## Checklist
- [x] Step 1: Re-read epic docs & catalog existing LangGraph / ingestion components.
- [ ] Step 2: Design client + ingestion interfaces (OpenAI, Voyage, chunker, telemetry) and decide on shared helper extraction.
- [ ] Step 3: Implement `LangGraphChatRunner` with SSE streaming + retries and tests.
- [ ] Step 4: Replace reduced ingestion shortcut with production pipeline gated by `use_real_tools`.
- [ ] Step 5: Update reduced-scope runtime & pillars to consume stored chunks/vectors.
- [ ] Step 6: Wire runner + ingestion into startup with diagnostics + fallback behavior.
- [ ] Step 7: Expand automated tests for runner, ingestion, flag fallback, telemetry, and rate limits.
- [ ] Step 8: Run QA suite (`uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto`).
- [ ] Step 9: Update docs/checklists + handoff notes, then delete plan & tracker.

## Notes
- 2025-12-03 10:05 PT — Tracker reset to align with new plan after verifying earlier attempt stalled pre-implementation.
- 2025-12-03 10:20 PT — Finished inventory: repo still lacks LangGraph graph definitions, ingestion helpers, or model clients; `pyproject.toml` has no `langgraph`, `openai`, or `voyageai` deps, and DocumentUploadService only stores text chunks with no embeddings.
- 2025-12-03 10:35 PT — Step 2 blocked: no shared ingestion helpers exist in repo or shared_data_layer, and epic docs reference `ArchaaS/lambdas/embedding_writer` code that is not present in this monorepo, so there is nothing to extract or reuse for chunking/Voyage embedding.
