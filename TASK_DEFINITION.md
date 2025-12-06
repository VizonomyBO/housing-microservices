# Task: Enable Full Document Ingestion Pipeline (LocalStack + AWS)

This repository currently uses a reduced-scope shortcut where Markdown text is written straight into Postgres. The goal is to re-enable the real ingestion architecture—upload via API Gateway/Lambda, Step Functions pipeline (convert → chunk → embeddings → index → activate), and safe attachment handling—so that both LocalStack and AWS environments accept PDFs/Markdown/etc. through the same curl-driven flow.

> Legacy notice: `services/marker-service` is deprecated. Ignore unused services by default (including marker) unless a task explicitly calls for bringing them up.

- **2025‑12 runtime decision:** To unblock AWS verification we’re intentionally over-provisioning Lambda layers. Every ingestion Lambda must reference both shared layers (`aws_lambda_layer_version.python_deps` plus `aws_lambda_layer_version.shared_data_layer`, which now bundles the `common/` helpers). Do not try to slim per-function dependencies until the full pipeline is proven; cutting fat is a follow-up task.

---

## 1. System & Service Overview

| Component | Role |
| --- | --- |
| `services/agent-api` | FastAPI + LangGraph chat service. Handles auth, conversations, attachments, and serves `/v1/chat`. |
| `ArchaaS/` | Terraform + Lambda code for the ingestion pipeline (document upload presign, preflight validator, conversion, chunking, embeddings, index refresh, activation). |
| `services/marker-service` | Removed legacy PDF→Markdown converter (Marker). No longer built or deployed. |
| `services/auth-service` / `user-service` | Authentication stack used during smoke tests. |
| `docker-compose.yml` | Reduced-scope runtime (agent-api, auth/user services, postgres, etc.; marker removed). |

### Task Order (updated)
1. EC2 deployment and AWS smoke (Task 12, done)
2. **Enforce SQL/Polars for numeric reasoning** (Task 13) – auto-extract numeric facts via LLM into tables and route numeric prompts through Polars/SQL.
3. **Replace Lambda ingestion with a FastAPI service on EC2** (Task 14 – done) – drop the Lambda/S3 flow, add a synchronous MarkItDown-based ingestion API compatible with the existing contract, and wire all services/smoke to it.
4. LocalStack verification (Task 15) – end-to-end ingestion + smoke in LocalStack.
5. Cleanup & quality gates (Task 16) – lint/type/tests and final cleanup.

### Current State
- Lambda/S3 ingestion has been replaced by a FastAPI ingestion service running on the EC2 host (`INGEST_BASE_URL=http://52.207.140.87:8085`); smoke uploads go through this service and complete end-to-end (docs active + chat).
- Legacy ArchaaS Step Functions remain but are bypassed for prod flows; API Gateway endpoint is deprecated in favor of the new service.
- `docs/runbooks/prod_setup.md` documents the new ingestion curl flow (presign via FastAPI → form upload → poll → attach → chat).

### Desired State
1. Uploads go through the ArchaaS ingestion API (via API Gateway) in both LocalStack and AWS.
2. Lambdas perform the necessary work so chunks land in Postgres, embeddings get written, indexes refresh, documents are marked active.
3. `agent-api` refuses attachments for documents still ingesting (“Document not ready”) to keep the chat flow safe.
4. Runbooks describe full curl flows (register/upload/attach/ask) and compose/terraform commands for both environments.

---

## 2. Tooling & Environment Prep

