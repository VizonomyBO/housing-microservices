# AGENTS – Agent API Service

Canonical guide for work inside `services/agent-api`. Follow root `AGENTS.md` plus these service specifics.

## 1) How to Work (Plan → Research → Act → Verify)
- Plans are auto-approved. Before coding, create a plan in the repo root (e.g., `TASK_PLAN_<slug>.md`) with scope, impacted files, risks, ordered steps, and sources; create a matching tracker and keep it current. Delete both when done unless a task says otherwise. Any new task lists/checklists belong under the repo-root `tasks/` directory.
- Research first: consult Context7/web docs for FastAPI, LangGraph, Valkey, Voyage/OpenAI, Pydantic v2, SQLAlchemy, and Compose. Cite sources in the plan when behavior is non-obvious.
- Act within this service; if persistence changes are needed, reuse `packages/shared_data_layer` repositories and follow its AGENTS guide.
- Verify early; run the full suite before calling work review-ready.

## 2) Service Shape & Dependencies
- Runtime: Python 3.13 via `uv`; venv at `services/agent-api/.venv`.
- Responsibilities: LangGraph chat/SSE, retrieval with citations, auth integration, document proxying to ingestion.
- Ingestion is external: `/v1/documents/upload` proxies to the ingestion FastAPI service (`INGEST_BASE_URL`); no inline ingestion.
- Retrieval: hybrid BM25 + vector with Voyage embeddings + reranker required; attachment gating stays until ingestion activates documents.
- Conversation contract: `/v1/chat` enforces authenticated UUID `thread_id`; `allow_stateless=true` skips persistence. Conversation history is paginated (`GET /v1/conversations/{id}`).

## 3) Environment & Commands (uv-first; run from services/agent-api)
| Purpose | Command |
| --- | --- |
| Ensure env | `uv venv --python 3.13 .venv` |
| Sync deps | `uv sync --all-extras` |
| Add dep | `uv add <package>` (use `--dev` for tooling) |
| Lock | `uv lock` |
| Run tools/tests | `uv run <command>` |

Quality gates (run before review-ready):
```bash
uv run ruff format .
uv run ruff check --fix .
uv run ty check .
uv run pytest -n auto
```
Use targeted tests during development (e.g., `uv run pytest tests/http/test_chat_stream.py`). For DB coverage, rely on shared data layer fixtures; do not start Postgres/Compose unless the task requires Compose work explicitly.

## 4) Data Layer & Boundaries
- Use repositories/DTOs from `packages/shared_data_layer`; do not duplicate schemas.
- If schema or repo changes are required, update `packages/shared_data_layer` per its AGENTS guide and run its suite in addition to this service’s tests.
- Keep logical DB separation: `housing` for Agent/shared, `auth_db` for auth/user.

## 5) Runtime Safety (Fail Fast)
- No fallbacks, no mocks/stubs in production or eval paths: require real Voyage/OpenAI, Valkey (unless `ALLOW_IN_MEMORY_VALKEY=1` for tests), rate limiter (bypass only with `ALLOW_RATE_LIMITER_BYPASS=1` for tests), and real ingestion. Surface failures via errors; do not silently degrade.
- Unit tests may patch clients; keep patches in tests/fixtures only.
- Keep attachment safety: documents stay blocked until ingestion activates them; preserve original upload payload when touching workflows/state machines.

## 6) Docs & Task Lists
- Update relevant docs when behavior or contracts change (`docs/agents/implementation.md`, `docs/overview/system_architecture.md`, API docs). Keep any new task lists/checklists under `tasks/`.
- Ignore orchestration helpers meant for humans (`run_tasks.sh`, `RUN_TASKS.md`); rely on the plan/tracker you create.

## 7) Definition of Done
1. Plan + tracker followed (and removed unless a task says otherwise).
2. Quality gates in §3 pass locally; include command summaries in the final response.
3. Schema/repo changes verified in shared data layer tests when touched.
4. Docs updated for user-facing or architectural changes.
5. No stubs/fallbacks added; production paths use real dependencies.

Follow these rules to keep Agent API work predictable, safe, and aligned with the rest of the project.
