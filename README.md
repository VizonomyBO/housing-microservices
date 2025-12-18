# Housing Microservices Platform

FastAPI Agent API (ReAct + tools + Pyodide sandbox) with a synchronous FastAPI ingestion service, Flask auth/user services, and Postgres 16 + pgvector. Retrieval is text-only: MarkItDown → contextual chunking → Voyage `voyage-context-3` embeddings (1024-d default) → rerank with `rerank-2.5` before prompting. Local dev uses Docker Compose + LocalStack; production runs on EC2 via `scripts/deploy_stack.sh`.

## Quick starts
- Choose env: `env_file=$(scripts/use_env.sh local|dev|prod); set -a && source "$env_file" && set +a`
- Local dev (LocalStack required): `docker compose --env-file "$env_file" up -d --build`
- Hybrid/EC2 compose: `docker compose --env-file "$env_file" -f docker-compose.ec2.yml up -d --build agent-api auth-service user-service ingestion-service`
- Prod deploy: `ENV_FILE="$env_file" ./scripts/deploy_stack.sh --mode services-only` (or `full-redeploy` for terraform + services)
- Prod smoke: `ENV_FILE="$env_file" ./scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_$(date +%s).log`
- Stop: `docker compose --env-file "$env_file" down [-v]`

## Architecture snapshot
- **agent-api (FastAPI, ${AGENT_API_PORT:-8000})** — ReAct agent with LangChain `create_agent`, shared-data-layer repositories, retrieval tools (BM25 + pgvector with voyage-context-3), rerank-2.5, attachment/status helpers, and Pyodide code tool (Wasm sandbox, no filesystem; install extras with `micropip`/`httpx`). SSE chat with per-fact `[c#]` citations and UUID `thread_id` ownership.
- **ingestion-service (FastAPI, ${INGESTION_SERVICE_PORT:-8085})** — Synchronous upload path: MarkItDown → contextual chunking → Voyage embeddings (`output_dimension` 256/512/1024/2048 when DB matches) → pgvector → activate. Allowed `source_type`: pdf, docx, doc, txt, md, html, json.
- **auth-service/user-service (Flask, ${AUTH_SERVICE_PORT:-5001}/${USER_SERVICE_PORT:-5002})** — JWT issuance/validation and user management backed by `auth_db`.
- **postgres (pgvector 16, ${POSTGRES_PORT:-5432})** — Two logical DBs: `housing` (Agent/ingestion/shared data layer) and `auth_db` (auth/user). Graph/telemetry/cache tables remain in the shared data layer but are deprecated/nullable.
- **localstack (${LOCALSTACK_EDGE_PORT:-4566})** — Required for dev AWS mocks; production bypasses LocalStack entirely.

## Local dev
```bash
env_file=$(scripts/use_env.sh local)
set -a && source "$env_file" && set +a
docker compose --env-file "$env_file" up -d --build
./test-api.sh
curl -fsS http://localhost:${INGESTION_SERVICE_PORT:-8085}/health
curl -fsS http://localhost:${AGENT_API_PORT:-8000}/health
```
Tear down with `docker compose --env-file "$env_file" down` (add `-v` to drop volumes).

## Hybrid / remote data plane
Run locally against remote Postgres/S3/ingestion:
```bash
env_file=$(scripts/use_env.sh dev)
set -a && source "$env_file" && set +a
docker compose --env-file "$env_file" -f docker-compose.ec2.yml up -d --build agent-api auth-service user-service ingestion-service
```

## Prod deploy + smoke
See `docs/setup/prod.md` and `docs/runbooks/prod_setup.md` for details.
```bash
env_file=$(scripts/use_env.sh prod)
set -a && source "$env_file" && set +a
ENV_FILE="$env_file" ./scripts/deploy_stack.sh --mode full-redeploy   # terraform + services
ENV_FILE="$env_file" ./scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_$(date +%s).log
```

## Quality gates
From repo root (uv-managed):
```bash
uv run ruff format .
uv run ruff check --fix .
uv run ty check .
uv run pytest -n auto
```

## Agent evals (prod dataset)
- Require `.env.evals` (no `.env.prod` fallback) with `AGENT_BASE_URL=http://localhost:8000`, prod `AUTH_BASE_URL`/DB URLs, `AUTH_SHARED_SECRET`, eval user creds (`eval_user@example.com` / `TestPass123!` / `52f96e69-2232-4215-878e-45041858ba30`), and OpenAI/Voyage keys.
- Install Deno via `curl -fsSL https://deno.land/install.sh | sh` (defaults to `$HOME/.deno/bin`) and ensure `export PATH="$HOME/.deno/bin:$PATH"` for non-login shells; do **not** add PATH overrides to env files. Verify with `deno --version`.
- Run: `set -a && source .env.evals && set +a && cd services/agent-api && uv run pytest tests/evals -m eval --maxfail=1` (streaming evals are currently skipped).
- Code-tool evals run locally via Deno (Pyodide sandbox) and do not require `PYODIDE_BASE_URL`. Artifacts write to `services/agent-api/tests/evals/artifacts/<timestamp>_<scenario>.json` (gitignored).

## Env files quick map
- `.env.local`: local compose (Agent API + ingestion + auth/user + Postgres; LocalStack when used). Selected by `scripts/use_env.sh local` and used for local smoke/dev.
- `.env.dev`: hybrid/dev against remote infra (e.g., EC2 Postgres/S3/ingestion) while running services locally with `docker-compose.ec2.yml`. Selected by `scripts/use_env.sh dev`.
- `.env.prod`: production stack values for deploys and prod smokes.
- `.env.evals`: required for the eval suite; mirrors prod creds/URLs but sets `AGENT_BASE_URL=http://localhost:8000` for a locally running Agent API.

## Env files quick map
- `.env.local`: local compose (Agent API + ingestion + auth/user + Postgres; LocalStack when used). Selected by `scripts/use_env.sh local` and used for local smoke/dev.
- `.env.dev`: hybrid/dev against remote infra (e.g., EC2 Postgres/S3/ingestion) while running services locally with `docker-compose.ec2.yml`. Selected by `scripts/use_env.sh dev`.
- `.env.prod`: production stack values for deploys and prod smokes.
- `.env.evals`: required for the eval suite; mirrors prod creds/URLs but sets `AGENT_BASE_URL=http://localhost:8000` for a locally running Agent API.

## Deprecations
- Lambda/Step Functions ingestion, Valkey cache/rate limiter, reduced-scope modes, and telemetry extras are removed from active workflows.
- Graph RAG/workflow tables remain in the shared data layer for backward compatibility but are explicitly deprecated and nullable; do not build new features on them.
