# Task 03 — Synchronous Workerless Runtime

## System Snapshot
- Tasks 01–02 enabled reduced-scope flags, enforced text-only ingestion, and exposed synchronous document/pillar endpoints that currently call shared-data-layer repositories directly.
- The original architecture (Epics 5–7) expected SQS/SFN workers housed in `services/agent-worker`; queue-oriented utilities still exist in docs/scripts but should remain dormant for the MVP.
- No CLI/management entry points currently exist inside `services/agent-api` for running ingestion completion or pillar recomputation inline.

## What You Inherit
- ReducedScope settings accessible via FastAPI app state + service modules (Task 01).
- New HTTP endpoints and ingestion helpers (Task 02) that already enforce text-only payloads but still include TODO markers for async queues/export jobs.
- Documentation outlining the legacy async architecture (`docs/infrastructure/async_jobs.md`, `docs/epics/05.md`).

## Goal
Introduce a `ReducedScopeWorkerRuntime` module (and CLI hooks) that executes ingestion completion, pillar generation, and artifact creation synchronously—removing all queue dependencies for the MVP while keeping the old worker code accessible behind feature flags and doc notes.

## Must Read Before Coding
1. `docs/epics/035.md` — Task 3.5.3 scope.
2. `docs/epics/05.md` — Original worker responsibilities + job taxonomy.
3. `docs/infrastructure/async_jobs.md` §2–§4 — SQS/EventBridge assumptions you must temporarily bypass.
4. `docs/interfaces/api_contracts.md` §2.3 & §4 — export + pillar job contracts.
5. `services/agent-api/epic-03/subgraph-acceptance.md` — outlines where ingestion + pillar artifacts are consumed in LangGraph.

## Implementation Scope & Files
- Create `services/agent-api/src/services/reduced_scope_runtime.py` with a `ReducedScopeWorkerRuntime` class exposing synchronous helpers for:
  - `complete_ingestion_job(document_id, payload)` — wraps the ingestion service from Task 02, updates `ingestion_jobs` + `documents` status fields, refreshes any materialized views needed for retrieval.
  - `generate_pillar_answers(country_code | conversation_id)` — calls the pillar service and persists rows in `pillar_answers` + `pillar_answer_sources` via shared_data_layer repositories.
  - `generate_artifact(conversation_id, artifact_type)` — placeholder that writes metadata rows without hitting S3/export queues, logging TODO markers for PDF generation.
- Update HTTP routes + services from Task 02 to call these helpers instead of enqueuing/polling jobs. Ensure they detect reduced-scope mode and `await` the runtime inline before responding.
- Add a CLI entry point (`services/agent-api/src/agent_api/cli.py` + `pyproject` script) exposing commands like `uv run python -m agent_api.cli run-ingestion --document-id ...` so operators can trigger the same helpers manually.
- Comment or feature-flag any existing queue bootstrap logic (`services/agent-worker` references, `docs/infrastructure` instructions) rather than deleting it. Provide README notes on how to re-enable (which env vars, modules, containers) once the demo is over.
- Update docs (`docs/infrastructure/async_jobs.md`, `docs/infrastructure/infrastructure_and_deployment.md`, `docs/epics/05.md` changelog section) describing the reduced-scope runtime, CLI commands, and the steps to restore SQS/SFN later.
- Tests: add coverage for the runtime helpers (`tests/services/test_reduced_scope_runtime.py`), CLI smoke tests (`tests/cli/test_cli_reduced_scope.py`), and HTTP route tests verifying that ingestion/pillar endpoints now block until the synchronous helper returns.

## Step-by-Step Instructions
1. **Implement the runtime helpers**:
   - Build `ReducedScopeWorkerRuntime` with explicit dependencies (DB session, ingestion service, pillar service, logger). Ensure methods reuse shared_data_layer repositories and wrap writes in transactions. Add context managers/tests to confirm `pillar_answers` rows are generated inline and ingestion completions update document state + ingestion job timestamps.
2. **Wire HTTP + CLI entry points**:
   - Add a dependency provider (e.g., `get_reduced_scope_runtime`) in `agent_api/http/deps.py` that instantiates the runtime when reduced scope is enabled. Update document/attachment/pillar routes to call the runtime instead of enqueueing jobs. Create a Typer (or argparse) CLI module so operators can execute `uv run python -m agent_api.cli pillar --conversation-id ...` and document how to run it.
3. **Document fallback + re-enable path**:
   - In `docs/infrastructure/async_jobs.md` and `docs/infrastructure/infrastructure_and_deployment.md`, add a “Reduced Scope” section enumerating which queues are paused, which helpers replaced them, and the exact TODO steps (uncomment worker entry point, restore SQS URLs, switch feature flag) to return to the distributed runtime after the demo.

## Definition of Done
- `ReducedScopeWorkerRuntime` + CLI exist and replace all queue-based ingestion/pillar/export calls inside `services/agent-api`.
- HTTP endpoints now await synchronous helpers and return concrete results; no SQS/EventBridge polling is required for the MVP.
- Documentation clearly calls out how to re-enable async workers after the demo.
- Tests cover runtime helpers, CLI commands, and affected routes; run `uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, and `uv run pytest -n auto`.
- **Handoff Notes**: Execution agent must describe remaining TODO markers for reintroducing queues, list CLI commands added, and summarize any doc updates others should read before Task 04.

## Handoff Notes
- Note where ReducedScopeWorkerRuntime is instantiated (files + dependency names) so Task 04 can reference them when building Docker images.
- Capture any assumptions about local Postgres/Testcontainers required for the runtime so ops docs stay accurate.
- List follow-up items for re-enabling SQS (env vars, modules, doc sections) to keep future reactivation simple.
- Runtime wiring lives in `agent_api/http/deps.py#get_reduced_scope_runtime`; FastAPI routes consume it via `Depends`, and the Typer CLI entry point (`agent_runtime` / `agent_api/cli.py`) exercises the same helpers (`run-ingestion`, `generate-pillars`, `generate-artifact`).
- Local runs still rely on the shared data layer fixtures/Testcontainers; the runtime only assumes `DATABASE_URL` points at the same Postgres instance as FastAPI. No Valkey/Testcontainers changes were required beyond those already documented in Task 02.
- To re-enable queues, flip `REDUCED_SCOPE_ENABLED=0`, restore the `services/agent-worker` processes plus SQS/SFN wiring described in `docs/infrastructure/async_jobs.md`, and remove the reduced-scope guards added to the HTTP routes/CLI so ingestion + pillar requests enqueue jobs again.
