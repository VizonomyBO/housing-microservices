# Epic 3.5 Task Checklist

Complete tasks sequentially.

1. - [ ] [Task 01 — Reduced Scope Gateway & Text-only Streaming](tasks/task-01-reduced-scope-gateway.md) — Add ReducedScope settings, no-op rate limiter, text-only routing, and SSE/demo-mode guards so `/v1/chat` runs without Valkey, vision, or table payloads.
2. - [ ] [Task 02 — Text-only Document, Attachment & Pillar APIs](tasks/task-02-text-only-apis.md) — Restrict uploads/attachments to markitdown text, auto-complete ingestion jobs, and expose JSON-only pillar endpoints.
3. - [ ] [Task 03 — Synchronous Workerless Runtime](tasks/task-03-synchronous-runtime.md) — Introduce ReducedScopeWorkerRuntime helpers, eliminate queue dependencies, and execute ingestion/pillar jobs inline.
4. - [ ] [Task 04 — Reduced Scope Docker Compose Deployment](tasks/task-04-reduced-scope-deployment.md) — Ship a Dockerfile + Compose profile for FastAPI + Postgres demo runs and document the manual runbook.
5. - [ ] [Task 05 — Auth & Notification Fallback](tasks/task-05-auth-notification-fallback.md) — Provide logging email provider, minimal rate-limiters for auth endpoints, and admin overrides so onboarding works without SES/Valkey.
98. - [x] [Task 98 — Dummy Validation Entry A](tasks/task-98-dummy-validation-entry.md) — Added `## Task 98` log entry (2025-12-02T22:23:27Z UTC) under `epic-035/dummy_runs/validation_log.md`.
99. - [x] [Task 99 — Dummy Validation Entry B](tasks/task-99-dummy-validation-entry.md) — Added Task 99 log bullets and created `dummy_runs/summary.md` for dummy validation breadcrumbs.
