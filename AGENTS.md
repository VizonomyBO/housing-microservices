# AGENTS

## 1) How to Work (Plan → Research → Act → Verify)
- Section 1 is authoritative if any other section conflicts.
- Before coding, create a task-specific plan file in the repo root (e.g., `TASK_PLAN_<slug>.md`) with summary, impacted files, risks, ordered steps, and sources; plans are auto-approved. Create a matching tracker file to check off steps. Delete both when the task is done unless the task explicitly says to retain them.
- Start research with Context7 or web sources; cite URLs/doc IDs in the plan. Avoid guessing—quote the reference when behavior is non-obvious.
- Keep the tracker in sync as you work; run verification (tests/linters) before calling a task review-ready.
- Prefer existing libraries/integrations over bespoke code (e.g., langchain-voyageai, LangChain splitters) whenever available; do not reimplement client/splitter logic already provided by maintained packages.

## 2) Project Overview (check memory bank)
- Services: FastAPI Agent API (ReAct with tools), FastAPI ingestion service (text-only sync), Flask auth-service, Flask user-service; optional Swagger is deprecated.
- Shared data layer: `packages/shared_data_layer` is retained; add new fields via this package only. Graph-RAG relations are deprecated—mark unused relations nullable and document deprecations rather than deleting.
- Databases: Postgres 16 + pgvector with two logical DBs—`housing` (Agent/shared) and `auth_db` (auth/user). Do not mingle schemas.
- Retrieval/LLM: Retrieval RAG only (graph RAG removed). Use Voyage `voyage-context-3` embeddings (e.g., 1024 dims) + `rerank-2.5`; apply advanced RAG techniques (HyDE/HyPE, contextual headers, fusion BM25+vector, rerank, filtering).
- Current status/focus: Read `.kilocode/rules/memory-bank/*.md` (brief, context, tasks, tech, product) before making changes to pick up active constraints or ongoing efforts.

## 3) Environments & Tooling (uv-first)
- Select env first: `env_file=$(scripts/use_env.sh local|dev|prod); set -a && source "$env_file" && set +a`.
- Env setup: `uv venv --python 3.13 .venv`; deps via `uv sync --all-extras`; add deps with `uv add [--dev] <pkg>`; lock with `uv lock`.
- Run commands with `uv run <command>` to ensure the pinned Python/venv is used.
- Local dev: docker compose brings up Postgres, auth, user, ingestion, agent, and LocalStack (S3/needed AWS mocks) in one stack; LocalStack is required for dev AWS services.
- Prod: EC2 deployment of auth, user, ingestion, agent, and Postgres; use env files per scripts. Hybrid/reduced profiles are deprecated along with Valkey/telemetry extras.

## 4) Project Structure & Dependencies
- `services/agent-api` (FastAPI ReAct agent + tools) — text-only retrieval; uses Voyage `voyage-context-3` embeddings + `rerank-2.5`; tools include retrieval, rerank/filtering helpers, attachment mgmt, and Pyodide sandbox for code.
- `services/ingestion-service` (FastAPI) — synchronous text-only ingestion (parse → chunk → contextualized embed → persist/activate). No graph RAG edges; no Lambda/S3 pipeline.
- `services/auth-service`, `services/user-service` (Flask) — JWT and user mgmt backed by `auth_db`.
- `services/swagger-service` — deprecated/disabled.
- `packages/shared_data_layer` — authoritative schemas/repos/tests; graph-RAG relations deprecated (mark unused nullable); add new fields here only.
- `scripts/` — env selection, smoke/deploy helpers (to be updated with deploy automation); `test-api.sh` for manual endpoint coverage.

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
- No fallbacks, no mocks for evals or production code: use real dependencies (Voyage/OpenAI/ingestion) and propagate failures loudly (proper exceptions/HTTP errors). Test-only bypass flags are allowed only where explicitly marked.
- Do not introduce stubs/fixtures for production paths. If a dependency is unavailable, fail fast, log, and surface the error rather than silently degrading.
- Attachment/ownership model is simplified: list docs, create conversations, bulk attach/detach by doc IDs; owner_id may be set/null/“0000” for shared docs; allow deletes (DB + S3). Graph RAG ownership rules and refcounting are removed.

## 8) Task Lists & Trackers
- When creating task lists or checklists for the project, place them under `tasks/` in the repo root (e.g., `tasks/<slug>.md`). Keep the task-building guidance with the list so future agents follow the same structure.
- Plan/tracker files for active work live in the repo root (see Section 1) and are ephemeral unless a task says otherwise.

## 9) Operations (brief)
- AWS/EC2 smoke: `ENV_FILE="$env_file" ./scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_$(date +%s).log`; ensure uploads are unique to avoid dedupe short-circuits.
- Deploy: prefer the deployment automation script (modes: full infra/app redeploy with confirmation, service-only image rebuild/push/update, or hot patch via SSH + container restart). Until then, patch deploys can use `scp` + `docker cp` + compose restart per runbooks.

## 10) Boundaries & Approvals
- Use the shared data layer for DB access; do not craft ad-hoc SQL schemas. Maintain separation between `housing` and `auth_db`. Mark deprecated graph-RAG relations as such instead of deleting the package.
- Confirm before modifying other packages/services outside the task scope or before changing deployment infrastructure.
- Avoid removing/renaming plan or tracker files that predate your work unless the task explicitly says to clean them up.
