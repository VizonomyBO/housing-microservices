# Production (Reduced Scope) Runbook

End-to-end checklist for bringing up the reduced stack, deploying the full ingestion pipeline (API Gateway → S3 → Step Functions → Postgres), and verifying the numerical SSE flow through `/v1/chat`. These steps apply to both LocalStack and real AWS; only the terraform workspace, compose overrides, and credentials change.

## 1. Prerequisites
- Ubuntu/AlmaLinux host or EC2 instance with Docker Engine v25+, Compose V2, `curl`, `jq`, and Terraform 1.7+.
- Python 3.11+ with `uv` if you need to run FastAPI locally.
- LocalStack Pro license for Step Functions **or** an AWS account with access to S3/Lambda/Step Functions/API Gateway.
- Populated `.env.prod` (LocalStack) and/or `.env.prod.aws` (real AWS).

## 2. Environment Files & Key Variables
1. Copy secrets templates and edit every placeholder (`CHANGE_ME`):
   ```bash
   cp env.example .env.prod
   cp env.example .env.prod.aws
   ```
2. Always export the environment before running compose, terraform, or helper scripts:
   ```bash
   set -a && source .env.prod && set +a          # LocalStack
   # or
   set -a && source .env.prod.aws && set +a      # AWS
   ```
3. New ingestion-specific variables:
   - `INGEST_BASE_URL`: API Gateway invoke URL (e.g., `https://abc123.execute-api.us-east-1.amazonaws.com/prod` or `http://localhost.localstack.cloud:4566/restapis/.../prod/_user_request_`).
   - `INGEST_UPLOAD_API_KEY` (optional): attach with `-H "x-api-key: $INGEST_UPLOAD_API_KEY"` if your gateway enforces API keys.
   - `USE_LOCALSTACK`: keep `1` for LocalStack, set `0` when pointing at AWS.

## 3. Start the Core Compose Stack
```bash
set -a && source .env.prod && set +a
COMPOSE_PROFILES=reduced,ops docker compose up -d --build
```
For AWS, source `.env.prod.aws` and include the override:
```bash
COMPOSE_PROFILES=reduced,ops \
  docker compose \
    -f docker-compose.yml \
    -f docker-compose.prod.override.yml \
    up -d --build
```
Health checks:
```bash
curl $AGENT_BASE_URL/health
curl $AGENT_BASE_URL/v1/health
curl $AUTH_BASE_URL/v1/health
```

## 4. Deploy the ArchaaS Ingestion Stack
All terraform commands run from `ArchaaS/`.

### 4.1 LocalStack deployment
```bash
cd ArchaaS
terraform init
terraform workspace select localstack || terraform workspace new localstack
terraform apply -var-file=configs/localstack.tfvars
```
Outputs include `ingest_api_endpoint`; export it:
```bash
export INGEST_BASE_URL=$(terraform output -raw ingest_api_endpoint)
```
LocalStack uses the bundled gateway at `localhost.localstack.cloud:4566`, so Terraform wires API Gateway, Lambdas, Step Functions, and S3 into the compose network automatically.

### 4.2 AWS deployment
```bash
cd ArchaaS
terraform init
terraform workspace select prod || terraform workspace new prod
terraform apply -var-file=configs/prod.tfvars
```
The apply step creates:
- API Gateway + custom domain (if configured).
- Lambdas for document upload, preflight, conversion, chunking, embedding, indexing, finalization.
- Step Functions state machine (`document_ingestion_workflow`).
- S3 buckets for raw + processed artifacts.
Capture the `ingest_api_endpoint` output and export it as `INGEST_BASE_URL`. If API keys are enabled, set `INGEST_UPLOAD_API_KEY` to the value terraform produced.

## 5. Full cURL Workflow (Register → Upload → Poll → Attach → Ask)
The commands below work for both environments once `INGEST_BASE_URL`, `$AGENT_BASE_URL`, and auth credentials are exported.

### 5.1 Obtain a session token
```bash
TOKEN=$(curl -sS -X POST "$AUTH_BASE_URL/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"login\":\"$PROD_DEMO_EMAIL\",\"password\":\"$PROD_DEMO_PASSWORD\"}" \
  | jq -r '.access_token')
```

