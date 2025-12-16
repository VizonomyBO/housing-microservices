# Task: Refresh Tests/CI for the Revamped Stack

Follow `.kilocode/rules/memory-bank-instructions.md` and `AGENTS.md`; create/update a plan + tracker in the repo root. Use service-specific AGENTS when touching those packages.
The agent must commit the changes before terminating the task.
Once the task is done, mark this as completed in the title

## Objective
- Update lint/type/test/eval tooling and scripts to reflect the new cache-free, text-only voyage-context-3 architecture across services.

## Scope
- Review quality gates (`uv run ruff format/check`, `ty`, `pytest`, smoke helpers) and adjust configs/scripts to drop Valkey/rate-limiter/Lambda/Step Functions/reduced-scope assumptions; ensure new ReAct/Pyodide tooling and ingestion pipelines are covered.
- Update test fixtures/mocks for agent/ingestion/shared data layer/auth/user to match new defaults (voyage-context-3 dims, no cache backend, LocalStack dev). Remove or rewrite tests tied to LangGraph graph planner, cache observability, Step Functions, or legacy compose profiles.
- Align any automation (Makefile, scripts, CI if present) to run the correct services/tests for dev/prod, including updated smoke/eval flows.

## Deliverables
- Cleaned test/CI/tooling configs without legacy cache/graph/Lambda dependencies, with coverage for the new ReAct agent, text-only ingestion, and updated schemas.
- Updated docs/readmes for running the revised quality gates.

## References
- `docs/requirements_revamp.md`
- `.kilocode/rules/memory-bank/*.md`, `AGENTS.md`, service-specific AGENTS as applicable
