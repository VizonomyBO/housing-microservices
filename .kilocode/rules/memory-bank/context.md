# Context

## Current Focus
Validate the AWS path after the FastAPI ingestion replacement while keeping LLM retrieval/eval quality high and avoiding any stubs. LocalStack verification is deferred; the priority is AWS smoke (Step 9) with unique uploads and evidence capture.

### Active Tasks
- **AWS Verification (Step 9)**: Rerun the AWS curl walkthrough plus `scripts/prod_smoke_check.sh` against the real stack; keep uploads unique and reuse the same execution until resolved.
- **Ingestion Service**: Exercise the EC2 FastAPI ingestion pipeline end-to-end (MarkItDown → chunk → embed → index → activate) and ensure Agent API attachment gates stay intact.
- **Tracker Discipline**: Maintain `TASK_PLAN.md` / `TASK_PLAN_PROGRESS.md` for the ingestion work; do **not** delete them at handoff per current-session instructions.

## Recent Changes
- **FastAPI ingestion on EC2** replaced Lambda/S3; envs/scripts point `INGEST_BASE_URL` to `http://52.207.140.87:8085`.
- **Shared Data Layer** centralized models/repos in `packages/shared_data_layer`; Agent API relies on it for persistence (Postgres 16, pgvector).
- **Tooling** standardized on `uv` + Python 3.13; quality gates run via `uv run` (ruff format/check, ty, pytest).
- **Retrieval & Eval Hardening**: Hybrid BM25 + vector with Voyage embeddings + rerank (`voyage-3-large` + `rerank-2.5`), HyDE-style rewrites, numeric-aware citation scoring, structured `[c#]` footnotes, and raised eval thresholds. `reembed-chunks` CLI refreshes embeddings.
- **Attachment safety**: Documents stay blocked until ingestion is active; `/v1/chat` enforces UUID ownership for `thread_id`, with optional stateless mode.

## Next Steps
1. Run `scripts/prod_smoke_check.sh` in AWS mode and capture command/output.
2. Verify document upload + activation through the ingestion service (unique content hash).
3. Update tracker files (`TASK_PLAN.md`, `TASK_PLAN_PROGRESS.md`) with AWS results; keep them for future sessions.
4. (Later) Re-verify LocalStack and reduced-scope demo once AWS path is stable.

## Known Issues / Constraints
- **LocalStack**: Broken/deferred; focus remains on AWS verification.
- **Swagger Service**: Not deployed in active environments.
- **Databases**: Keep `housing` (Agent/shared) separate from `auth_db` (auth/user); do not mingle schemas.
- **No stubs/shortcuts**: Production paths must use real retrieval/ingestion/LLM; avoid preview-only heuristics.
