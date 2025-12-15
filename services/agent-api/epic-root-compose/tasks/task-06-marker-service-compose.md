# Task 06 — Marker-service Full Profile Compose Parity

## System Snapshot
- The root `docker-compose.yml` now defines every service with shared build anchors (`context: .`), reduced/full profiles, and LocalStack wiring (Tasks 01–05 complete).
- Marker-service still reuses the original Dockerfile that assumes a service-local build context (`COPY requirements.txt .`). When `docker compose --profile full run --no-deps --rm marker-service …` runs, the build fails because the file is copied from the wrong path (`logs/task_04/codex.log`).
- Because of that failure, the `full` profile (which should include marker-service + LocalStack) has never been validated end-to-end.

## What You Inherit
- Root compose + env assets: `docker-compose.yml`, `.env.example`, LocalStack network setup.
- Marker-service sources: `services/marker-service/Dockerfile`, `main.py`, `aws_runtime.py`, `scripts/localstack_smoke.py`, and `requirements.txt`.
- Assessment notes in `ROOT_COMPOSE_ASSESSMENT.md` describing the exact breakage.
- Prior task logs under `logs/task_04/` documenting attempted compose runs.

## Goal
Make the marker-service container buildable/run-able from the root compose stack so that `COMPOSE_PROFILES=full docker compose --profile full up marker-service localstack` succeeds. Preserve the existing runtime behavior (LocalStack-aware settings, env injection, smoke script) while ensuring the build context mismatch is resolved.

## Must Read / Inspect
1. `docker-compose.yml` (marker-service + LocalStack service definitions).
2. `services/marker-service/Dockerfile` and `.dockerignore`.
3. `services/marker-service/requirements.txt`, `main.py`, and helper modules.
4. `ROOT_COMPOSE_ASSESSMENT.md` and `logs/task_04/codex.log:6718-6768` for historical context.
5. Existing task instructions in `epic-root-compose/tasks` (follow the same workflow + verification commands from `AGENTS.md`).

## Implementation Scope & Deliverables
- Adjust the build pipeline so the Dockerfile sees the correct files when invoked from the repo root. Options include overriding the compose build context to `services/marker-service` or updating the Dockerfile COPY paths—document the reasoning.
- Ensure marker-service still installs dependencies (`requirements.txt`) and copies application sources exactly once; avoid duplicating the entire repo if only service files are needed.
- Update supporting docs if instructions mention workarounds or broken builds.
- Provide a LocalStack smoke validation inside the container (e.g., `docker compose --profile full run --no-deps --rm marker-service python scripts/localstack_smoke.py`) after the fix.
- Keep the broader stack untouched except for what is necessary to restore the build.

## Step-by-Step Instructions
1. Confirm the current failure by inspecting the logs (no need to rerun the broken command unless helpful).
2. Choose and implement a fix for the build context (compose override vs Dockerfile path updates). If touching compose, ensure other services keep using the shared build anchor.
3. Rebuild marker-service via Docker Compose, ensuring LocalStack dependency wiring remains intact.
4. Run the LocalStack smoke script from inside the container (`docker compose --profile full run --no-deps --rm marker-service python scripts/localstack_smoke.py`).
5. Bring up marker-service + LocalStack with `docker compose --profile full up --build marker-service localstack` (can be short-lived; tear down afterward) to prove profile parity.
6. Run standard quality gates from `services/agent-api` per `AGENTS.md` (format, lint, type check, pytest) if any shared files were touched.
7. Update relevant documentation/logs, then clean up plan/tracker files.

## Definition of Done
- Marker-service builds successfully from the root compose stack without manual venv hacks.
- `docker compose --profile full run --no-deps --rm marker-service python scripts/localstack_smoke.py` succeeds and logs bucket output (even if empty).
- `docker compose --profile full up --build marker-service localstack` starts both services (you may Ctrl+C afterward, but capture evidence in the task log).
- Any docs referencing the failure are updated or annotated with the fix.
- Standard verification commands run successfully; outputs recorded in the final report.
- Plan + tracker removed; `logs/task_06` contains the CLI history.

## Handoff Notes
- If the fix required altering the shared build anchor, document the change so other services can follow the same pattern.
- Note any lingering issues (e.g., long build times, large contexts) that future tasks should consider optimizing.