### 5.2 Request a presigned upload (API Gateway / Lambda)
```bash
FILE=services/agent-api/tests/data/reduced_e2e/doc_policy.pdf   # real PDF, avoids broken test PDFs
FILE_SIZE=$(stat -c%s "$FILE")

UPLOAD_REQ=$(jq -n \
  --arg name "Prod Smoke $(date +%s)" \
  --arg country "$PROD_DEMO_COUNTRY" \
  '{
     document_name:$name,
     source_type:"pdf",
     country_code:$country,
     language:"en",
     file_size_bytes:$ENV.FILE_SIZE | tonumber,
     tags:["demo","ingestion"],
     metadata:{scenario:"full_ingestion"}
   }')

UPLOAD_RESP=$(echo "$UPLOAD_REQ" | curl -sS -X POST "$INGEST_BASE_URL/v1/documents/upload" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  ${INGEST_UPLOAD_API_KEY:+-H "x-api-key: $INGEST_UPLOAD_API_KEY"} \
  -d @-)
echo "$UPLOAD_RESP" | jq .
DOC_ID=$(echo "$UPLOAD_RESP" | jq -r '.document_id')
UPLOAD_URL=$(echo "$UPLOAD_RESP" | jq -r '.upload.url')
UPLOAD_FIELDS=$(echo "$UPLOAD_RESP" | jq -r '.upload.fields')
```

### 5.3 Upload the binary to S3
```bash
CONTENT_TYPE=$(echo "$UPLOAD_FIELDS" | jq -r '."Content-Type" // "application/pdf"')
FORM_ARGS=()
while IFS=$'\t' read -r key val; do
  FORM_ARGS+=(-F "$key=$val")
done < <(echo "$UPLOAD_FIELDS" | jq -r 'to_entries[] | [.key, (.value|tostring)] | @tsv')
FORM_ARGS+=(-F "file=@${FILE};type=${CONTENT_TYPE}")

curl -sSf -X POST "$UPLOAD_URL" "${FORM_ARGS[@]}"
```
On LocalStack, the upload triggers the S3 event immediately. In AWS the Lambda fires as soon as the object lands in the raw bucket.

**Note:** Use the real PDF at `services/agent-api/tests/data/reduced_e2e/doc_policy.pdf` (added to avoid corrupt test PDFs). If you swap files, ensure the `file_size_bytes` and SHA256 hash reflect the exact upload.

### 5.4 Poll Agent API for ingest status
```bash
FILE_HASH=$(sha256sum "$FILE" | awk '{print $1}')
until curl -sS "$AGENT_BASE_URL/v1/documents?page=1&page_size=50&content_hash=$FILE_HASH" \
  -H "Authorization: Bearer $TOKEN" \
  | tee /tmp/doc_status.json \
  | jq -e --arg doc "$DOC_ID" '.documents[] | select(.document_id == $doc) | select(.status=="active")'; do
    echo "waiting for ingestion..."; sleep 5;
done
```
The list endpoint exposes the document’s status/ingestion stage even before attachments are allowed. While ingestion runs, attempts to attach the document respond with `DOCUMENT_NOT_READY` (HTTP 409). The poll exits once the matching row reports `status=active` and `ingestion_stage=activate`.

### 5.5 Create a conversation and attach the document
```bash
CONV_ID=$(curl -sS -X POST "$AGENT_BASE_URL/v1/conversations" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"country_code":"'"$PROD_DEMO_COUNTRY"'","namespace":"prod-demo"}' \
  | jq -r '.conversation.conversation_id')

curl -sS -X POST "$AGENT_BASE_URL/v1/conversations/$CONV_ID/attachments" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"document_id":"'"$DOC_ID"'","auto_attach_base_docs":false}'
```

### 5.6 Stream the numerical SSE flow
```bash
ADV_PROMPT="Using the uploaded PDF and KPI dashboard, identify which zones exceed the 80-point trigger and outline a two-step arrears relief plan with voucher guardrails. Cite KPI values."

curl -N \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Accept: text/event-stream' \
  -H 'Content-Type: application/json' \
  -d '{
        "thread_id":"'"$CONV_ID"'",
        "message":{"type":"user","content":"'"$ADV_PROMPT"'"},
        "constraints":{"country_code":"'"$PROD_DEMO_COUNTRY"'","auto_attach_base_docs":false}
      }' \
  "$AGENT_BASE_URL/v1/chat" | tee sse_full_flow.log
```
Verify the SSE transcript includes:
- `router` events with `requires_sql=true`.
- `numerical_text_to_sql`, `numerical_polars_executor`, and `numerical_result_validator`.
- Final payload citing `[SQL_RESULT]` with matching table rows.

