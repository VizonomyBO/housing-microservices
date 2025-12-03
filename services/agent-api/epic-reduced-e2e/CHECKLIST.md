# Reduced E2E Smoke Epic – Checklist

Complete the tasks in order. Each task must follow `services/agent-api/AGENTS.md` (plan → tracker → research → act → verify → finalize). When a task changes the scope of another, update this checklist immediately so future agents don’t duplicate work.

_Run these tasks sequentially via:_ `./run_tasks.sh --epic epic-reduced-e2e`

_Automated loop available:_ `./run_epic_loop.sh --epic epic-reduced-e2e` re-reads this checklist after each run so newly inserted fix tasks are executed automatically.

## Important
> Since the new code you'll write will be located at `services/agent-api/scripts/`, create a new uv venv with python 3.13 and manage all dependencies for the scripts there in all the tasks of this checklist.

1. - [x] [Task 01 — Reduced Stack E2E Test Plan](tasks/task-01-reduced-e2e-plan.md) *(2025-12-03: Auth+doc scenario plan documented in `docs/testing/reduced_e2e_smoke_plan.md`; follow that spec before tackling Task 02.)*
2. - [x] [Task 02 — Scenario Fixtures & Helper Modules](tasks/task-02-fixtures-and-helpers.md) *(2025-12-03: Added `tests/data/reduced_e2e` markdown docs + manifest, new `scripts/reduced_e2e_fixtures.py`, and tests in `tests/scripts/test_reduced_e2e_fixtures.py`. Task 03 can import the loader to bootstrap uploads + prompt metadata; scenario remains per `docs/testing/reduced_e2e_smoke_plan.md`.)*
3. - [x] [Task 03 — Reduced E2E CLI Automation](tasks/task-03-e2e-cli.md) *(2025-12-03: Added `scripts/reduced_e2e_smoke/` package, Typer CLI shim `scripts/run_reduced_e2e_smoke.py`, and mocked tests in `tests/scripts/test_run_reduced_e2e_smoke.py`; next task can call the CLI via Compose wrapper.)*
4. - [x] [Task 04 — Compose Wrapper & CI Integration](tasks/task-04-compose-wrapper.md) *(2025-12-03: Added `scripts/run_reduced_e2e_compose.sh`, new `make reduced-e2e-smoke` target, README + testing plan updates, and CI snippet. Task 05 should expand docs/troubleshooting based on wrapper behavior.)*
5. - [ ] [Task 05 — Documentation & Production Compose Guide](tasks/task-05-docs-and-prod.md)
