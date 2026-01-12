# Tasks

## Prod Smoke (FastAPI ingestion)
- **Goal**: Run ingestion → activation → attachment → chat against the live EC2 stack using the synchronous FastAPI ingestion service.
- **Discipline**: Upload a unique document each run (stamp filenames/content to avoid dedupe) and avoid parallel uploads.
- **Commands**:
  ```bash
  env_file=$(scripts/use_env.sh prod); set -a && source "$env_file" && set +a
  ENV_FILE="$env_file" ./scripts/local_smoke.sh --target prod --upload-file <file> --smoke-output /tmp/prod_smoke_$(date +%s).json

  # One-shot deploy + smoke helper (services-only by default)
  ENV_FILE="$env_file" ./scripts/prod_deploy_and_smoke.sh \
    --deploy-mode services-only \
    --smoke-file services/agent-api/evals/data/MEX_2016_Mexico\ Financial\ Sector\ Assessment\ Program\ Housing\ Finance.pdf \
    --log-file /tmp/prod_deploy_and_smoke_$(date +%s).log
  ```
- **Evidence**: Capture doc IDs/content hashes plus smoke output (`prod_sample_run.json` or the JSON path above).

## Patch Deploys on EC2 (Python Services)
- **When**: Hot-fix Agent API/auth/user without a full redeploy (prefer `scripts/deploy_stack.sh` or `scripts/prod_deploy_and_smoke.sh` when possible).
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
- Publication year metadata backfill completed in prod (269 docs updated; HTI_2016_* ambiguous case set to 2016). Backfill script/documentation lives under `packages/shared_data_layer` with logs in `packages/logs/`.

## Agent Eval Suite (Prod, Pytest)
- **Purpose**: Run RAG evals over the prod Agent API using the eval user and preloaded MEX corpus (no uploads). Artifacts are stored at `services/agent-api/tests/evals/artifacts/<timestamp>_<scenario>.json` (gitignored; flat).
- **Prereqs**: `.env.evals` (no `.env.prod` fallback) with `AGENT_BASE_URL=http://localhost:8000`, prod DB/auth URLs, `AUTH_SHARED_SECRET`, `EVAL_USER_EMAIL=eval_user@example.com`, `EVAL_USER_PASSWORD=TestPass123!`, `EVAL_USER_ID=52f96e69-2232-4215-878e-45041858ba30`, `OPENAI_API_KEY`, Voyage keys.
- **Deno**: install locally via `curl -fsSL https://deno.land/install.sh | sh` and ensure `$HOME/.deno/bin` is on PATH; do not set PATH in `.env.evals`/`.env.prod`.
- **Command**: `set -a && source .env.evals && set +a && cd services/agent-api && uv run pytest tests/evals -m eval --maxfail=1` (streaming currently skipped; re-enable with `-m eval_sse`).
- **Scenarios/Data**: Defined in `services/agent-api/tests/evals/datasets/shared_mex_arg.yaml`; uses doc IDs from the MEX corpus already active for the eval user. Metrics include citation coverage/precision/recall, retrieval relevance, latency, grounding, truthfulness, and bias via `gpt-5.1` judge.
- **Clients/Fixtures**: Harness under `services/agent-api/tests/evals/core/*` with HTTP client (blocking + SSE), runner, metrics, judge, and env/doc validation. Fails fast if required env vars are missing.

## Prod Smoke / Deploy
- **Deploy**: `env_file=$(scripts/use_env.sh prod); ENV_FILE="$env_file" ./scripts/deploy_stack.sh --mode services-only --host 52.207.140.87 --ssh-key ArchaaS/dist/vizonomy-v2-ec2-dev2.pem` (use `--mode full-redeploy` for infra + services). `scripts/prod_deploy_and_smoke.sh` wraps deploy + smoke and defaults to the FSAP PDF.
- **PATH note**: Do not override PATH in `.env.prod`; Deno PATH is set in the agent-api image. Postgres relies on its default PATH for `initdb`.
- **Smoke**: Unified `scripts/local_smoke.sh` (supports `--target prod --env-file .env.prod --upload-file <pdf> --smoke-output <file>`). Uses demo user creds from `.env.prod` (skip registration), re-ingests the MEX FSAP PDF, attaches, and asks the code-tool CAGR question plus RAG questions. Expects `pyodide_sandbox` tool invocation and citations.
