# Task 11 Tracker

- [x] Step 1: Review epic docs, LangGraph state/nodes, ArchaaS ingestion helpers.
- [ ] Step 2: Extract or map reusable ingestion utilities for chunking/Voyage/pgvector.
- [ ] Step 3: Implement LangGraphChatRunner with context build + SSE streaming + retries/metrics.
- [ ] Step 4: Replace reduced ingestion shortcut with real pipeline in DocumentUploadService + CLI helpers.
- [ ] Step 5: Update ReducedScopeWorkerRuntime/pillar generation to read chunk/vector data.
- [ ] Step 6: Wire runner + ingestion into app startup, remove UnconfiguredChatRunner paths, add diagnostics.
- [ ] Step 7: Add/extend tests for runner, ingestion flow, flag fallback, telemetry.
- [ ] Step 8: Run QA suite (ruff format/check, ty check, pytest -n auto) and record outputs.
- [ ] Step 9: Update checklist/docs/handoff, delete plan + tracker.

> Status 2025-12-03: Blocked on missing LangGraph runner + retrieval/LLM client implementations (see TASK_11_PLAN.md blockers). No code changes performed pending upstream design decisions.
