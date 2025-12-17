# [Completed] Task: Refresh Dev Compose/Env for Simplified Stack

Follow `.kilocode/rules/memory-bank-instructions.md` and `AGENTS.md`; create/update a plan + tracker in the repo root.
The agent must commit the changes before terminating the task.
Once the task is done, mark this as completed in the title

## Objective
- Rebuild local/dev compose/env tooling to run only Postgres, auth, user, ingestion, agent, plus LocalStack (required for S3/AWS mocks), removing reduced/full/hybrid/valkey/telemetry footprints.

## Scope
- Replace `docker-compose.yml` (and related overrides) with a minimal profile that always brings up Postgres + auth-service + user-service + ingestion-service + agent-api + LocalStack; remove Valkey/otel/reduced-scope profiles and the legacy backup compose.
- Update env templates (`env.example`, `.env.local/.env.dev/.env.prod` flow via `scripts/use_env.sh`) to match the retained services and voyage-context-3 defaults; strip cache/rate-limit vars.
- Ensure compose includes ingestion service (not just EC2 profile) and LocalStack wiring for S3/mock AWS used in dev; adjust healthchecks/depends_on accordingly.
- Update helper scripts (`scripts/init-databases.sh`, `test-api.sh`, smoke helpers) and docs/README quick starts to match the new compose topology and ingestion-first uploads.

## Deliverables
- New compose files/env templates/scripts reflecting the simplified stack with LocalStack required in dev.
- Updated quick-start/runbook snippets demonstrating the new dev bring-up and smoke flow.

## References
- `docs/requirements_revamp.md`
- `.kilocode/rules/memory-bank/*.md`, `AGENTS.md`
