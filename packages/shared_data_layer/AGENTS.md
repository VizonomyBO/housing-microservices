# AGENTS – Shared Data Layer

Authoritative guide for `packages/shared_data_layer`. Follow root `AGENTS.md` plus the specifics here.

## 1) How to Work (Plan → Research → Act → Verify)
- Plans are auto-approved. Before coding, create a plan in the repo root (e.g., `TASK_PLAN_<slug>.md`) with scope, impacted files, risks, ordered steps, and sources; create a matching tracker and keep it updated. Delete both when done unless the task explicitly says otherwise. If you create task lists/checklists, place them under `tasks/` in the repo root.
- Research first: consult Context7/web docs for `ltree`, `pgvector`, SQLAlchemy, Testcontainers, Polyfactory, etc. Cite links in the plan.
- Act from within `packages/shared_data_layer`; keep changes scoped to this package unless a task requires cross-package work.
- Verify early and often; run the full suite before calling work review-ready.

## 2) Environment & Commands (pwd = packages/shared_data_layer)
| Purpose | Command |
| --- | --- |
| Install deps | `uv sync --all-extras` |
| Formatter | `./.venv/bin/ruff format .` |
| Lint (auto-fix) | `./.venv/bin/ruff check --fix .` |
| Type check | `./.venv/bin/ty check .` |
| Full test suite | `./.venv/bin/pytest -n auto` |
| Single test | `./.venv/bin/pytest tests/path/to/test.py::test_name` |
| Migration smoke | `./.venv/bin/pytest tests/test_migrations.py -s` |

Testing tips: run targeted tests first; disable `-n auto` when debugging races; capture flaky cases with `pytest -k pattern --maxfail=1 -vv`. Do not start Docker/Compose manually—pytest manages Testcontainers.

## 3) Definition of Done
All must pass locally (only the known `chunks.text_tsv` warning acceptable):
1. `./.venv/bin/ruff format .`
2. `./.venv/bin/ruff check --fix .`
3. `./.venv/bin/ty check .`
4. `./.venv/bin/pytest -n auto`
Summarize commands/results in your final response.

## 4) Architecture Notes & Patterns
- Extensions: `pgcrypto`, `ltree`, `vector`, `pg_trgm`.
- Schema lives in `src/shared_data_layer/migrations/versions/000000000001_initial.py`; extend there unless a task mandates a new revision.
- Maintenance/procedures: expose via `shared_data_layer/db/maintenance.py` or `shared_data_layer/db/procedures.py`; repositories should call helpers, not raw `text(...)`.
- Stored procedure `workflow_nodes_move_subtree(graph_id UUID, source_path ltree, target_parent_path ltree)` must cast outputs to `ltree`.
- Triggers are minimal; prefer ORM/event hooks in `shared_data_layer/db/events.py` to refresh materialized views (`active_chunks`, `graph_edge_evidence_rollup`, `graph_hot_entities`, etc.) only when sources change.
- ORM: avoid lazy-load after session close; use `selectinload`/`joinedload` before serializing. Use LTREE shim `shared_data_layer/db/ltree.py`; avoid `sqlalchemy_utils`.
- Testing: use factories in `shared_data_layer/testing/factories/...`; fixtures (`event_loop`, `postgres_container`, `engine` session-scoped; `db_session` function-scoped). `tests/test_end_to_end_ingestion.py` is the ingestion smoke—update when ingestion/doc/graph flows change.
- Common fixes: cast `::ltree` to avoid type errors; ensure embeddings are non-empty; stop local Postgres if Testcontainers hangs.

## 5) Runtime Safety & Boundaries
- No fallbacks/mocks/stubs in production or eval paths; fail fast and surface real errors. Test-only patches belong in tests/fixtures.
- Keep DB separation: do not introduce schemas for other services here without coordination; shared data layer is authoritative for models/repos used by Agent API.
- Do not run ad-hoc Docker/Compose; let pytest manage containers.

## 6) Source Map (high-value files)
- `src/shared_data_layer/db/models/*`
- `src/shared_data_layer/db/events.py`, `maintenance.py`, `procedures.py`
- `src/shared_data_layer/migrations/versions/000000000001_initial.py`
- `src/shared_data_layer/testing/*`
- `tests/test_*.py`

Update this guide when architecture changes so future agents inherit accurate instructions.
