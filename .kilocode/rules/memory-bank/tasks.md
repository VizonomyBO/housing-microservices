# Tasks

## AWS Smoke (Step 9 – Current Focus)
- **Goal**: Rerun the AWS curl walkthrough and `scripts/prod_smoke_check.sh` against the live stack.
- **Discipline**: Upload a unique document each run (or reuse the same execution until resolved); do **not** trigger parallel uploads if a flow is pending. Poll `/v1/documents?content_hash=…`, inspect the Step Functions execution, and review per-Lambda/ingestion logs before retrying.
- **Commands**:
  ```bash
  env_file=$(scripts/use_env.sh prod); set -a && source "$env_file" && set +a
  ENV_FILE="$env_file" ./scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_$(date +%s).log
  ```
- **Evidence**: Record doc IDs/content hashes and execution ARNs in tracker (`TASK_PLAN.md` / `TASK_PLAN_PROGRESS.md` stay in place per current-session rules).

## Patch Deploys on EC2 (Python Services)
- **When**: Hot-fix Agent API/auth/user without full redeploy.
- **Prep**:
  ```bash
  env_file=$(scripts/use_env.sh prod); set -a && source "$env_file" && set +a
  ssh -i ArchaaS/dist/vizonomy-v2-ec2-dev2.pem ec2-user@${POSTGRES_HOST} "echo ok && uptime"
  ```
- **Copy + restart**:
  ```bash
  scp -i ArchaaS/dist/vizonomy-v2-ec2-dev2.pem path/to/local_file.py ec2-user@${POSTGRES_HOST}:/tmp/local_file.py
  sudo docker ps --format '{{.Names}}' | grep agent-api
  sudo docker cp /tmp/local_file.py <container>:/app/services/agent-api/src/.../file.py
  sudo docker compose -f /opt/housing-microservices/docker-compose.ec2.yml restart agent-api
  sudo docker ps --format '{{.Names}} {{.Status}}' | grep agent-api
  curl http://localhost:8000/health
  ```
- **Notes**: Repeat `docker cp` per file before one restart; use `.env.prod`; keep Swagger disabled unless explicitly needed.

## End-to-End Ingestion Smoke Suite (Optional)
- **Location**: `packages/shared_data_layer/tests/test_end_to_end_ingestion.py` (opt-in, defaults to skip).
- **Command**:
  ```bash
  uv run pytest --end-to-end packages/shared_data_layer/tests/test_end_to_end_ingestion.py -n 0
  ```
- **Coverage**: MarkItDown → chunk → embed → index → activation + KG rollups.

## Fail-Fast Dependencies (Agent API)
- OpenAI is required for chat/numerical flows; no text-only fallbacks. Set `OPENAI_API_KEY`.
- Valkey is required unless `ALLOW_IN_MEMORY_VALKEY=1` (tests/dev only); guardrails must import at runtime.
- Rate limiter must be real or explicitly bypassed via `ALLOW_RATE_LIMITER_BYPASS=1` (tests/dev only).
- Lingua stub is allowed only with `ALLOW_STUB_LANGUAGE_DETECTOR=1` for tests; otherwise Lingua must load.
- Reduced-scope runtime/CLI now refuse to run unless `REDUCED_SCOPE_ENABLED=1`; production paths should use real ingestion/exports.

## Recent Updates
- Auth/user services aligned to cache-free stack; images built locally via `docker compose build auth-service user-service` (not pushed to any registry yet).

## Agent Eval Suite (Prod, Pytest)
- **Purpose**: Run RAG evals over the prod Agent API using the eval user and preloaded MEX corpus (no uploads). Artifacts are stored at `services/agent-api/tests/evals/artifacts/<timestamp>_<scenario>.json` (gitignored; flat).
- **Prereqs**: `.env.evals` mirrors `.env.prod` but sets `AGENT_BASE_URL=http://localhost:8000` for local Agent API against the prod DB/auth; requires `EVAL_USER_EMAIL=eval_user@example.com`, `EVAL_USER_PASSWORD=TestPass123!`, `EVAL_USER_ID=52f96e69-2232-4215-878e-45041858ba30`, `OPENAI_API_KEY`, Voyage keys. Loader fails if `.env.evals` and `.env.prod` are both missing.
- **Command**: `set -a && source .env.evals && set +a && cd services/agent-api && uv run pytest tests/evals -m eval` (streaming currently skipped; re-enable with `-m eval_sse`).
- **Scenarios/Data**: Defined in `services/agent-api/tests/evals/datasets/shared_mex_arg.yaml`; uses doc IDs from the MEX corpus already active for the eval user. Metrics include citation coverage/precision/recall, retrieval relevance, latency, grounding, truthfulness, and bias via `gpt-5.1` judge.
- **Clients/Fixtures**: Harness under `services/agent-api/tests/evals/core/*` with HTTP client (blocking + SSE), runner, metrics, judge, and env/doc validation. Fails fast if required env vars are missing.

## Prod Smoke / Deploy
- **Deploy**: `scripts/prod_deploy_and_smoke.sh --deploy-mode services-only --no-build --env-file .env.prod --smoke-file services/agent-api/evals/data/MEX_2016_Mexico\ Financial\ Sector\ Assessment\ Program\ Housing\ Finance.pdf`. Deploy copies repo to `/opt/housing-microservices` on EC2 and runs `docker-compose.ec2.yml` (Postgres included).
- **PATH note**: Do not override PATH in `.env.prod`; Deno PATH is set in the agent-api image. Postgres relies on its default PATH for `initdb`.
- **Smoke**: Unified `scripts/local_smoke.sh` (supports `--target prod --env-file .env.prod --upload-file <pdf> --smoke-output <file>`). Uses demo user creds from `.env.prod` (skip registration), re-ingests the MEX FSAP PDF, attaches, and asks the code-tool CAGR question plus RAG questions. Expects `pyodide_sandbox` tool invocation and citations.
