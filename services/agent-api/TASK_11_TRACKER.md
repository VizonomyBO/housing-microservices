# Task 11 Tracker — LangGraph Runner & Ingestion Integration

- [x] Step 1: Re-review LangGraph state/subgraphs, ingestion helpers, and shared data layer modules; document reusable pieces.
- [ ] Step 2: Identify/extract chunking + Voyage embedding helpers; implement clients with retry/backoff + telemetry.
- [ ] Step 3: Implement `LangGraphChatRunner` with SSE streaming + structured error handling.
- [ ] Step 4: Replace reduced ingestion shortcuts with the real pipeline when `use_real_tools` is true; keep text-only fallback.
- [ ] Step 5: Update pillar generation / `ReducedScopeWorkerRuntime` to draw from persisted chunks/vectors.
- [ ] Step 6: Wire runner + ingestion into app startup, removing `UnconfiguredChatRunner` from runtime paths and adding diagnostics logs.
- [ ] Step 7: Expand tests covering runner, ingestion flow, telemetry, and flag fallback.
- [ ] Step 8: Run QA suite (`uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto`).
- [ ] Step 9: Update docs/checklists + handoff notes, then delete plan & tracker.

> Tracker created 2025-12-03 immediately after plan auto-approval; update notes below as work proceeds.
>
> 2025-12-03: Step 1 complete. Repo review confirmed there is still no LangGraph runner (`ChatRunnerProtocol` only backed by `UnconfiguredChatRunner` in `src/agent_api/http/streaming.py`), no answer composer implementations, and no ingestion pipeline that calls Voyage/OpenAI. Starting Step 2 is blocked until those foundational dependencies exist.
>
> 2025-12-03: Step 2 Scope Check — still blocked. Repository lacks any Voyage/OpenAI clients or chunking helpers; `pyproject.toml` has no `langgraph`, `openai`, or `voyageai` dependency, and `packages/shared_data_layer` exposes only ORM models (no ingestion utilities). Implementing runners/clients would require designing entirely new infrastructure, which is out of scope for Task 11 without upstream specs.
