# Root Compose Modernization Checklist

Complete the tasks in order. Each task should follow the `AGENTS.md` workflow (plan, tracker, research, act, verify, finalize) and update this checklist when finished.

1. - [x] [Task 01 — Deployment Discovery & Compose Plan](tasks/task-01-deployment-discovery.md) — plan captured in `docs/infrastructure/root_compose_plan.md` (includes service inventory, profiles, env/localstack strategy).
2. - [x] [Task 02 — Root Compose Implementation & Service Wiring](tasks/task-02-root-compose.md) — Root compose now orchestrates all services with reduced/full profiles, LocalStack/valkey stubs, and migrated db-init/db-shell helpers; service-specific compose deleted.
3. - [x] [Task 03 — Environment Templates & Runtime Profiles](tasks/task-03-env-and-profiles.md) — Root `.env.example` now documents the complete env schema, service configs read the shared variables, and Compose pulls URLs/LocalStack toggles from `.env`.
4. - [ ] [Task 04 — LocalStack & AWS Toggle Integration](tasks/task-04-localstack-toggle.md)
5. - [ ] [Task 05 — Documentation & Developer Workflow Update](tasks/task-05-docs-and-onboarding.md)
