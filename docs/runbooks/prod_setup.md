# Production Runbook (AWS-first ingestion)

End-to-end guide for deploying the prod stack (Terraform + EC2 services), running the AWS curl walkthrough (login → presign via ingestion service → form upload → poll → attach → chat), and exposing a frontend-ready endpoint reference. Swagger is unhealthy in prod—use the curls below instead.

## 1) Live endpoints (AWS)
- `AGENT_BASE_URL=http://52.207.140.87:8000`
- `AUTH_BASE_URL=http://52.207.140.87:5001`
- `INGEST_BASE_URL=http://52.207.140.87:8085` (FastAPI ingestion service on EC2)
- Auth demo creds: `PROD_DEMO_EMAIL` / `PROD_DEMO_PASSWORD` from `.env.prod`.  
Run `env_file=$(scripts/use_env.sh prod)` then `set -a && source "$env_file" && set +a` to load them.

## 2) Environment & prerequisites
- Tools: Docker 25+ with Compose V2, Terraform 1.7+, AWS CLI, `jq`, `curl`. Python/uv optional (`scripts/ensure_tooling_env.sh` seeds `.venv.tooling`).
- Env toggle (required before any command):  
  ```bash
  env_file=$(scripts/use_env.sh prod)   # USE_LOCALSTACK=0, real AWS endpoints
  set -a && source "$env_file" && set +a
  ```
- Env files: `.env.local` (LocalStack), `.env.dev` (cloud data plane with local services), `.env.prod` (AWS). Each file sets `ENV_FILE` so compose/env scripts pick up the right configuration.
- LocalStack is deferred per user directive; keep USE_LOCALSTACK=0 for this runbook.

## 2.5) CORS configuration (agent-api/auth-service)
- `agent-api` now reads `AGENT_API_CORS_ORIGINS` (falls back to `CORS_ORIGINS`); auth/user-service continue to use `CORS_ORIGINS`.
- During the current testing phase, `.env.prod` (and `.env.dev` if you use it) set both `AGENT_API_CORS_ORIGINS=*` and `CORS_ORIGINS=*` to allow any origin. Wildcards automatically disable credentials to satisfy FastAPI/Starlette rules.
- To allowlist specific origins/IPs instead, edit the env file(s) before redeploy:  
  `AGENT_API_CORS_ORIGINS=http://12.34.56.78:3000,https://partner.example` and mirror the list in `CORS_ORIGINS` for auth/user-service. Then redeploy (`ENV_FILE=.env.prod ./scripts/deploy_ec2_services.sh ...`) so containers reload the values.
- Revert to `*` if you need fully open CORS again during testing.

## 3) Frontend integration quick reference
- **Auth (AUTH_BASE_URL)**
  - Login: `POST /v1/auth/login` with `{"login": "...", "password": "..."}` → `{access_token, refresh_token, user_id}`.
- **Agent API (AGENT_BASE_URL)**
  - Health: `GET /health`, `GET /v1/health`.
  - Documents: `GET /v1/documents?page=1&page_size=50&content_hash=<sha256>` returns status (`pending|active|failed`) and `ingestion_stage`. Failed docs include `metadata.ingestion_failure`.
  - Conversations: `POST /v1/conversations` body `{"country_code":"US","namespace":"prod-demo"}` → `{conversation_id}`.
  - Attachments: `POST /v1/conversations/{id}/attachments` body `{"document_id":"...","auto_attach_base_docs":false}`. Returns `409 DOCUMENT_NOT_READY` until the doc is `active`. For bulk, call `POST /v1/conversations/{id}/attachments/bulk` with `{"document_ids":["...","..."]}` (frontend can fetch IDs via `/v1/documents?country_code=ARG` first).
  - Chat (SSE): `POST /v1/chat` with headers `Accept: text/event-stream`, `Authorization: Bearer $TOKEN`, body:
    ```json
    {
      "thread_id": "<conversation_id>",
      "message": {"type": "user", "content": "KPI/ledger question"},
      "constraints": {"country_code": "US", "auto_attach_base_docs": false}
    }
    ```
    Expect `requires_sql: true` for KPI/ledger prompts and nodes `numerical_text_to_sql`, `numerical_polars_executor`, `numerical_result_validator`.
- **Ingestion FastAPI service (INGEST_BASE_URL, port 8085)**
  - Presign: `POST /v1/documents/upload` with JSON:
    ```json
    {
      "document_name": "Prod Smoke 1738880000",
      "source_type": "pdf",
      "country_code": "US",
      "language": "en",
      "file_size_bytes": 123456,
      "tags": ["demo","ingestion"],
      "metadata": {"scenario": "prod_smoke"}
    }
    ```
    Requires `Authorization: Bearer $TOKEN` (and `x-api-key` if configured). Response includes `document_id`, `upload.url`, and `upload.fields` (SigV4 POST fields per AWS docs: `policy`, `x-amz-credential`, `x-amz-algorithm`, `x-amz-signature`, `Content-Type`, etc.).
  - Upload to S3: `curl -X POST "$UPLOAD_URL" -F "key=..." ... -F "file=@/path/to.pdf;type=$CONTENT_TYPE"`.

