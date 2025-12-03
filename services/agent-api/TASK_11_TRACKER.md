# Task 11 Tracker — LangGraph Runner & Ingestion Integration

- [x] Step 1: Context review of LangGraph state/subgraphs, DocumentUploadService, ReducedScopeWorkerRuntime, ingestion helpers. ✅ Reviewed `src/agent_api/http/streaming.py`, LangGraph node modules, ingestion docs, ArchaaS `embedding_writer`, and shared data layer models to map current reduced-mode shortcuts.
- [ ] Step 2: Extract or implement shared ingestion helpers (chunking, Voyage embeddings, pgvector persistence) inside this service while reusing shared data layer repos.
- [ ] Step 3: Implement LangGraphChatRunner with client wiring, SSE streaming, retries, and telemetry hooks.
- [ ] Step 4: Replace reduced ingestion shortcuts with full pipeline in DocumentUploadService/CLI, gated by `use_real_tools` flag.
- [ ] Step 5: Wire runner + ingestion into app startup and pillar generation, removing `UnconfiguredChatRunner` from real runtime paths.
- [ ] Step 6: Add/extend tests for runner, ingestion flow, flag fallback, telemetry.^
- [ ] Step 7: Run QA suite (`uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto`).
- [ ] Step 8: Update docs/checklists, add handoff notes, delete plan + tracker.

> Tracker initialized 2025-12-03 immediately after plan auto-approval.

> 2025-12-03 update: Step 2+ blocked because the repo lacks any LangGraph builder, LLM client implementations (AnswerComposer, Voyage reranker, OpenAI wrappers), or ingestion pipeline code to reuse. Implementing them would require creating entirely new subsystems with no existing design references beyond high-level docs.
