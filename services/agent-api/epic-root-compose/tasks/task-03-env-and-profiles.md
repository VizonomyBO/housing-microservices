# Task 03 — Environment Templates & Runtime Profiles

## System Snapshot
- The new root `docker-compose.yml` (Task 02) references `.env` for shared configuration but the repository still relies on scattered env templates (`env.example`, service-level `.env` samples).
- Reduced vs Full stacks need distinct defaults (e.g., fewer services, feature flags, LocalStack usage), yet there is no canonical `.env.example` capturing those knobs.
- Many services read configuration via their own `Config` classes, but they may not yet expose variables for LocalStack endpoints, AWS creds, or reduced-scope flags.

## Goal
Establish a single source of truth for environment variables and runtime profiles:
- Author a comprehensive root `.env.example` (and instructions for copying to `.env`) that includes every variable consumed by the Compose stack and services.
- Align service config modules so they can read the new variables (e.g., `SERVICE_MODE=reduced|full`, `USE_LOCALSTACK=1`, shared DB creds, AWS access keys).
- Ensure the root Compose file loads `.env` automatically and services inherit the correct profile-specific vars.

## Must Read / Inspect Before Coding
1. `docker-compose.yml` (post-Task-02) to understand which env vars are required.
2. Existing env samples: root `env.example`, `services/*/.env*.example`, and README instructions.
3. Service config files: `services/<name>/app/config.py`, `.env` loaders, and any `settings.py` modules that parse envs.
4. Task 01 plan sections on environment strategy and reduced/full profiles.

## Implementation Scope & Files
- Replace the root `env.example` with a new version that includes:
  - Standard Compose settings (project name, default networks, port overrides).
  - Shared database credentials (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, etc.).
  - Service-specific secrets (JWT keys, auth salts) with placeholder values.
  - Reduced/Full toggles (e.g., `STACK_PROFILE=reduced`, `REDUCED_SCOPE_ENABLED=1`).
  - LocalStack flag + credentials (`USE_LOCALSTACK=1`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `LOCALSTACK_EDGE_PORT`, etc.).
- Document in the file header how to copy `.env.example` → `.env` and warn against committing real secrets.
- Update service configuration modules to consume the new env variable names (e.g., if Compose now sets `AGENT_API_PORT`, ensure `agent_api/settings.py` honors it).
- Ensure `docker-compose.yml` references `.env` via `env_file: .env` or `${VAR:-default}` for every service.
- Add any necessary helper scripts or Makefile targets to simplify copying `.env.example`.

## Step-by-Step Instructions
1. **Design the env schema**:
   - Start from the matrix in `docs/infrastructure/root_compose_plan.md`.
   - Group variables by category (Global, Database, AWS/LocalStack, Service-specific).
   - Decide on naming conventions (e.g., `SERVICE_NAME_*` prefixes) and default values suitable for local development.
2. **Author `.env.example`**:
   - Include descriptive comments for each variable.
   - Provide sensible defaults for local dev (non-secret) and leave placeholders for secrets (e.g., `CHANGE_ME`).
   - Cover both reduced and full profiles (e.g., `STACK_PROFILE=full` with guidance on switching to `reduced`).
3. **Propagate vars into services**:
   - Update config files (`services/*/app/config.py`, `agent_api/settings.py`, etc.) to read the new variable names.
   - Ensure services can detect `STACK_PROFILE` or `REDUCED_SCOPE_ENABLED` and behave accordingly (even if the behavior is already implemented, align the env names).
4. **Wire Compose to `.env`**:
   - Confirm each service definition in `docker-compose.yml` references the new vars.
   - Remove any hardcoded passwords/usernames; everything should come from `.env`.
5. **Validation**:
   - Copy `.env.example` to `.env` locally (with dummy secrets) and run `docker compose config` to verify interpolation.
   - Run targeted unit tests if service config code changed (e.g., `uv run pytest services/agent-api/tests/settings`).
6. **Update supporting docs**:
   - Add a short note to `docs/infrastructure/root_compose_plan.md` referencing the finalized env schema (full README updates happen in Task 05).

## Definition of Done
- Root `.env.example` documents every variable required to run either reduced or full stack, with clear comments and defaults.
- All services read their configuration from the new env names; there are no stale references to removed vars.
- `docker-compose.yml` successfully loads `.env` (tested via `docker compose config`), and switching `STACK_PROFILE` or `REDUCED_SCOPE_ENABLED` in `.env` affects Compose/service behavior.
- The old scattered env templates are either deleted or updated to point back to the root `.env`.
- Task 03 checkbox is ticked in `CHECKLIST.md`, and logs reflect the commands executed.

## Handoff Notes
- 2025-12-02: Root `docker-compose.yml` now loads `.env` for every service; copy `env.example` → `.env` before running Compose commands to avoid missing-file errors until Task 03 finalizes templates.
- `scripts/init-databases.sh` provisions the `agent_reduced` database/user via `AGENT_API_DB*` envs—ensure the new `.env.example` keeps those values in sync.
- Reduced/full profiles exist as `profiles: ["reduced", "full"]` on `agent-api`, `db-init`, etc. Task 03 should document how toggles like `SERVICE_MODE` and `USE_LOCALSTACK` relate to `COMPOSE_PROFILES`.