## 4) Idempotent prod deploy (infra + EC2 services)
Use the new entrypoint to apply Terraform and restart the EC2 compose stack in one go:
```bash
ENV_FILE=${ENV_FILE:-.env.prod} ./scripts/deploy_prod_stack.sh --open-ports
```
What it does:
- Sources the selected env (defaults to `.env.prod`).
- Runs `scripts/provision_remote_stack.sh` (Terraform `-chdir=ArchaaS apply -var-file=terraform.v2.tfvars` in workspace `prod`, optional `--destroy-first` if passed).
- Updates `POSTGRES_HOST` in the env with the latest EC2 IP, reruns `scripts/setup_remote_databases.sh`.
- Calls `scripts/deploy_ec2_services.sh` to rsync code, use `.env.prod` on the host, open ports (if `--open-ports`), and start `agent-api`, `auth-service`, `user-service` via `docker-compose.ec2.yml`.
Flags: `--skip-terraform`, `--skip-deploy`, `--include-swagger`, `--no-build`, `--no-sync`, `--tfvars <file>`, `--workspace <name>`.

## 5) AWS curl walkthrough (manual)
The commands below run entirely against the live AWS endpoints and the new ingestion FastAPI service on EC2. Use fresh copies of the sample PDFs to bypass content-hash dedupe.

1. **Set env + token**
   ```bash
   env_file=$(scripts/use_env.sh aws)
   set -a && source "$env_file" && set +a
   TOKEN=$(curl -sS -X POST "$AUTH_BASE_URL/v1/auth/login" \
     -H 'Content-Type: application/json' \
     -d "{\"login\":\"$PROD_DEMO_EMAIL\",\"password\":\"$PROD_DEMO_PASSWORD\"}" \
     | jq -r '.access_token')
   ```
2. **Pick a unique PDF (repeat for policy/ledger/KPI)**  
   ```bash
   SRC=services/agent-api/tests/data/reduced_e2e/doc_policy.pdf   # or doc_ledger.pdf / doc_kpi.pdf
   FILE=/tmp/prod_ingest_$(basename "$SRC" .pdf)_$(date +%s).pdf
   cp "$SRC" "$FILE"
   printf '\n%% smoke-run %s\n' "$(date -Iseconds)" >> "$FILE"   # stamp to avoid content-hash dedupe
   FILE_SIZE=$(stat -c%s "$FILE")
   FILE_HASH=$(sha256sum "$FILE" | awk '{print $1}')
   ```
3. **Request presigned upload via ingestion service** (FastAPI on EC2; no S3 POST required)
   ```bash
   UPLOAD_RESP=$(jq -n \
     --arg name "Prod Smoke $(date +%s)" \
     --arg country "$PROD_DEMO_COUNTRY" \
     --argjson size "$FILE_SIZE" \
     '{document_name:$name, source_type:"pdf", country_code:$country, language:"en",
       file_size_bytes:$size, tags:["demo","prod_smoke"], metadata:{scenario:"prod_manual"}}' | \
     curl -sS -X POST "$INGEST_BASE_URL/v1/documents/upload" \
       -H 'Content-Type: application/json' \
       -H "Authorization: Bearer $TOKEN" \
       ${INGEST_UPLOAD_API_KEY:+-H "x-api-key: $INGEST_UPLOAD_API_KEY"} \
       -d @-)
   echo "$UPLOAD_RESP" | jq .
   DOC_ID=$(echo "$UPLOAD_RESP" | jq -r '.document_id')
   UPLOAD_URL=$(echo "$UPLOAD_RESP" | jq -r '.upload.url')
   UPLOAD_FIELDS=$(echo "$UPLOAD_RESP" | jq -c '.upload.fields')
   ```
4. **POST the binary to ingestion service form endpoint**  
   (The FastAPI service returns an HMAC-signed form; upload directly to its `/v1/documents/upload/complete` URL with your bearer token. No S3 POST/fields juggling needed.)
   ```bash
   FORM_ARGS=()
   while IFS=$'\t' read -r key val; do FORM_ARGS+=(-F "$key=$val"); done \
     < <(echo "$UPLOAD_FIELDS" | jq -r 'to_entries[] | [.key, (.value|tostring)] | @tsv')
   FORM_ARGS+=(-F "file=@${FILE}")
   curl -sSf -X POST "$UPLOAD_URL" -H "Authorization: Bearer $TOKEN" "${FORM_ARGS[@]}"
   ```
