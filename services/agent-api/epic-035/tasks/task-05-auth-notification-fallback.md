# Task 05 — Auth & Notification Fallback

## System Snapshot
- After Task 04, agent-api can run entirely via Docker Compose with ReducedScope enabled; no SES, Valkey rate limiting, or separate auth service is available for the demo.
- Existing auth context (`agent_api/http/context.py`) is a stub that only reads bearer tokens—registration, password reset, and verification endpoints do not exist yet in this service.
- Docs (`docs/security/auth_and_tokens.md`, `docs/epics/07.md`) still assume SES + Valkey-backed abuse controls.

## What You Inherit
- ReducedScope settings + runtime/CLI + deployment artifacts from Tasks 01–04.
- Shared data layer already provides `users`, `verification_tokens`, and auth-related repositories (see `packages/shared_data_layer/repositories/*`).
- `docs/security/auth_and_tokens.md` defines the required headers, rate limits, and verification flow you must preserve even in fallback mode.

## Goal
Keep registration/password flows usable without SES or Valkey-backed abuse controls by adding logging-based email delivery, lightweight per-process rate limiting, and admin override tooling—while documenting exactly how to flip the reduced-scope flag off and restore SES + Valkey later.

## Must Read Before Coding
1. `docs/epics/035.md` — Task 3.5.5 scope.
2. `docs/security/auth_and_tokens.md` §2 — header/auth requirements + abuse limits.
3. `docs/epics/07.md` §§7.1–7.7 — SES + rate limiter design.
4. `docs/interfaces/api_contracts.md` §5 — auth endpoints + notification payloads.
5. `packages/shared_data_layer/AGENTS.md` + relevant repositories for auth/email tables.

## Implementation Scope & Files
- Add `agent_api/notifications/logging_email_provider.py` (new module) implementing the email provider interface expected by auth flows. It should:
  - Accept `send_verification`, `send_password_reset`, etc., serialize payloads to structured logs, and immediately mark the corresponding verification token as delivered.
  - Record payloads under `logs/reduced_scope_emails/*.json` (optional) for manual inspection.
- Create lightweight rate limiter utilities (`agent_api/http/rate_limit.py` or reuse Task 01 shim) with per-process counters (e.g., `collections.Counter` + timestamps) enforcing `/forgot-password` ≤3/hour/IP and `/verify-email` ≤10/hour/IP. Add TODO comments + flag checks showing where the Valkey-backed limiter will reconnect.
- Expose new FastAPI routes under `/v1/auth`:
  - `POST /v1/auth/register`, `POST /v1/auth/forgot-password`, `POST /v1/auth/reset-password`, `POST /v1/auth/verify-email`.
  - Guard each route with the reduced-scope limiter + logging provider; ensure responses include `{"delivery_status": "logged"}` when SES is disabled.
  - Provide an admin-only route (e.g., `POST /v1/internal/demo/verify-email`) protected by a static token or Basic auth that flips `email_verified` for demo users.
- Update `agent_api/http/context.py` and any auth middleware to read the reduced-scope flag and include headers like `Viz-Auth-Mode: demo` so clients know SES is bypassed.
- Add CLI helpers (`agent_api/cli.py` or new subcommand) for toggling verification flags and dumping the logged email payloads.
- Documentation updates: `docs/security/auth_and_tokens.md`, `docs/interfaces/api_contracts.md`, `README.md`, and Docker runbook from Task 04 should mention the fallback provider, rate limits, admin override endpoint, and steps to re-enable SES/Valkey (env vars, Terraform modules, queue configs).
- Tests: add HTTP tests for each auth route (`tests/http/test_auth_routes.py`), unit tests for `LoggingEmailProvider` + limiter (`tests/notifications/test_logging_email_provider.py`, `tests/http/test_rate_limit.py`), and CLI tests verifying the admin helper toggles `email_verified`.

## Step-by-Step Instructions
1. **Implement providers + limiters**:
   - Build `LoggingEmailProvider` with methods mirroring the future SES adapter. Wire it into a `ReducedScopeAuthConfig` (extends Task 01 settings) so other modules can inject it easily. Implement per-process rate limiter helpers that store request counts in memory, reset hourly, and expose telemetry hooks. Add tests to guarantee limits (3/hr, 10/hr) are enforced and that metadata contains TODO references for Valkey reintegration.
2. **Add auth routes + admin overrides**:
   - Create `agent_api/http/routes/auth.py` (public endpoints) and `agent_api/http/routes/internal_demo.py` (admin overrides). Use shared_data_layer repositories to create users, verification tokens, and password reset records synchronously. Each route should log via `LoggingEmailProvider`, respect ReducedScope rate limits, and return consistent JSON payloads documented in `docs/interfaces/api_contracts.md`.
3. **Document + wire CLI helpers**:
   - Extend the CLI from Task 03 with commands like `uv run python -m agent_api.cli emails --tail` and `... auth --verify <email>`. Update Docker runbook/README/security docs describing how to use these helpers during the demo and how to flip back to SES/Valkey (env vars, Terraform state) afterward.

## Definition of Done
- LoggingEmailProvider + reduced-scope rate limiter are implemented, tested, and automatically used when `REDUCED_SCOPE_ENABLED=1`.
- Auth endpoints function without SES/Valkey, emit demo-mode headers, and expose an admin override for verification.
- CLI + docs clearly explain how to operate the fallback flows and how to re-enable the real providers/rate limiters post-demo.
- Tests cover provider behavior, limiter enforcement, and HTTP routes; run `uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, and `uv run pytest -n auto`.
- **Handoff Notes**: Agent must note any remaining integration points with SES/Valkey, document secrets required for admin routes, and highlight risk areas for post-demo reactivation.

## Handoff Notes
- Describe where logged email payloads live and how long to retain them.
- Capture configuration needed to secure the admin override route (header name, token location) so future agents can harden it.
- Note outstanding TODOs for reintroducing SES/Valkey-backed rate limiting and email delivery.
