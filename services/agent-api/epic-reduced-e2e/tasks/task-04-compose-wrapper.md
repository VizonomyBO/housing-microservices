# Task 04 — Compose Wrapper & CI Integration

## System Snapshot
- Tasks 01–03 produced the scenario plan, fixtures, and the CLI automation script.
- Running the CLI still requires several manual steps (starting Compose, exporting env vars, exec’ing into the container).
- There is no Make/CI target to guarantee the reduced profile + LocalStack are up before the script runs, nor a teardown/cleanup routine.

## What You Inherit
- CLI script `services/agent-api/scripts/run_reduced_e2e_smoke.py` with tests.
- Root compose stack and runbooks describing reduced/full profiles.
- `run_tasks.sh` orchestration that expects tasks to be self-contained and sequential.

## Goal
Package the CLI into an operator-friendly workflow that can be executed locally or in CI with a single command. This includes:
- A bash wrapper that starts the reduced stack (postgres, db-init, agent-api, auth-service, user-service, LocalStack), waits for health checks, runs the CLI inside the `agent-api` container, and tears down the stack unless `KEEP_STACK=1`.
- A Makefile target (e.g., `make reduced-e2e-smoke`) that invokes the wrapper.
- Optional GitHub Actions job template or documentation snippet so CI can run the same command.

## Must Read / Inspect
1. `docs/runbooks/reduced_scope_demo.md` for the expected services/profiles.
2. CLI usage instructions from Task 03.
3. Existing scripts in `services/agent-api/scripts/` for style (e.g., `verify_reduced_scope_compose.sh`).

## Implementation Scope & Deliverables
- Add `services/agent-api/scripts/run_reduced_e2e_compose.sh` that:
  - Copies `.env.example` → `.env` if missing (warns before overwriting).
  - Starts the reduced stack with LocalStack (e.g., `STACK_PROFILE=reduced COMPOSE_PROFILES=reduced,aws-mock docker compose --profile reduced up --build -d postgres db-init agent-api auth-service user-service localstack`).
  - Waits for health endpoints (`/health`, `/v1/health`) before running the CLI via `docker compose --profile reduced exec agent-api uv run python scripts/run_reduced_e2e_smoke.py --output /app/logs/reduced_e2e_smoke.json`.
  - Captures exit codes, streams logs to `services/agent-api/logs/task_XX/codex.log` when run via Codex (use `tee`), and tears down the stack unless `KEEP_STACK=1`.
- Update the repo `Makefile` with a `reduced-e2e-smoke` target calling the new script from repo root.
- If relevant, add a CI example (e.g., `docs/testing/reduced_e2e_smoke_plan.md` section) or GitHub Actions snippet referencing the Make target.
- Update `epic-reduced-e2e/CHECKLIST.md` accordingly.

## Step-by-Step Instructions
1. Prototype the wrapper script locally, ensuring it respects env overrides (ports, AWS creds) and stops on failure.
2. Add helper functions for health checks (curl with retries) inside the script.
3. Update `Makefile` and document the new target in `README.md` (brief mention; Task 05 will expand docs further if needed).
4. If CI automation is required, provide a workflow snippet or doc excerpt so future engineers can wire it into GitHub Actions/GitLab.
5. Run the standard QA suite plus an actual smoke run (optional but recommended) to confirm everything works end-to-end.
6. Mark the checklist entry complete and capture any issues in Handoff Notes.

## Definition of Done
- Wrapper script + Make target exist and can run the CLI with one command.
- Script handles startup, health probing, CLI execution, and teardown, honoring `KEEP_STACK`.
- README (or appropriate doc) briefly mentions the new command so Task 05 can build on it.
- QA commands succeed.

## Handoff Notes
- Note any flakiness (e.g., services needing longer warm-up) so Task 05 can document prerequisites/troubleshooting.
