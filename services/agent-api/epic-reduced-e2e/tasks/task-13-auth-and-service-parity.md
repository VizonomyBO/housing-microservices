# Task 13 — Auth & Service Parity

## System Snapshot
- `/v1/*` routes still rely on the stubbed `get_auth_context` that trusts any `Bearer` token string; JWT validation, scope checks, and user lookups are bypassed.
- AWS access remains hard-coded to LocalStack in smoke workflows; there is no turnkey way to run against real AWS resources (S3, queues, etc.) even though the rest of the stack is production-like.
- Tasks 10–12 ensure real LLM/ingestion flows, but without real auth + optional AWS passthrough we still diverge from the production environment.

## What You Inherit
- A working auth service in `services/auth-service` that issues JWTs and a reduced smoke CLI capable of registering demo users.
- Task 10 env plumbing for real-tool flags and Task 12 compose wrapper improvements.
- AWS configuration files (`env.example`, runbooks) already describing required credentials for the full stack.

## Goal
Make the Agent API smoke environment enforce the same auth + AWS behaviors as production (with optional LocalStack fallback). Outcomes:
1. FastAPI routes validate JWTs (signature + claims) and refuse unauthenticated/unauthorized requests.
2. AWS SDK clients can target either LocalStack or real AWS via env toggles; LocalStack remains the default for affordable smoke runs, but operators can switch to real AWS without code changes.
3. CLI + docs explain how to obtain/refresh tokens and how to provide AWS creds when running in full-real mode.

## Must Read / Inspect
1. `services/auth-service` docs + token contract.
2. `agent_api/http/deps.py:get_auth_context` and any downstream uses of `AuthContext`.
3. Runbooks for reduced/full stack compose flows (`docs/runbooks/reduced_scope_demo.md`, `docs/runbooks/full_stack_compose.md`).

## Implementation Scope & Deliverables
- Replace the stubbed auth dependency with a proper JWT validator and delete the legacy helper so no runtime path can fall back to accepting raw IDs:
  - Parse `Authorization` header, verify signature using the auth-service public key or JWKS endpoint.
  - Enforce required claims (subject, tenant, scopes) and surface consistent errors.
  - Cache keys and expose metrics for auth failures.
- Update CLI + smoke docs to ensure demo users obtain real tokens (or the CLI reuses the auth-service login endpoint and forwards the JWT).
- Introduce AWS client factories that respect `USE_LOCALSTACK` and credentials set in `.env`:
  - Default to LocalStack endpoints for reduced-cost runs.
  - When `USE_LOCALSTACK=0`, use the real AWS SDK endpoints/creds without code changes.
- Update compose wrapper + runbooks to describe how to toggle between LocalStack and real AWS (including required IAM credentials, safety checks, and teardown instructions).
- Add tests for auth middleware (valid token, expired token, signature mismatch) and for AWS client selection logic.

## Step-by-Step Instructions
1. Integrate `python-jose`, `authlib`, or similar library for JWT validation; wire it into `get_auth_context` (or a new dependency) and update all routes to expect real user IDs.
2. Add caching for JWKS/public keys and log errors with enough context for debugging.
3. Refactor any AWS SDK usage (S3 uploads, LocalStack probes, etc.) to go through a helper that reads endpoints/creds from `Settings`.
4. Update CLI + docs so operators know how to obtain tokens/creds for both modes.
5. Extend automated tests (unit + integration) to cover the new auth + AWS toggles.
6. Run QA suite.

## Definition of Done
- Every HTTP route enforces real JWT validation; unauthorized requests fail with 401/403.
- AWS-dependent features run against LocalStack by default but can target real AWS simply by switching env vars.
- CLI/runbooks document the process end-to-end (tokens, creds, toggles).
- QA suite passes.

## Handoff Notes
- Document any remaining auth/AWS gaps (e.g., missing IAM policies, token refresh ergonomics).
- Call out operational safeguards (rate limits, cost considerations) when pointing smoke runs at production AWS resources.
- Auth-service still issues HS256 tokens and lacks a JWKS endpoint. Keep `AUTH_SHARED_SECRET` synchronized with `JWT_SECRET_KEY` until the JWKS route ships, then set `AUTH_JWKS_URL` so the validator can swap to RS256.
- When operators point the smoke stack at real AWS (`USE_LOCALSTACK=0`) remind them to clean up buckets/queues afterward and to run with tightly scoped IAM credentials—the wrapper no longer stands up LocalStack in this mode.
