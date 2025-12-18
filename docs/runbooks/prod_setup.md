# Production Runbook (AWS/EC2)

Deploy the ingestion-first stack (agent-api, ingestion-service, auth-service, user-service, Postgres) to EC2 and run the synchronous ingestion smoke. Legacy Lambda/Step Functions, Valkey cache, telemetry, and reduced-scope modes are deprecated.

## Live endpoints
- `AGENT_BASE_URL=http://52.207.140.87:8000`
- `AUTH_BASE_URL=http://52.207.140.87:5001`
- `INGEST_BASE_URL=http://52.207.140.87:8085`
- Auth demo creds: `PROD_DEMO_EMAIL` / `PROD_DEMO_PASSWORD` (from `.env.prod`)

## Prereqs
- Docker + Compose, Terraform 1.7+, AWS CLI, `jq`, `curl`.
- Env selection is required:  
  ```bash
  env_file=$(scripts/use_env.sh prod)
  set -a && source "$env_file" && set +a
  ```
- SSH key from Terraform outputs (defaults to `ArchaaS/dist/...pem`) for deploy/patched restarts.

## Deploy
Use the unified deploy script (cache-free stack only):
```bash
# terraform apply + compose rollout (DB preserved unless --destroy-first is passed)
ENV_FILE="$env_file" ./scripts/deploy_stack.sh --mode full-redeploy

# or services-only when infra is already up
ENV_FILE="$env_file" ./scripts/deploy_stack.sh --mode services-only
```
Options: `--destroy-first` (confirmation required), `--no-sync`, `--no-build`, `--host`, `--ssh-key`, `--patch-file` (hot-patch path).

### DB + migrations
- Postgres runs from `pgvector/pgvector:pg16` with `scripts/init-databases.sh` creating `housing` + `auth_db`.
- A one-shot `init-migrations` service (built from `docker/init-migrations/Dockerfile`) waits for Postgres and runs `shared_data_layer.manage migrate --revision head` before Agent API/ingestion start (`depends_on: condition: service_completed_successfully`).
- For a clean slate, drop the compose volume before redeploy:  
  `sudo docker compose --env-file .env.prod -f docker-compose.ec2.yml down --remove-orphans --volumes && sudo docker volume rm vizonomy-prod_repo_postgres_data repo_postgres_data || true`

### One-shot deploy + smoke
Deploy the ingestion-first stack (services-only by default) and immediately run the prod smoke with the FSAP PDF:
```bash
env_file=$(scripts/use_env.sh prod)
ENV_FILE="$env_file" ./scripts/prod_deploy_and_smoke.sh \
  --ssh-key ArchaaS/dist/vizonomy-v2-ec2-dev2.pem \
  --log-file /tmp/prod_deploy_and_smoke_$(date +%s).log
```
Key flags: `--deploy-mode services-only|full-redeploy|skip`, `--no-build`, `--no-sync`, `--host`, `--smoke-file` (defaults to `services/agent-api/evals/data/MEX_2016_Mexico Financial Sector Assessment Program Housing Finance.pdf`), `--output-file` (defaults to `prod_sample_run.json`).

### Deploying new code changes (services-only)
Use this for routine updates when infra is already up:
```bash
env_file=$(scripts/use_env.sh prod)
ENV_FILE="$env_file" ./scripts/deploy_stack.sh \
  --mode services-only \
  --host 52.207.140.87 \
  --ssh-key ArchaaS/dist/vizonomy-v2-ec2-dev2.pem
```
What it does: syncs the repo + env to `/opt/housing-microservices` on the host, stops any port conflicts (5432/5001/5002/8000/8085), rebuilds images, runs `docker compose -f docker-compose.ec2.yml up -d postgres init-migrations agent-api auth-service user-service ingestion-service`, and prints health-check commands. To force a clean DB, add the volume-drop command from the section above before rerunning.