### Required Tools
- Python 3.11+ with [`uv`](https://github.com/astral-sh/uv) (`pip install uv`), used for `services/agent-api`.
- Docker Engine 25+, Docker Compose V2.
- Terraform 1.7+ for `ArchaaS`.
- LocalStack Pro (Step Functions support) for local ingestion testing.
- AWS CLI + account credentials for real deployment.
- `jq`, `curl`.

### Base Commands

#### Python/uv environment (agent-api)
```bash
cd services/agent-api
uv sync --all-extras --dev       # once
. .venv/bin/activate
```

#### Compose (default reduced stack)
```bash
cd /path/to/repo
set -a && source .env.prod && set +a
COMPOSE_PROFILES=reduced,ops docker compose up -d --build
```

#### Compose + AWS override
```bash
set -a && source .env.prod.aws && set +a
COMPOSE_PROFILES=reduced,ops \
  docker compose \
    -f docker-compose.yml \
    -f docker-compose.prod.override.yml \
    up -d --build
```

#### Terraform (ArchaaS)
```bash
cd ArchaaS
terraform init
terraform workspace select localstack || terraform workspace new localstack
terraform apply -var-file=configs/localstack.tfvars   # LocalStack

# For AWS:
terraform workspace select prod || terraform workspace new prod
terraform apply -var-file=configs/prod.tfvars
```

(Exact tfvars files depend on credentials/endpoints; create them if missing.)

---

## 3. Implementation Plan

### 3.1 Complete Lambda Functionality

1. **`ingestion_finalizer`**
   - Update `documents` row (`status='active'`, `ingestion_stage='activate'`, timestamps, content_hash/byte_size).
   - Mark associated `ingestion_jobs` `status` (`succeeded` or `failed`).
   - Refresh materialized views if needed (`active_chunks`).
   - Ensure failure path (DeadLetter) updates DB accordingly.

2. **`embedding_writer`**
   - Verify it inserts chunk rows exactly as expected by `shared_data_layer` (id, document_id, position, chunk_type, etc.).
   - Ensure `embedding` column exists (pgvector) in both LocalStack and AWS DBs.
   - When Voyage API disabled, still insert text chunks without embeddings.

3. **`index_refresher`**
   - Replace placeholder with call to refresh `active_chunks` (using direct SQL or CLI helper).
   - Optionally enqueue other index maintenance steps; log success/failure.

4. **`table_normalizer` & `figure_captioner`**
   - They can remain pass-through but must return structured success responses quickly. Make sure they never throw so parallel branch completes.

5. **`document_upload` Lambda**
   - Confirm allowed source types include pdf/docx/md/csv, etc.
   - Response must include presigned POST fields used in curl examples.

6. **`preflight_validator`**
   - Already hashes and dedups; confirm Step Function input includes all fields used downstream (`owner_user_id`, `canonical_name`, etc.).

### 3.2 Attachment Safety in `agent-api`

Modify `/v1/conversations/{id}/attachments` logic so:
- When `document.status != 'active'` or `ingestion_stage != 'activate'`, return `400`/`409` with error `"DOCUMENT_NOT_READY"`.
- Update tests (`tests/http/test_conversations_route.py`) to cover the error case.
- Provide a clear error message; frontend will poll and retry once ingestion completes.

### 3.3 API Gateway / Upload Flow

1. Deploy ArchaaS `api_gateway.tf` resources in both LocalStack and AWS (ensure LocalStack endpoint works; for LocalStack use `localhost.localstack.cloud:4566` routing).
2. Document new env vars:
   - `INGEST_BASE_URL` (API Gateway endpoint).
   - `INGEST_UPLOAD_API_KEY` if gateway uses an API key (optional).
3. In runbooks and scripts, reference this endpoint for document upload steps instead of FastAPI’s reduced-scope shortcut.

### 3.4 Runbook Overhaul (`docs/runbooks/prod_setup.md`)

Restructure into clear sections:
1. Overview + prerequisites.
2. LocalStack deployment
   - Source `.env.prod`
   - `docker compose` for base services.
   - `terraform apply -var-file=configs/localstack.tfvars`.
   - Curl workflow (login, request presigned URL, upload file, poll doc status, create conversation, attach, SSE chat).
3. AWS deployment
   - Source `.env.prod.aws`.
   - Compose w/ override.
   - `terraform apply -var-file=configs/prod.tfvars`.
   - Same curl workflow with AWS endpoints.
4. Full-flow SSE verification + event expectations.
5. Cleanup instructions (`terraform destroy`, `docker compose down`, S3 cleanup).

Ensure `docs/runbooks/prod_setup.md` now contains the LocalStack and AWS sections plus the long curl walkthrough (already partly added in previous edits).

### 3.5 CLI / Curl Walkthrough

For both environments provide scripts/commands:
1. Obtain token (`/v1/auth/login`).
2. Call ArchaaS `/v1/documents/upload` to get presigned POST.
3. Upload PDF/Markdown file (use sample docs under `services/agent-api/tests/data/reduced_e2e/`).
4. Poll `/v1/documents/{id}` (agent-api) until status `active`.
5. Create conversation, attach document, run advanced prompt via SSE.
6. Capture SSE log (`sse_full_flow.log`) confirming `numerical_text_to_sql`, `numerical_polars_executor`, etc.

### 3.6 LocalStack Validation

1. Start LocalStack + compose stack.
2. `terraform apply` against LocalStack.
3. Run ingestion curl flow with sample PDF.
4. Run pytest suite:
   ```bash
   cd services/agent-api
   . .venv/bin/activate
   pytest
   ```
5. Run `./scripts/prod_smoke_check.sh` (still points at reduced stack but should work once doc is active).
6. Stream `/v1/chat` SSE; verify events show controller/numerical nodes and `requires_sql=true`.
7. Tear down LocalStack resources (`terraform destroy`, `docker compose down -v`).

### 3.7 AWS Validation

1. Apply Terraform with real AWS tfvars (buckets, Step Function, Lambdas, RDS).
2. Start compose stack with `.env.prod.aws` + override.
3. Repeat curl upload/attach/chat flow using the AWS API Gateway URL.
4. Run pytest locally (same as above).
5. Run `./scripts/prod_smoke_check.sh` pointing at AWS endpoints (ensure `.env.prod.aws` values match).
6. Confirm SSE log shows identical numerical events with `requires_sql=true`.
7. If any Terraform/AWS errors occur that block verification, stop and request help.

---

## 4. File References & Key Commands

| Purpose | File(s) |
| --- | --- |
| Reduced ingestion helpers | `services/agent-api/src/services/ingestion_job_service.py` |
| Attachment API | `services/agent-api/src/agent_api/http/routes/conversations.py` (check attachments handler) |
| SSE/numerical pipeline | `services/agent-api/src/services/langgraph_runner.py`, `src/subgraphs/numerical/*` |
| ArchaaS Lambdas | `ArchaaS/lambdas/**/handler.py` |
| Step Function definition | `ArchaaS/step_functions/document_ingestion_workflow.asl.json` |
| Terraform stack | `ArchaaS/*.tf`, `ArchaaS/configs/*.tfvars` |
| Curl walkthrough docs | `docs/runbooks/prod_setup.md` |

### Helpful Commands
- Dump docker logs: `docker compose logs -f agent-api`
- SSE tail: `curl -N ... "$AGENT_BASE_URL/v1/chat" | tee sse_full_flow.log`
- Terraform destroy (LocalStack): `terraform destroy -var-file=configs/localstack.tfvars`
- Terraform destroy (AWS): `terraform destroy -var-file=configs/prod.tfvars`

---

## 5. Success Criteria
1. **Lambdas**: `ingestion_finalizer`, `index_refresher`, and `embedding_writer` perform real work; Step Function completes without placeholders.
2. **Attachment Safety**: Attempting to attach a document mid-ingestion returns a clear error.
3. **LocalStack Flow**: Full curl walkthrough succeeds, SSE logs show numerical events, smoke script passes, pytest clean.
4. **AWS Flow**: Same as above using real AWS resources.
5. **Docs**: `docs/runbooks/prod_setup.md` clearly explains both setups and the new curl flow.
6. **No regressions**: Existing tests remain green; `./scripts/prod_smoke_check.sh` outputs SQL trace data for numerical prompts.

---


## Env files

The following files exist in the root of the repo, but are gitignored, in case you can't open them here is their complete content.

### .env
```
# =============================================================================
# Root Environment Template (Copy to .env)
# =============================================================================
# How to use:
# 1. cp env.example .env
# 2. Update secrets (passwords, API keys) with non-default values.
# 3. Keep .env out of version control. Never commit real credentials.
#
# This template powers the root docker-compose stack and every service beneath it.
# Variables are grouped by concern so you can quickly switch between reduced and
# full profiles, toggle LocalStack, and share common secrets across services.
# =============================================================================

# -----------------------------------------------------------------------------
# Compose & Runtime Profiles
# -----------------------------------------------------------------------------
COMPOSE_PROJECT_NAME=vizonomy
STACK_PROFILE=reduced            # reduced | full (mirrors demo vs full stack docs)
SERVICE_MODE=reduced             # consumed by agent-api to gate reduced/full behavior
COMPOSE_PROFILES=default         # override (e.g., agent-api,full,ops) when running compose
REDUCED_SCOPE_ENABLED=1          # see Reduced Scope Flags section for additional knobs
USE_LOCALSTACK=1                 # 1=route AWS clients to LocalStack, 0=use real AWS endpoints
LOCALSTACK_HOST=localstack
LOCALSTACK_EDGE_PORT=4566
LOCALSTACK_SERVICES=s3,sqs,sns,events,secretsmanager
LOCALSTACK_DEBUG=0

# -----------------------------------------------------------------------------
# Networking & Ports (host-side overrides)
# -----------------------------------------------------------------------------
POSTGRES_PORT=5433              # maps postgres container 5432 -> host
AGENT_API_PORT=8000              # maps uvicorn port to host; also used by uvicorn in dev
AUTH_SERVICE_PORT=5001           # host port for auth-service (container listens on 5000)
USER_SERVICE_PORT=5002           # host port for user-service (container listens on 5001)
SWAGGER_SERVICE_PORT=3000        # host port for swagger-service
VALKEY_PORT=6379                 # host port for valkey cache (full profile)
OTEL_COLLECTOR_GRPC_PORT=4317
OTEL_COLLECTOR_HTTP_PORT=4318

# -----------------------------------------------------------------------------
# PostgreSQL & Shared Databases
# -----------------------------------------------------------------------------
POSTGRES_DB=housing
AUTH_DB=auth_db
POSTGRES_USER=vizonomy_user
POSTGRES_PASSWORD=iSQOjvXTBzJBcGCCt4koPDno
DATABASE_URL=postgresql+asyncpg://agent_api:agent_api_pass@postgres:5432/agent_reduced
AGENT_API_DB=agent_reduced
AGENT_API_DB_USER=agent_api
AGENT_API_DB_PASSWORD=agent_api_pass

# -----------------------------------------------------------------------------
# Auth/User Service Secrets
# -----------------------------------------------------------------------------
JWT_SECRET_KEY=a90eeae37c4406b52a6776a363e5a2733e5ee6d146bd7972b38d8aeaf60e9924
JWT_ACCESS_TOKEN_EXPIRES=900
JWT_REFRESH_TOKEN_EXPIRES=2592000
JWT_ACCESS_TOKEN_EXPIRES_MINUTES=15
SECRET_KEY=dev-secret-key-change-in-production # what is this? :v
AUTH_SHARED_SECRET=a90eeae37c4406b52a6776a363e5a2733e5ee6d146bd7972b38d8aeaf60e9924
COOKIE_SECURE=False              # set True when running behind HTTPS
CORS_ORIGINS=http://localhost:3000,http://localhost:5001,http://localhost:5002,http://localhost:5173
FLASK_ENV=production
FLASK_DEBUG=False
NODE_ENV=production
LOG_LEVEL=info
RATE_LIMIT_PER_MINUTE=60

# SMTP / Email fallbacks (auth-service)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
EMAIL_FROM=noreply@vizonomy.com

# -----------------------------------------------------------------------------
# Agent API Settings & Metrics
# -----------------------------------------------------------------------------
SERVICE_NAME=agent-api
METRICS_NAMESPACE=agent-api
METRICS_AUTH_HEADER=Authorization
METRICS_AUTH_SCHEME=Bearer
METRICS_AUTH_TOKEN=

# Reduced Scope Flags (docs/epics/035.md)
REDUCED_SCOPE_TEXT_ONLY_CHUNKS=1
REDUCED_SCOPE_DISABLE_VALKEY=1
REDUCED_SCOPE_DISABLE_RATE_LIMITING=1
REDUCED_SCOPE_EMIT_DEMO_EVENTS=1
REDUCED_SCOPE_ALLOWED_CHUNK_TYPES=text

# -----------------------------------------------------------------------------
# AWS / LocalStack & Storage Defaults
# -----------------------------------------------------------------------------
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=localstack
AWS_SECRET_ACCESS_KEY=localstack
# Leave blank to auto-derive LocalStack vs AWS endpoints from USE_LOCALSTACK
# AWS_ENDPOINT_URL=https://n01e1zyyw6.execute-api.us-east-1.amazonaws.com
RAW_DOCUMENTS_BUCKET=vizonomy-raw-docs-dev-ff0df41e
PROCESSED_BUCKET=vizonomy-processed-artifacts-dev-ff0df41e
OPENAI_API_KEY=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
VOYAGE_API_KEY=pa-1cGXsHRKMKqBKW0eifgcYrXMd8OiiXwJ813-58mTuxu
VOYAGE_EMBEDDING_MODEL=voyage-3

# -----------------------------------------------------------------------------
# Valkey / Cache Configuration (full profile only)
# -----------------------------------------------------------------------------
VALKEY_URL=
VALKEY_USERNAME=
VALKEY_PASSWORD=
VALKEY_PASSWORD_FILE=
VALKEY_DB=
VALKEY_MAX_CONNECTIONS=64
VALKEY_SOCKET_TIMEOUT_SECONDS=3.0
VALKEY_CONNECT_TIMEOUT_SECONDS=1.0
VALKEY_HEALTHCHECK_INTERVAL_SECONDS=30.0
VALKEY_POOL_IDLE_TIMEOUT_SECONDS=60.0
VALKEY_RETRY_ATTEMPTS=3
VALKEY_RETRY_BACKOFF_SECONDS=0.05
VALKEY_RETRY_BACKOFF_MULTIPLIER=2.0
VALKEY_RETRY_MAX_BACKOFF_SECONDS=0.5
VALKEY_RETRY_JITTER_SECONDS=0.01
VALKEY_DEFAULT_TTL_SECONDS=172800
VALKEY_SENTINEL_SERVICE=
VALKEY_CLUSTER_MODE=0
VALKEY_CLIENT_NAME=agent-api
VALKEY_TLS_CA_CERT=
VALKEY_TLS_CLIENT_CERT=
VALKEY_TLS_CLIENT_KEY=
VALKEY_TLS_SKIP_VERIFY=0

# -----------------------------------------------------------------------------
# Service URLs (inter-service RPC)
# -----------------------------------------------------------------------------
AUTH_SERVICE_URL=http://auth-service:5000
USER_SERVICE_URL=http://user-service:5001
ACCOUNT_SERVICE_URL=http://auth-service:5000

# -----------------------------------------------------------------------------
# Developer Tips
# -----------------------------------------------------------------------------
# - Copy this file to .env for every profile. Switch between reduced/full stacks by
#   toggling STACK_PROFILE + COMPOSE_PROFILES (e.g., `COMPOSE_PROFILES=agent-api` for demo
#   or `COMPOSE_PROFILES=full,ops` for the entire stack).
# - When USE_LOCALSTACK=0, set AWS credentials + endpoints to real AWS values.
# - For custom overrides, create `.env.local` (gitignored) and source it before compose.
REDUCED_SCOPE_USE_REAL_TOOLS=1
REAL_REDUCED_E2E_TOOLS=1
REDUCED_E2E_VERIFY_REAL_TOOLS=1   # optional but recommended
```

.env.prod
```
# =============================================================================
# Production Environment (Reduced Scope)
# =============================================================================
# 1. Update every placeholder marked CHANGE_ME with strong secrets before running.
# 2. source env.prod && docker compose --profile reduced up -d --build
# 3. Flip USE_LOCALSTACK between 1 (default) and 0 per docs/runbooks/prod_setup.md.
# =============================================================================

COMPOSE_PROJECT_NAME=vizonomy-prod
STACK_PROFILE=reduced
SERVICE_MODE=reduced
COMPOSE_PROFILES=reduced,ops

# -----------------------------------------------------------------------------
# AWS / LocalStack toggle
# -----------------------------------------------------------------------------
# USE_LOCALSTACK=1 routes all AWS traffic to the bundled LocalStack container.
# Switch to 0 + provide real AWS creds/region to hit production AWS instead.
USE_LOCALSTACK=1
LOCALSTACK_HOST=localstack
LOCALSTACK_EDGE_PORT=4566
LOCALSTACK_SERVICES=s3,sqs,sns,events,secretsmanager
LOCALSTACK_DEBUG=0
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=localstack
AWS_SECRET_ACCESS_KEY=localstack
AWS_ENDPOINT_URL=

# -----------------------------------------------------------------------------
# Networking (adjust ports if exposing via ALB / load balancer)
# -----------------------------------------------------------------------------
POSTGRES_PORT=5433
AGENT_API_PORT=8000
AUTH_SERVICE_PORT=5001
USER_SERVICE_PORT=5002
SWAGGER_SERVICE_PORT=3000
MARKER_SERVICE_PORT=8004
VALKEY_PORT=6379
OTEL_COLLECTOR_GRPC_PORT=4317
OTEL_COLLECTOR_HTTP_PORT=4318

# Public URLs used by scripts/tests (override when frontends hit via ALB)
AGENT_BASE_URL=http://localhost:8000
AUTH_BASE_URL=http://localhost:5001

# -----------------------------------------------------------------------------
# Postgres / shared DBs
# -----------------------------------------------------------------------------
POSTGRES_DB=housing
AUTH_DB=auth_db
POSTGRES_USER=vizonomy_user
POSTGRES_PASSWORD=iSQOjvXTBzJBcGCCt4koPDno
DATABASE_URL=postgresql+asyncpg://agent_api:rXfQ4rXw2C6JcX9eYtrf@postgres:5432/agent_reduced
AGENT_API_DB=agent_reduced
AGENT_API_DB_USER=agent_api
AGENT_API_DB_PASSWORD=rXfQ4rXw2C6JcX9eYtrf

# -----------------------------------------------------------------------------
# Auth/User secrets
# -----------------------------------------------------------------------------
JWT_SECRET_KEY=a90eeae37c4406b52a6776a363e5a2733e5ee6d146bd7972b38d8aeaf60e9924
JWT_ACCESS_TOKEN_EXPIRES=900
JWT_REFRESH_TOKEN_EXPIRES=2592000
JWT_ACCESS_TOKEN_EXPIRES_MINUTES=15
SECRET_KEY=34a3f9c5cce84f00bfce2da03b8f516ccf2d3d9c8b6de0b81d8e827b0d4d3e7d
AUTH_SHARED_SECRET=a90eeae37c4406b52a6776a363e5a2733e5ee6d146bd7972b38d8aeaf60e9924
COOKIE_SECURE=False
CORS_ORIGINS=
FLASK_ENV=production
FLASK_DEBUG=False
NODE_ENV=production
LOG_LEVEL=info
RATE_LIMIT_PER_MINUTE=60
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
EMAIL_FROM=noreply@vizonomy.com

# -----------------------------------------------------------------------------
# Agent API reduced-scope flags
# -----------------------------------------------------------------------------
REDUCED_SCOPE_ENABLED=1
UVICORN_LOG_LEVEL=info
AGENT_API_LOG_LEVEL=info
REDUCED_SCOPE_TEXT_ONLY_CHUNKS=1
REDUCED_SCOPE_DISABLE_VALKEY=1
REDUCED_SCOPE_DISABLE_RATE_LIMITING=1
REDUCED_SCOPE_EMIT_DEMO_EVENTS=1
REDUCED_SCOPE_ALLOWED_CHUNK_TYPES=text
REDUCED_SCOPE_USE_REAL_TOOLS=1
REAL_REDUCED_E2E_TOOLS=1
REDUCED_E2E_VERIFY_REAL_TOOLS=1
METRICS_NAMESPACE=agent-api
SERVICE_NAME=agent-api

# -----------------------------------------------------------------------------
# LLM / embeddings (replace with production keys)
# -----------------------------------------------------------------------------
OPENAI_API_KEY=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
VOYAGE_API_KEY=pa-1cGXsHRKMKqBKW0eifgcYrXMd8OiiXwJ813-58mTuxu
VOYAGE_EMBEDDING_MODEL=voyage-3
RAW_DOCUMENTS_BUCKET=vizonomy-raw-docs-prod
PROCESSED_BUCKET=vizonomy-processed-artifacts-prod

# -----------------------------------------------------------------------------
# Demo user used by scripts/prod_smoke_check.sh
# -----------------------------------------------------------------------------
PROD_DEMO_EMAIL=demo.client@example.com
PROD_DEMO_USERNAME=demo_client
PROD_DEMO_PASSWORD=ChangeMe!123
PROD_DEMO_FIRST_NAME=Demo
PROD_DEMO_LAST_NAME=Client
PROD_DEMO_COUNTRY=USA
PROD_DEMO_TAG=demo
```

.env.prod.aws
```
# =============================================================================
# Production Environment (Reduced Scope)
# =============================================================================
# 1. Update every placeholder marked CHANGE_ME with strong secrets before running.
# 2. source env.prod && docker compose --profile reduced up -d --build
# 3. Flip USE_LOCALSTACK between 1 (default) and 0 per docs/runbooks/prod_setup.md.
# =============================================================================

COMPOSE_PROJECT_NAME=vizonomy-prod
STACK_PROFILE=reduced
SERVICE_MODE=reduced
COMPOSE_PROFILES=reduced,ops

# -----------------------------------------------------------------------------
# AWS / LocalStack toggle
# -----------------------------------------------------------------------------
# USE_LOCALSTACK=1 routes all AWS traffic to the bundled LocalStack container.
# Switch to 0 + provide real AWS creds/region to hit production AWS instead.
USE_LOCALSTACK=0
# LocalStack settings remain for parity but are ignored when USE_LOCALSTACK=0
LOCALSTACK_HOST=localstack
LOCALSTACK_EDGE_PORT=4566
LOCALSTACK_SERVICES=s3,sqs,sns,events,secretsmanager
LOCALSTACK_DEBUG=0
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIAU4ZRWOAEIWVRUNOQ
AWS_SECRET_ACCESS_KEY=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
AWS_SESSION_TOKEN=
AWS_ENDPOINT_URL=

# -----------------------------------------------------------------------------
# Networking (adjust ports if exposing via ALB / load balancer)
# -----------------------------------------------------------------------------
POSTGRES_PORT=5433
AGENT_API_PORT=8000
AUTH_SERVICE_PORT=5001
USER_SERVICE_PORT=5002
SWAGGER_SERVICE_PORT=3000
MARKER_SERVICE_PORT=8004
VALKEY_PORT=6379
OTEL_COLLECTOR_GRPC_PORT=4317
OTEL_COLLECTOR_HTTP_PORT=4318

# Public URLs used by scripts/tests (override when frontends hit via ALB)
AGENT_BASE_URL=https://agent-api.mycompany.com
AUTH_BASE_URL=https://auth-api.mycompany.com

# -----------------------------------------------------------------------------
# Postgres / shared DBs
# -----------------------------------------------------------------------------
POSTGRES_DB=housing
AUTH_DB=auth_db
POSTGRES_USER=vizonomy_user
POSTGRES_PASSWORD=iSQOjvXTBzJBcGCCt4koPDno
DATABASE_URL=postgresql+asyncpg://agent_api:rXfQ4rXw2C6JcX9eYtrf@postgres:5432/agent_reduced
AUTH_DATABASE_URL=postgresql+asyncpg://agent_api:rXfQ4rXw2C6JcX9eYtrf@postgres:5432/auth_db
AGENT_API_DB=agent_reduced
AGENT_API_DB_USER=agent_api
AGENT_API_DB_PASSWORD=rXfQ4rXw2C6JcX9eYtrf

# -----------------------------------------------------------------------------
# Auth/User secrets
# -----------------------------------------------------------------------------
JWT_SECRET_KEY=a90eeae37c4406b52a6776a363e5a2733e5ee6d146bd7972b38d8aeaf60e9924
JWT_ACCESS_TOKEN_EXPIRES=900
JWT_REFRESH_TOKEN_EXPIRES=2592000
JWT_ACCESS_TOKEN_EXPIRES_MINUTES=15
SECRET_KEY=34a3f9c5cce84f00bfce2da03b8f516ccf2d3d9c8b6de0b81d8e827b0d4d3e7d
AUTH_SHARED_SECRET=a90eeae37c4406b52a6776a363e5a2733e5ee6d146bd7972b38d8aeaf60e9924
COOKIE_SECURE=False
CORS_ORIGINS=
FLASK_ENV=production
FLASK_DEBUG=False
NODE_ENV=production
LOG_LEVEL=info
RATE_LIMIT_PER_MINUTE=60
SMTP_SERVER=email-smtp.us-east-1.amazonaws.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
EMAIL_FROM=noreply@vizonomy.com

# -----------------------------------------------------------------------------
# Agent API reduced-scope flags
# -----------------------------------------------------------------------------
REDUCED_SCOPE_ENABLED=1
UVICORN_LOG_LEVEL=info
AGENT_API_LOG_LEVEL=info
REDUCED_SCOPE_TEXT_ONLY_CHUNKS=1
REDUCED_SCOPE_DISABLE_VALKEY=1
REDUCED_SCOPE_DISABLE_RATE_LIMITING=1
REDUCED_SCOPE_EMIT_DEMO_EVENTS=1
REDUCED_SCOPE_ALLOWED_CHUNK_TYPES=text
REDUCED_SCOPE_USE_REAL_TOOLS=1
REAL_REDUCED_E2E_TOOLS=1
REDUCED_E2E_VERIFY_REAL_TOOLS=1
METRICS_NAMESPACE=agent-api
SERVICE_NAME=agent-api

# -----------------------------------------------------------------------------
# LLM / embeddings (replace with production keys)
# -----------------------------------------------------------------------------
OPENAI_API_KEY=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
VOYAGE_API_KEY=pa-1cGXsHRKMKqBKW0eifgcYrXMd8OiiXwJ813-58mTuxu
VOYAGE_EMBEDDING_MODEL=voyage-3
RAW_DOCUMENTS_BUCKET=vizonomy-raw-docs-prod
PROCESSED_BUCKET=vizonomy-processed-artifacts-prod

# -----------------------------------------------------------------------------
# Demo user used by scripts/prod_smoke_check.sh
# -----------------------------------------------------------------------------
PROD_DEMO_EMAIL=demo.client@example.com
PROD_DEMO_USERNAME=demo_client
PROD_DEMO_PASSWORD=ChangeMe!123
PROD_DEMO_FIRST_NAME=Demo
PROD_DEMO_LAST_NAME=Client
PROD_DEMO_COUNTRY=USA
PROD_DEMO_TAG=demo
```
