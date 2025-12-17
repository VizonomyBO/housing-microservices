# Project Status & Focus

## Current focus
- Synchronous, text-only ingestion via the FastAPI ingestion service (MarkItDown → contextual chunking → Voyage `voyage-context-3` embeddings → pgvector activation). Uploads are proxied through the Agent API but processed by ingestion-service only.
- ReAct agent in agent-api with a lean tool suite: hybrid retrieval (BM25 + pgvector) with `rerank-2.5`, attachment/status helpers, rerank utilities (HyDE/HyPE, contextual headers), and a Pyodide code tool for light computations/tabular work (Wasm sandbox, no filesystem; install extras with `micropip`/`httpx`).
- Local dev uses Docker Compose + LocalStack; production runs on EC2 via `scripts/deploy_stack.sh` with smoke coverage from `scripts/prod_smoke_check.sh`.

## Architecture snapshot
- Services: `agent-api` (FastAPI ReAct), `ingestion-service` (FastAPI synchronous), `auth-service` and `user-service` (Flask), Postgres 16 + pgvector, LocalStack for dev AWS mocks. Swagger aggregator remains disabled.
- Datastores: two logical DBs — `housing` (Agent/ingestion/shared data layer) and `auth_db` (auth/user). Graph/workflow tables persist in `packages/shared_data_layer` but are **deprecated**; keep them nullable and document-only.
- Retrieval defaults: Voyage `voyage-context-3` embeddings (1024-d by default; 256/512/2048 supported when DB matches) and Voyage `rerank-2.5`; fusion of BM25 + vector; per-fact `[c#]` citations; HyDE/HyPE and contextual headers encouraged.

## Operational posture
- Env selection is mandatory: `env_file=$(scripts/use_env.sh local|dev|prod); set -a && source "$env_file" && set +a`.
- Local dev: `docker compose --env-file "$env_file" up -d --build` then `./test-api.sh`.
- Hybrid dev: `docker compose --env-file "$env_file" -f docker-compose.ec2.yml up -d --build agent-api auth-service user-service ingestion-service`.
- Prod: `ENV_FILE="$env_file" ./scripts/deploy_stack.sh --mode services-only|full-redeploy` then `ENV_FILE="$env_file" ./scripts/prod_smoke_check.sh`.

## Deprecations
- Removed from active workflows: Step Functions/Lambda ingestion, Valkey cache/rate limiter, reduced-scope/telemetry profiles, graph RAG/planner flows. LocalStack remains only for dev S3/mocks.
- Legacy epics/interfaces are retained for historical context and labeled as archived; do not build new features against them.
