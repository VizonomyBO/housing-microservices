# Task 01 — Deployment Discovery & Compose Plan

## System Snapshot
- The repo hosts five Python services (`agent-api`, `auth-service`, `user-service`, `marker-service`, `swagger-service`) plus shared packages (`packages/shared_data_layer`, etc.).
- Root-level `docker-compose.yml` only provisions the legacy account/user stack, while `services/agent-api/docker-compose.reduced.yml` bootstraps a FastAPI + Postgres demo for Epic 3.5.
- Environment variables are scattered across multiple `.env.example` files and README snippets; there is no single source of truth for service ports, AWS credentials, or inter-service dependencies.

## What You Inherit
- Existing Compose assets: root `docker-compose.yml`, `docker-compose.test.yml`, `services/agent-api/docker-compose.reduced.yml`, and service-specific Dockerfiles under `services/*/Dockerfile`.
- Deployment documentation: `README.md`, `QUICKSTART.md`, `docs/infrastructure/infrastructure_and_deployment.md`, `docs/runbooks/reduced_scope_demo.md`, and service READMEs.
- Shared tooling: `services/agent-api/run_tasks.sh`, `AGENTS.md`, and Makefile helpers.

## Goal
Produce a research-backed deployment plan that explains how to revamp the root `docker-compose.yml` into a single entrypoint that can launch every microservice (full mode) or a reduced demo stack. The plan must cover shared dependencies (Databases, LocalStack, networking, volumes), environment-variable strategy, and migration steps for removing `services/agent-api/docker-compose.reduced.yml`.

## Must Read / Inspect Before Coding
1. Root Compose + env assets: `docker-compose.yml`, `docker-compose.test.yml`, `env.example`, `Makefile`.
2. Service-level Compose/Docker artifacts: `services/agent-api/docker-compose.reduced.yml`, each `services/*/Dockerfile`, plus any service-specific `.env` templates.
3. Deployment docs: `README.md`, `QUICKSTART.md`, `docs/infrastructure/infrastructure_and_deployment.md`, `docs/runbooks/reduced_scope_demo.md`.
4. Any AWS/LocalStack references in code (search for `AWS_`, `LOCALSTACK`, `boto3`, etc.) to understand required mock services.

## Implementation Scope & Deliverables
- Create a new plan document at `docs/infrastructure/root_compose_plan.md` outlining:
  - Service inventory (ports, images, build contexts, runtime dependencies, required AWS services).
  - Proposed Compose structure (networks, shared volumes, `profiles` for reduced/full, dependency graph).
  - Environment variable matrix (global `.env`, per-service overrides, secrets vs defaults).
  - LocalStack integration strategy (which AWS services to emulate, how to toggle prod vs local).
  - Migration steps for deleting `services/agent-api/docker-compose.reduced.yml` once the root stack replaces it.
- Summarize open questions / risks (e.g., missing Dockerfiles, services that require additional adapters).
- Update `services/agent-api/epic-root-compose/CHECKLIST.md` to mark Task 01 complete when finished.

## Step-by-Step Instructions
1. **Inventory services & dependencies**:
   - For each service under `services/`, capture Dockerfile base image, exposed port, database/cache requirements, and third-party integrations (AWS, Postgres, Redis, etc.).
   - Note any shared Python packages or volumes they need at runtime (e.g., `packages/shared_data_layer` editable install).
2. **Analyze existing Compose files**:
   - Map what the current root `docker-compose.yml` does and why it is insufficient.
   - Extract reusable patterns from `services/agent-api/docker-compose.reduced.yml` (db-init, seeding, env file usage) that should be preserved or improved.
3. **Research best practices**:
   - Review Docker Compose docs for multi-profile setups, shared build contexts, and `.env` handling.
   - Review LocalStack guidance for wiring AWS SDKs via `EDGE_PORT`, `AWS_ENDPOINT_URL`, or `LOCALSTACK_HOSTNAME`.
   - Capture links/notes in the plan so later tasks can cite them without re-researching.
4. **Draft the root compose plan document**:
   - Organize sections for architecture overview, service matrix, environment strategy, LocalStack toggle, migration checklist, and testing approach (`docker compose config`, smoke tests).
   - Call out required follow-up tasks (e.g., code changes to respect new env vars) so later task files can reference them.
5. **Review & finalize**:
   - Run `git status` to ensure only the new plan + checklist updates are staged.
   - No code build/test is expected for this research task, but lint the plan with `markdownlint` if available (optional).

## Definition of Done
- `docs/infrastructure/root_compose_plan.md` exists with the details listed above, including citations/links for any external guidance.
- The plan explicitly covers reduced vs full profiles, LocalStack usage, env strategy, and migration steps for retiring `services/agent-api/docker-compose.reduced.yml`.
- Risks, unknowns, and assumptions are clearly called out to guide future tasks.
- `services/agent-api/epic-root-compose/CHECKLIST.md` reflects Task 01 completion, and no other files are unintentionally modified.
- Logs for this task land under `services/agent-api/logs/task_01` via `run_tasks.sh`.
