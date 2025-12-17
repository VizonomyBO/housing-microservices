# Quick Start Guide

Bring up the simplified text-only stack (agent-api, ingestion-service, auth-service, user-service, Postgres, LocalStack) and run a smoke in a few commands.

## 1) Prerequisites
- Docker Desktop / Engine 25.x with Compose V2.
- Bash-compatible shell, `curl`, `jq`.
- [uv](https://github.com/astral-sh/uv) if you want to run lint/tests locally.

## 2) Pick an environment
```bash
env_file=$(scripts/use_env.sh local|dev|prod)
set -a && source "$env_file" && set +a
```
- `.env.local` — LocalStack-first dev.
- `.env.dev` — local services pointed at remote data plane via `docker-compose.ec2.yml`.
- `.env.prod` — AWS/EC2 endpoints for deploy/smoke.

## 3) Start local stack (LocalStack required)
```bash
docker compose --env-file "$env_file" up -d --build
./test-api.sh
```
Health probes:
```bash
curl -fsS http://localhost:${AUTH_SERVICE_PORT:-5001}/health
curl -fsS http://localhost:${USER_SERVICE_PORT:-5002}/v1/health
curl -fsS http://localhost:${INGESTION_SERVICE_PORT:-8085}/health
curl -fsS http://localhost:${AGENT_API_PORT:-8000}/health
```

## 4) Hybrid / remote data plane
Run local services against remote Postgres/S3/ingestion:
```bash
env_file=$(scripts/use_env.sh dev)
set -a && source "$env_file" && set +a
docker compose --env-file "$env_file" -f docker-compose.ec2.yml up -d --build agent-api auth-service user-service ingestion-service
```

## 5) Quick ingestion + chat smoke (manual)
```bash
TOKEN=$(curl -sS -X POST "$AUTH_BASE_URL/v1/auth/login" -H 'Content-Type: application/json' \
  -d '{"login":"'"${PROD_DEMO_EMAIL:-demo@example.com}"'","password":"'"${PROD_DEMO_PASSWORD:-password}"'"}' | jq -r '.access_token')
FILE=/tmp/quickstart_$(date +%s).txt; echo "Hello from quickstart $(date -Iseconds)" > "$FILE"
RESP=$(curl -sS -X POST "$INGEST_BASE_URL/v1/documents/upload" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"document_name":"Quickstart Doc","source_type":"txt","country_code":"'"${PROD_DEMO_COUNTRY:-USA}"'","file_size_bytes":'$(stat -c%s "$FILE")'}')
UPLOAD_URL=$(echo "$RESP" | jq -r '.upload.url'); FIELDS=$(echo "$RESP" | jq -c '.upload.fields')
while IFS=$'\t' read -r k v; do FORM+=(-F "$k=$v"); done < <(echo "$FIELDS" | jq -r 'to_entries[] | [.key, (.value|tostring)] | @tsv'); FORM+=(-F "file=@$FILE")
curl -sSf -X POST "$UPLOAD_URL" -H "Authorization: Bearer $TOKEN" "${FORM[@]}" >/dev/null
DOC_ID=$(echo "$RESP" | jq -r '.document_id')
CONV_ID=$(curl -sS -X POST "$AGENT_BASE_URL/v1/conversations" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"country_code":"'"${PROD_DEMO_COUNTRY:-USA}"'","namespace":"quickstart"}' | jq -r '.conversation.conversation_id')
curl -sS -X POST "$AGENT_BASE_URL/v1/conversations/$CONV_ID/attachments" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"document_id":"'"$DOC_ID"'","auto_attach_base_docs":false}' >/dev/null
curl -sS -X POST "$AGENT_BASE_URL/v1/chat" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"thread_id":"'"$CONV_ID"'","message":{"type":"user","content":"Summarize the uploaded note."},"constraints":{"country_code":"'"${PROD_DEMO_COUNTRY:-USA}"'"}}' | jq .
```

## 6) Tear down
```bash
docker compose --env-file "$env_file" down              # stop containers, keep volumes
docker compose --env-file "$env_file" down -v           # delete Postgres + LocalStack data
```

## 7) Troubleshooting
- `OPENAI_API_KEY` and `VOYAGE_API_KEY` must be set before starting agent-api.
- LocalStack health: `curl -fsS http://localhost:${LOCALSTACK_EDGE_PORT:-4566}/_localstack/health`.
- Rerun migrations if needed: `docker compose --env-file "$env_file" run --rm db-init`.
- Graph/Step Functions/cache references in older docs are deprecated; use the ingestion-first flow above.
