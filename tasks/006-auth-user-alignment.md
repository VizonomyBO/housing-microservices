# Task: Align Auth/User Services with Simplified Stack

Follow `.kilocode/rules/memory-bank-instructions.md` and `AGENTS.md`; create/update a plan + tracker in the repo root.
The agent must commit the changes before terminating the task.
Once the task is done, mark this as completed in the title

## Objective
- Update auth-service and user-service to match the cache-free, simplified architecture while keeping `auth_db` separation intact.

## Scope
- Remove reliance on rate limiters/cache extras (SlowAPI/Flask-Limiter configs) in favor of simple guards appropriate for the new quotas; clean up unused env vars and config defaults.
- Ensure JWT issuance/verification and user flows match the new compose/env naming and integrate cleanly with the ingestion/agent path (owner_id nullable/“0000” shared semantics, attachments list/create flows supported upstream).
- Refresh Dockerfiles/pyproject/uv/requirements as needed to drop deprecated deps and align with Python 3.13/uv tooling standards.
- Update tests/docs for auth/user to reflect the trimmed feature set and new environment defaults.

## Deliverables
- Auth/User services without rate-limit/cache dependencies, using the new env conventions and validated against `auth_db`.
- Updated tests/config/docs for these services consistent with the simplified stack.

## References
- `docs/requirements_revamp.md`
- `.kilocode/rules/memory-bank/*.md`, `AGENTS.md`