5. **Poll Agent API until active (or failed)**
   ```bash
   until curl -sS "$AGENT_BASE_URL/v1/documents?page=1&page_size=50&content_hash=$FILE_HASH" \
     -H "Authorization: Bearer $TOKEN" \
     | tee /tmp/doc_status.json \
     | jq -e --arg doc "$DOC_ID" '.documents[] | select(.document_id==$doc) | select(.status=="active")'; do
       echo "waiting for ingestion..."; sleep 5;
   done
   ```
   If the document shows `status: "failed"`, check `metadata.ingestion_failure` for the convert error and avoid attaching.
6. **Create conversation + attach**
   ```bash
   CONV_ID=$(curl -sS -X POST "$AGENT_BASE_URL/v1/conversations" \
     -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"country_code":"'"$PROD_DEMO_COUNTRY"'","namespace":"prod-demo"}' \
     | jq -r '.conversation.conversation_id')

   curl -sS -X POST "$AGENT_BASE_URL/v1/conversations/$CONV_ID/attachments" \
     -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"document_id":"'"$DOC_ID"'","auto_attach_base_docs":false}' \
     | jq .
   ```
7. **Stream chat (numerical SSE)**
   ```bash
   ADV_PROMPT="Using the uploaded PDFs and KPI dashboard, flag any zone over the 80-point trigger and summarize arrears guardrails."
   curl -N \
     -H "Authorization: Bearer $TOKEN" \
     -H 'Accept: text/event-stream' \
     -H 'Content-Type: application/json' \
     -d '{"thread_id":"'"$CONV_ID"'","message":{"type":"user","content":"'"$ADV_PROMPT"'"},"constraints":{"country_code":"'"$PROD_DEMO_COUNTRY"'","auto_attach_base_docs":false}}' \
     "$AGENT_BASE_URL/v1/chat" | tee /tmp/sse_full_flow.log
   ```
   Confirm `requires_sql:true` and the numerical nodes appear in the SSE stream.

## 6) Automated smoke (multi-PDF)
Run the helper in AWS mode to upload **all three** PDFs (`doc_policy.pdf`, `doc_ledger.pdf`, `doc_kpi.pdf`) via the FastAPI ingestion service, poll until `active`, attach, and fire three prompts. Each upload is copied to `/tmp/prod_smoke_upload_XXXX.pdf` to avoid dedupe.
```bash
ENV_FILE=.env.prod bash scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_$(date +%s).log
```
- Output: updates `prod_sample_run.json` with answers + `requires_sql` fields; smoke log captured via `tee`.
- Override a single upload: `SMOKE_UPLOAD_FILE=/tmp/custom.pdf ENV_FILE=.env.prod bash scripts/prod_smoke_check.sh`.
- Expectations: KPI/ledger prompts show `requires_sql:true`, non-empty `sql_queries`, and `table_results` rows. Numeric prompts in prose (no markdown table) are auto-routed to SQL via the synthesized numeric-fact table, so `requires_sql` should still be `true` when digits/ledger/KPI language appears.

## 7) Troubleshooting & cleanup
- `DOCUMENT_NOT_READY` on attach → keep polling `/v1/documents` until `status=active`.
- `status=failed` with `ingestion_failure` → conversion error is fatal (fail-on-parse); do not re-attach until a new upload succeeds.
- Step Functions visibility:
  ```bash
  AWS_DEFAULT_REGION=${AWS_REGION:-us-east-1} aws stepfunctions list-executions --state-machine-arn <state_machine_arn>
  AWS_DEFAULT_REGION=${AWS_REGION:-us-east-1} aws stepfunctions describe-execution --execution-arn <arn>
  ```
- S3 dedupe: each run must upload a unique binary (copy with `$(date +%s)` as above) to avoid the ingestion API short-circuiting with `status: "DEDUPED"`.
- Cleanup:
  ```bash
  terraform -chdir=ArchaaS workspace select prod && terraform -chdir=ArchaaS destroy -var-file=terraform.v2.tfvars
  COMPOSE_PROFILES=reduced,ops docker compose down -v --remove-orphans
  ```
  (LocalStack destroy is the same with workspace `localstack` and `configs/localstack.tfvars` if needed later.)
  - Data reset (AWS) before final deploy:
    ```bash
    # housing DB – remove smoke docs/chats and cascades
    set -a && source .env.prod && set +a
    PGPASSWORD=$POSTGRES_PASSWORD psql -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER -d $POSTGRES_DB \
      -c "begin; delete from conversations; delete from documents; commit;"

    # auth_db – drop stale refresh tokens
    PGPASSWORD=$POSTGRES_PASSWORD psql -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER -d $AUTH_DB \
      -c "begin; delete from refresh_tokens; commit;"
    ```
  - Quality gates (services/agent-api):
    ```bash
    uv run ruff format .
    uv run ruff check --fix .
    uv run ty check .
    uv run pytest -n auto
    ```