## Smoke (automated)
Runs ingestion → activation → attachment → chat over live endpoints using the FastAPI ingestion service.
```bash
ENV_FILE="$env_file" ./scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_$(date +%s).log
```
- Uploads stamped copies of the policy/ledger/KPI PDFs to avoid dedupe.
- Uses synchronous ingestion (MarkItDown → voyage-context-3 embeddings → pgvector → activate) and checks `status=active` before attaching.
- Produces `prod_sample_run.json` with answers/citations/SQL traces.

## Smoke (manual walkthrough)
1) **Auth**  
```bash
TOKEN=$(curl -sS -X POST "$AUTH_BASE_URL/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"login":"'"$PROD_DEMO_EMAIL"'","password":"'"$PROD_DEMO_PASSWORD"'"}' | jq -r '.access_token')
```
2) **Upload via ingestion service (text-only, synchronous)**  
```bash
FILE=/tmp/prod_manual_$(date +%s).txt; echo "Prod manual smoke $(date -Iseconds)" > "$FILE"
SIZE=$(stat -c%s "$FILE")
REQ=$(jq -n --arg name "Prod Manual $(date +%s)" --arg country "$PROD_DEMO_COUNTRY" --argjson size "$SIZE" \
  '{document_name:$name, source_type:"txt", country_code:$country, language:"en", file_size_bytes:$size, tags:["prod","manual"], metadata:{scenario:"prod_manual"}}')
RESP=$(curl -sS -X POST "$INGEST_BASE_URL/v1/documents/upload" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d "$REQ")
UPLOAD_URL=$(echo "$RESP" | jq -r '.upload.url'); FIELDS=$(echo "$RESP" | jq -c '.upload.fields'); DOC_ID=$(echo "$RESP" | jq -r '.document_id')
FORM=(); while IFS=$'\t' read -r k v; do FORM+=(-F "$k=$v"); done < <(echo "$FIELDS" | jq -r 'to_entries[] | [.key, (.value|tostring)] | @tsv'); FORM+=(-F "file=@$FILE")
curl -sSf -X POST "$UPLOAD_URL" -H "Authorization: Bearer $TOKEN" "${FORM[@]}" >/dev/null
```
3) **Poll until active**  
```bash
until curl -sS "$AGENT_BASE_URL/v1/documents?page=1&page_size=50&content_hash=$(sha256sum "$FILE" | awk '{print $1}')" \
  -H "Authorization: Bearer $TOKEN" | jq -e --arg doc "$DOC_ID" '.documents[] | select(.document_id==$doc) | select(.status=="active")'; do
  sleep 5
done
```
4) **Conversation, attach, chat**  
```bash
CONV=$(curl -sS -X POST "$AGENT_BASE_URL/v1/conversations" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"country_code":"'"$PROD_DEMO_COUNTRY"'","namespace":"prod-manual"}' | jq -r '.conversation.conversation_id')
curl -sS -X POST "$AGENT_BASE_URL/v1/conversations/$CONV/attachments" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"document_id":"'"$DOC_ID"'","auto_attach_base_docs":false}' >/dev/null
curl -sS -X POST "$AGENT_BASE_URL/v1/chat" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"thread_id":"'"$CONV"'","message":{"type":"user","content":"Summarize the uploaded file."},"constraints":{"country_code":"'"$PROD_DEMO_COUNTRY"'","auto_attach_base_docs":false}}' | jq .
```

## Troubleshooting
- `DOCUMENT_NOT_READY`: wait for ingestion to activate; ingestion is synchronous but may take a few seconds for larger files.
- `status=failed`: check `metadata.ingestion_failure` and re-upload with a fresh binary (content-hash dedupe is enforced).
- Missing citations or empty answers: verify `OPENAI_API_KEY`/`VOYAGE_API_KEY` in the env file and rerun; no cache/rate-limit fallbacks exist.
- CORS: `.env.prod` sets `AGENT_API_CORS_ORIGINS=*` and `CORS_ORIGINS=*` for testing; tighten and redeploy if needed.

## Cleanup
- Redeploy with `--destroy-first` only when you intend to tear down/recreate infra (DB data is otherwise preserved).
- Remove local containers/volumes after smokes: `COMPOSE_PROFILES=reduced,ops docker compose down -v --remove-orphans` (or the equivalent for your profile).
