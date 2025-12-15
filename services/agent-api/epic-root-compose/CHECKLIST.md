# Root Compose Modernization Checklist

Complete the tasks in order. Each task should follow the `AGENTS.md` workflow (plan, tracker, research, act, verify, finalize) and update this checklist when finished.

1. - [x] [Task 01 — Deployment Discovery & Compose Plan](tasks/task-01-deployment-discovery.md) — plan captured in `docs/infrastructure/root_compose_plan.md` (includes service inventory, profiles, env/localstack strategy).
2. - [x] [Task 02 — Root Compose Implementation & Service Wiring](tasks/task-02-root-compose.md) — Root compose now orchestrates all services with reduced/full profiles, LocalStack/valkey stubs, and migrated db-init/db-shell helpers; service-specific compose deleted.
3. - [x] [Task 03 — Environment Templates & Runtime Profiles](tasks/task-03-env-and-profiles.md) — Root `.env.example` now documents the complete env schema, service configs read the shared variables, and Compose pulls URLs/LocalStack toggles from `.env`.
4. - [x] [Task 04 — LocalStack & AWS Toggle Integration](tasks/task-04-localstack-toggle.md) — LocalStack-aware helpers, compose/profile updates, smoke script, and env defaults now route AWS clients through LocalStack when `USE_LOCALSTACK=1`.
5. - [x] [Task 05 — Documentation & Developer Workflow Update](tasks/task-05-docs-and-onboarding.md) — README/QUICKSTART now describe the root compose stack (profiles, `.env`, LocalStack, seeding), infra docs/runbooks were refreshed, and a new `docs/runbooks/full_stack_compose.md` was added for full-stack onboarding (2025-12-03).
6. - [x] [Task 06 — Marker-service Full Profile Compose Parity](tasks/task-06-marker-service-compose.md) — marker-service/auth-service/user-service builds now use service-local contexts; LocalStack smoke + `POSTGRES_PORT=5542 docker compose --profile full up --build -d marker-service localstack` logged under `logs/task_06`.
7. - [x] [Task 07 — Telemetry Cache Observability Test Repair](tasks/task-07-telemetry-test-fix.md) — telemetry test now seeds a baseline `pillar_answers` row and scopes assertions to the cache write, eliminating `MultipleResultsFound` failures; QA bundle recorded in `logs/task_07/codex.log`.
