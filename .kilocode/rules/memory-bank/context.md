# Context

## Current Focus
Keep the ingestion-first stack healthy across LocalStack dev and EC2 prod, with fast smokes and real evals (no stubs). Unique uploads remain required to avoid content-hash dedupe during smokes.

### Active Tasks
- **Prod smoke (FastAPI ingestion)**: Run `scripts/local_smoke.sh --target prod --env-file "$(scripts/use_env.sh prod)" --upload-file <file> --smoke-output <path>` or `scripts/prod_deploy_and_smoke.sh` after deploys. Use stamped uploads to dodge dedupe and capture the JSON output.
- **Ingestion pipeline**: Exercise the synchronous MarkItDown → contextual chunk → Voyage embed → pgvector → activation path and confirm Agent API attachment gating stays intact.
- **Plan/Tracker discipline**: Create a plan + tracker per task in repo root (auto-approved); remove when done unless a task says otherwise.
- **Agent eval harness**: Pytest eval suite under `services/agent-api/tests/evals` hits prod data with the eval user; artifacts land in `services/agent-api/tests/evals/artifacts/<timestamp>_<scenario>.json`. Requires `.env.evals` (no `.env.prod` fallback) plus `OPENAI_API_KEY`/Voyage keys and Deno on PATH.

## Recent Changes
- **FastAPI ingestion on EC2** replaced Lambda/S3; Agent API upload proxies to this service (no inline ingestion). Live endpoints (prod runbook): `AGENT_BASE_URL=http://52.207.140.87:8000`, `AUTH_BASE_URL=http://52.207.140.87:5001`, `INGEST_BASE_URL=http://52.207.140.87:8085`.
- **Ingestion pipeline tightened**: text-only, synchronous MarkItDown → contextual/proposition chunking → voyage-context-3 embeddings (default 1024-dim; supports 256/512/2048 when pgvector dimension matches), with form field `output_dimension` and trimmed source types (`pdf`, `docx`, `doc`, `txt`, `md`, `html`, `json`).
- **Shared Data Layer** centralizes models/repos in `packages/shared_data_layer`; Agent API relies on it for persistence (Postgres 16, pgvector).
- **Tooling** standardized on `uv` + Python 3.13; quality gates run via `uv run` (ruff format/check, ty, pytest). Env selection via `scripts/use_env.sh`.
- **Retrieval & Eval Hardening**: Hybrid BM25 + vector with Voyage embeddings + rerank (`voyage-context-3` + `rerank-2.5`) is required (no optional fallback), HyDE-style rewrites, numeric-aware citation scoring, structured `[c#]` footnotes, and raised eval thresholds. `reembed-chunks` CLI refreshes embeddings.
- **Agent eval/smoke**: Unified `scripts/local_smoke.sh` (`--target local|prod`) handles smokes; prod helper `scripts/prod_deploy_and_smoke.sh` wraps deploy + smoke. PATH is no longer overridden in `.env.prod`; Deno PATH is set in the agent-api image, and Postgres uses its default PATH to ensure `initdb` is found.
- **Fail-fast dependencies**: OPENAI/Voyage/Valkey/rate limiter are required by default; bypass flags (`ALLOW_IN_MEMORY_VALKEY`, `ALLOW_RATE_LIMITER_BYPASS`, etc.) are test-only.
- **Attachment safety**: Documents stay blocked until ingestion is active; `/v1/chat` enforces UUID ownership for `thread_id`, with optional stateless mode.
- **LangChain integrations**: Agent and ingestion use LangChain Voyage integrations (embeddings/rerank) and LangChain text splitters (RecursiveCharacterTextSplitter) instead of bespoke clients/splitters.
- **Dev reload compose**: `docker-compose.dev.yml` bind-mounts code for agent-api/ingestion/auth/user/shared_data_layer and runs services with reload; rebuild is only needed when dependencies change. LocalStack is required for dev AWS mocks.
- **Init-migrations flow**: Compose uses a one-shot `init-migrations` service (Dockerfile under `docker/init-migrations/`) that waits for Postgres (pgvector 16 + `scripts/init-databases.sh`), runs `shared_data_layer.manage migrate --revision head`, and gates agent/ingestion startup (`condition: service_completed_successfully`). Prod deploy script includes this service and stops port 5432 conflicts.

## Next Steps
1. Run `scripts/local_smoke.sh --target prod` (or `scripts/prod_deploy_and_smoke.sh`) with a stamped upload and capture the smoke JSON.
2. Verify document upload + activation through the ingestion service (unique content hash) and attachment gating in Agent API.
3. Keep plan/tracker files updated per task; remove them when the task is complete unless told otherwise.
4. Use LocalStack for dev smokes (`scripts/local_smoke.sh --target local`) and keep retrieval/eval defaults intact.

## Known Issues / Constraints
- **Swagger Service**: Not deployed in active environments.
- **Databases**: Keep `housing` (Agent/shared) separate from `auth_db` (auth/user); do not mingle schemas.
- **No stubs/shortcuts**: Production paths must use real retrieval/ingestion/LLM; avoid preview-only heuristics.