### 5.7 Known-good AWS example (2025-12-05)
- Env: `.env.prod.aws` with `USE_LOCALSTACK=0`, `INGEST_BASE_URL=https://gs6w1i52n4.execute-api.us-east-1.amazonaws.com/dev2`, Postgres host `44.216.103.232`.
- Upload file: `services/agent-api/tests/data/reduced_e2e/doc_policy.pdf` copied to `/tmp/aws_smoke_step9/doc_policy_smoke_md_1764941879_fix.md` (unique tag appended).
- Commands: `SMOKE_UPLOAD_FILE=/tmp/aws_smoke_step9/doc_policy_smoke_md_1764941879_fix.md ./scripts/prod_smoke_check.sh`
- Result: Document `bae6eef5-7776-4a78-9333-dfb61d8ec65f` -> `active`; conversation `e079ab22-b664-5d41-9d34-320e1b3ff204`; chat answers and SQL evidence recorded in `prod_sample_run.json`; run log `/tmp/aws_smoke_step9/prod_smoke_check_1764941879.log`.

## 6. Smoke Tests
The helper script continues to validate seeded documents plus your freshly ingested artifacts:
```bash
./scripts/prod_smoke_check.sh
```
It logs into the demo account, uploads the configured `SMOKE_UPLOAD_FILE`, attaches required docs (skipping any still ingesting), fires three `/v1/chat` prompts, and writes `prod_sample_run.json`. Check that the KPI prompt shows `requires_sql=true`, contains SQL text, and includes `table_results`.  
When `INGEST_BASE_URL` is defined the script will request a presigned URL from the ingestion API; otherwise it streams the Markdown directly to `POST /v1/documents/upload` so the reduced-stack pipeline still exercises the real HTTP flow.

## 7. AWS vs LocalStack Differences
| Concern | LocalStack | AWS |
| --- | --- | --- |
| Compose | `docker compose up -d --build` | add `docker-compose.prod.override.yml` |
| Terraform workspace | `localstack` | `prod` |
| API Gateway URL | `localhost.localstack.cloud:4566/...` | `https://<id>.execute-api.<region>.amazonaws.com/<stage>` |
| Credentials | dummy locals (`localstack/localstack`) | real IAM access keys |
| SSE verification | identical | identical |
| Tear down | `terraform destroy -var-file=configs/localstack.tfvars` | `terraform destroy -var-file=configs/prod.tfvars` |

## 8. Troubleshooting
| Symptom | Remedy |
| --- | --- |
| `DOCUMENT_NOT_READY` when attaching | The document is still ingesting. Poll `GET /v1/documents?page=1&page_size=5&content_hash=<SHA256>` (use `sha256sum` on the upload file) and retry once the matching row reports `status=active`. |
| Step Function never starts | Confirm preflight Lambda logs in CloudWatch (or `docker compose logs preflight-validator` in LocalStack). Ensure S3 notification rules exist and the raw bucket matches `.env`. |
| `embedding_writer` failures about pgvector | Run Postgres migrations (compose `db-init`) so the `embedding` column and pgvector extension exist. |
| SSE lacks numerical nodes | Verify the uploaded document was attached, the conversation `country_code` matches, and the prompt references KPIs/thresholds. |
| Terraform destroy hangs | Make sure compose services that talk to LocalStack are stopped before running `terraform destroy` to avoid dangling resources. |

## 9. Cleanup
```bash
# Tear down terraform resources
cd ArchaaS
terraform workspace select localstack && terraform destroy -var-file=configs/localstack.tfvars
# or
terraform workspace select prod && terraform destroy -var-file=configs/prod.tfvars

# Stop containers
cd ..
COMPOSE_PROFILES=reduced,ops docker compose down -v --remove-orphans
```
Delete any uploaded PDFs from the raw bucket if you do not want them retained in S3.
