# AGENTS

## 1) How to Work (Plan → Research → Act → Verify)
- Section 1 is authoritative if any other section conflicts.
- Before coding, create a task-specific plan file in the repo root (e.g., `TASK_PLAN_<slug>.md`) with summary, impacted files, risks, ordered steps, and sources; plans are auto-approved. Create a matching tracker file to check off steps. Delete both when the task is done unless the task explicitly says to retain them.
- Start research with Context7 or web sources; cite URLs/doc IDs in the plan. Avoid guessing—quote the reference when behavior is non-obvious.
- Keep the tracker in sync as you work; run verification (tests/linters) before calling a task review-ready.

## 2) Project Overview (check memory bank)
- Services: FastAPI Agent API, FastAPI ingestion service (EC2), Flask auth-service, Flask user-service, optional Node/TS swagger-service.
- Shared data layer: `packages/shared_data_layer` holds models/repos/fixtures; Agent API should rely on it for persistence.
- Databases: Postgres 16 + pgvector with two logical DBs—`housing` (Agent/shared) and `auth_db` (auth/user). Do not mingle schemas.
- Retrieval/LLM: Hybrid BM25 + vector with Voyage embeddings + reranker required; attachment gating stays in place until ingestion activates documents.
- Current status/focus: Read `.kilocode/rules/memory-bank/*.md` (brief, context, tasks, tech, product) before making changes to pick up active constraints or ongoing smoke efforts.

## 3) Environments & Tooling (uv-first)
- Select env first: `env_file=$(scripts/use_env.sh local|dev|prod); set -a && source "$env_file" && set +a`.
- Env setup: `uv venv --python 3.13 .venv`; deps via `uv sync --all-extras`; add deps with `uv add [--dev] <pkg>`; lock with `uv lock`.
- Run commands with `uv run <command>` to ensure the pinned Python/venv is used.
- Local/hybrid/prod compose: use `.env.local` for LocalStack (optional/deferred), `.env.dev` for hybrid, `.env.prod` for AWS/EC2; compose files include `docker-compose.ec2.yml` for hybrid/prod workflows.

## 4) Project Structure & Dependencies
- `services/agent-api` (FastAPI + LangGraph) — chat, retrieval, citations.
- `services/ingestion-service` (FastAPI) — MarkItDown → chunk → embed → index → activate; `/v1/documents/upload` proxies here.
- `services/auth-service`, `services/user-service` (Flask) — JWT + user mgmt backed by `auth_db`.
- `services/swagger-service` (Node/TS) — optional aggregated docs (disabled by default).
- `packages/shared_data_layer` — authoritative schemas/repos/tests; reuse instead of duplicating models.
- `scripts/` — env selection, prod smoke, deploy helpers; `test-api.sh` for manual endpoint coverage.

## 5) Workflow & Git Hygiene
- Prefer small, reviewable changes; follow CONTRIBUTING if present. Do not rewrite or drop user changes. Avoid destructive commands (`git reset --hard`, `git checkout --`) unless explicitly requested.
- Keep commits scoped; don’t amend pushed commits unless asked. Use feature branches when possible.
- Ask before adding heavy dependencies or changing infra beyond the task scope.

## 6) Quality Gates (run before review-ready)
```bash
uv run ruff format .
uv run ruff check --fix .
uv run ty check .
uv run pytest -n auto
```
Add targeted tests when behavior changes; prefer real integrations over stubs.

## 7) Runtime Safety & Fail-Fast Policy
- No fallbacks, no mocks for evals or production code: use real dependencies (Voyage/OpenAI/Valkey/rate limiter/ingestion) and propagate failures loudly (proper exceptions/HTTP errors). Test-only bypass flags are allowed only where explicitly marked.
- Do not introduce stubs/fixtures for production paths. If a dependency is unavailable, fail fast, log, and surface the error rather than silently degrading.
- Keep attachment safety: documents remain blocked until ingestion activates them; preserve original upload payload for downstream steps when working on workflows/state machines.

## 8) Task Lists & Trackers
- When creating task lists or checklists for the project, place them under `tasks/` in the repo root (e.g., `tasks/<slug>.md`). Keep the task-building guidance with the list so future agents follow the same structure.
- Plan/tracker files for active work live in the repo root (see Section 1) and are ephemeral unless a task says otherwise.

## 9) Operations (brief)
- AWS/EC2 smoke: `ENV_FILE="$env_file" ./scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_$(date +%s).log`; ensure uploads are unique to avoid dedupe short-circuits.
- Patch deploy (Python services): `scp` file to EC2, `docker cp` into the target container, then `sudo docker compose -f /opt/housing-microservices/docker-compose.ec2.yml restart <service>`; verify health (`/health` or targeted endpoint). See runbooks in `docs/` and `notes/` for details.

## 10) Boundaries & Approvals
- Use the shared data layer for DB access; do not craft ad-hoc SQL schemas. Maintain separation between `housing` and `auth_db`.
- Confirm before modifying other packages/services outside the task scope or before changing deployment infrastructure.
- Avoid removing/renaming plan or tracker files that predate your work unless the task explicitly says to clean them up.
