# Task 07 — Telemetry Cache Observability Test Repair

## System Snapshot
- The reduced/full compose work (Tasks 01–06) is documented, but the standard verification suite still fails.
- `uv run pytest -n auto` currently errors in `tests/telemetry/test_cache_observability.py::test_cache_observability_persists_shared_data_layer_writes` with `sqlalchemy.exc.MultipleResultsFound` when querying `PillarAnswer` (see `logs/task_05/codex.log`).
- Telemetry fixtures rely on seeded data from the shared data layer and reduced-scope seed scripts; Task 05 deferred the fix.

## What You Inherit
- Existing telemetry code/tests: `services/agent-api/tests/telemetry/test_cache_observability.py`, any related fixtures under `tests/` and `packages/shared_data_layer`.
- Seed data and repositories referenced by the test (`packages/shared_data_layer`, `services/agent-api/scripts/seed_reduced_scope_data.py`).
- Assessment + logs (`ROOT_COMPOSE_ASSESSMENT.md`, `logs/task_05/codex.log`) noting the exact failure message.

## Goal
Restore the telemetry cache observability test so the standard QA bundle (`uv run ruff format/check`, `uv run ty check`, `uv run pytest -n auto`) passes. Root cause likely lies in duplicated `PillarAnswer` rows (multiple seeds or query assumptions); the fix should make the test deterministic without hiding legitimate issues.

## Must Read / Inspect
1. `tests/telemetry/test_cache_observability.py` (understand expectations and fixtures).
2. `services/agent-api/src/agent_api/telemetry/*` modules referenced by the test.
3. Seed scripts + shared data layer repositories (especially anything inserting pillar answers).
4. `logs/task_05/codex.log:4931` and related entries describing the failure stack trace.
5. `ROOT_COMPOSE_ASSESSMENT.md` to understand why this blocks the epic definition of done.

## Implementation Scope & Deliverables
- Identify why multiple `PillarAnswer` rows are returned: duplicated seed data, missing filters, or repository query issues.
- Adjust seeds, fixtures, or repository logic so the test enforces the intended behavior (one answer per conversation/pillar) without making overly brittle assumptions.
- If seed data is updated, ensure reduced-scope demos still work (rerun seeding script or migration if needed).
- Maintain or add targeted unit tests covering the new behavior (e.g., verifying repository filters or fixture adjustments).
- Update docs or handoff notes if telemetry behavior changes.

## Step-by-Step Instructions
1. Reproduce the failure locally (`uv run pytest tests/telemetry/test_cache_observability.py -k persists_shared_data_layer_writes`). Capture the stack trace in the tracker/log.
2. Inspect the failing query + dataset to determine the duplication source (seed scripts vs test fixtures vs repository filter).
3. Implement a fix (e.g., adjust fixture factories, limit query by ID, or de-duplicate seeds). Include concise comments if logic changes.
4. Rerun the targeted test to confirm it passes.
5. Execute the full QA suite from `services/agent-api` per `AGENTS.md`:
   - `uv run ruff format .`
   - `uv run ruff check --fix .`
   - `uv run ty check .`
   - `uv run pytest -n auto`
6. Update `logs/task_07` with relevant commands/output and note any remaining risks.
7. Remove plan/tracker files after completion.

## Definition of Done
- Root cause documented in the task log.
- `tests/telemetry/test_cache_observability.py::test_cache_observability_persists_shared_data_layer_writes` passes consistently.
- Full QA bundle succeeds; outputs captured for review.
- Any data/fixture/doc changes keep reduced/full demos functioning (rerun seeding if modified).
- Plan/tracker removed, checklist updated, and handoff notes capture insights for future telemetry work.

## Handoff Notes
- If the fix depends on new seed ordering or unique constraints, document it so future migrations/tests stay aligned.
- Flag any remaining telemetry gaps discovered during the investigation.
- Task 06 moved marker-service/auth-service/user-service builds to service-local contexts so the `full` profile now starts successfully; see `logs/task_06/codex.log` for the latest compose runs and reuse the `POSTGRES_PORT=5542` override if your host already binds 5432 when running Docker Compose QA.
- Telemetry QA now seeds a placeholder `pillar_answers` row inside `tests/telemetry/test_cache_observability.py` and narrows assertions to the cache write (document ID + owner + pillar route + summary text). Keep these filters in sync if cache routes or pillar naming change, otherwise the deterministic guard will fail again.
