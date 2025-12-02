# Epic 3.5 Task Checklist

Complete tasks sequentially.

1. - [x] [Task 01 — Reduced Scope Gateway & Text-only Streaming](tasks/task-01-reduced-scope-gateway.md) — ReducedScope settings, demo-mode headers/SSE events, rate-limiter/cache shims, and router/subgraph guards are in place so `/v1/chat` runs text-only without Valkey.
2. - [x] [Task 02 — Text-only Document, Attachment & Pillar APIs](tasks/task-02-text-only-apis.md) — `/v1/documents/upload`, `/v1/conversations/{id}/attachments`, and `/v1/pillars/*` now run synchronously in text-only mode with reduced-scope messaging, metadata stubs, and tests.
3. - [ ] [Task 03 — Synchronous Workerless Runtime](tasks/task-03-synchronous-runtime.md) — Introduce ReducedScopeWorkerRuntime helpers, eliminate queue dependencies, and execute ingestion/pillar jobs inline.
4. - [ ] [Task 04 — Reduced Scope Docker Compose Deployment](tasks/task-04-reduced-scope-deployment.md) — Ship a Dockerfile + Compose profile for FastAPI + Postgres demo runs and document the manual runbook.
5. - [ ] [Task 05 — Auth & Notification Fallback](tasks/task-05-auth-notification-fallback.md) — Provide logging email provider, minimal rate-limiters for auth endpoints, and admin overrides so onboarding works without SES/Valkey.
