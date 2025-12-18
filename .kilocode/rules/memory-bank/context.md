# Context

## Current Focus
Validate the AWS path after the FastAPI ingestion replacement while keeping LLM retrieval/eval quality high and avoiding any stubs. LocalStack verification is deferred; the priority is AWS smoke (Step 9) with unique uploads and evidence capture.

### Active Tasks
- **AWS Verification (Step 9)**: Rerun the AWS curl walkthrough plus `scripts/prod_smoke_check.sh` against the real stack; keep uploads unique and reuse the same execution until resolved.
- **Ingestion Service**: Exercise the EC2 FastAPI ingestion pipeline end-to-end (MarkItDown → chunk → embed → index → activate) and ensure Agent API attachment gates stay intact.
- **Tracker Discipline**: Maintain `TASK_PLAN.md` / `TASK_PLAN_PROGRESS.md` for the ingestion work; do **not** delete them at handoff per current-session instructions.
- **Agent Eval Harness**: Pytest eval suite now lives under `services/agent-api/tests/evals` hitting prod with the eval user and preloaded MEX corpus; artifacts drop under `services/agent-api/tests/evals/artifacts/<timestamp>_<scenario>.json`. Requires `.env.prod` (loads by default) plus `OPENAI_API_KEY`.

## Recent Changes
- **FastAPI ingestion on EC2** replaced Lambda/S3; envs/scripts point `INGEST_BASE_URL` to `http://52.207.140.87:8085`, and Agent API upload now proxies to this service (no inline ingestion).
- **Ingestion pipeline tightened**: text-only, synchronous MarkItDown → contextual/proposition chunking → voyage-context-3 embeddings (default 1024-dim; supports 256/512/2048 when pgvector dimension matches), with form field `output_dimension` and trimmed source types (`pdf`, `docx`, `doc`, `txt`, `md`, `html`, `json`).
- **Shared Data Layer** centralized models/repos in `packages/shared_data_layer`; Agent API relies on it for persistence (Postgres 16, pgvector).
- **Tooling** standardized on `uv` + Python 3.13; quality gates run via `uv run` (ruff format/check, ty, pytest); defaults are AWS-first (no LocalStack unless explicitly enabled).
- **Retrieval & Eval Hardening**: Hybrid BM25 + vector with Voyage embeddings + rerank (`voyage-3-large` + `rerank-2.5`) is required (no optional fallback), HyDE-style rewrites, numeric-aware citation scoring, structured `[c#]` footnotes, and raised eval thresholds. `reembed-chunks` CLI refreshes embeddings.
- **Agent eval/smoke**: Evals and smokes run via unified `scripts/local_smoke.sh` (supports `--target local|prod` and `--env-file`). Prod uses existing demo user, reuses MEX FSAP PDF, and enforces pyodide code-tool invocation. Artifacts are flat and include tool_calls. PATH is no longer overridden in `.env.prod`; Deno PATH is set in the agent-api image, and Postgres uses its default PATH to ensure `initdb` is found.
- **Fail-fast dependencies**: OPENAI/Voyage/Valkey/rate limiter are required by default; bypass flags (`ALLOW_IN_MEMORY_VALKEY`, `ALLOW_RATE_LIMITER_BYPASS`, etc.) are test-only.
- **Attachment safety**: Documents stay blocked until ingestion is active; `/v1/chat` enforces UUID ownership for `thread_id`, with optional stateless mode.
- **LangChain integrations**: Agent and ingestion now use LangChain Voyage integrations (embeddings/rerank) and LangChain text splitters (RecursiveCharacterTextSplitter) instead of bespoke clients/splitters.
- **Dev reload compose**: `docker-compose.dev.yml` bind-mounts code for agent-api/ingestion/auth/user/shared_data_layer and runs services with reload; rebuild is only needed when dependencies change.
- **Init-migrations flow**: Compose now uses a one-shot `init-migrations` service (Dockerfile under `docker/init-migrations/`) that waits for Postgres (pgvector 16 + `scripts/init-databases.sh`), runs `shared_data_layer.manage migrate --revision head`, and gates agent/ingestion startup (`condition: service_completed_successfully`). Prod deploy script includes this service and stops port 5432 conflicts.

## Next Steps
1. Run `scripts/prod_smoke_check.sh` in AWS mode and capture command/output.
2. Verify document upload + activation through the ingestion service (unique content hash).
3. Update tracker files (`TASK_PLAN.md`, `TASK_PLAN_PROGRESS.md`) with AWS results; keep them for future sessions.
4. (Later) Re-verify LocalStack and reduced-scope demo once AWS path is stable.

## Known Issues / Constraints
- **LocalStack**: Broken/deferred; focus remains on AWS verification and AWS-first defaults.
- **Swagger Service**: Not deployed in active environments.
- **Databases**: Keep `housing` (Agent/shared) separate from `auth_db` (auth/user); do not mingle schemas.
- **No stubs/shortcuts**: Production paths must use real retrieval/ingestion/LLM; avoid preview-only heuristics.
