#!/usr/bin/env bash
# Local end-to-end smoke: user -> login -> profile -> ingest eval docs -> poll -> attach -> chat.
set -euo pipefail

log() { echo "[local_smoke] $*" >&2; }
require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "Missing required command: $1"
    exit 1
  fi
}

require_cmd curl
require_cmd jq
require_cmd python3

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
env_file=${ENV_FILE:-"$("$ROOT_DIR"/scripts/use_env.sh local)"}
if [[ -f "$env_file" ]]; then
  log "Loading env from $env_file"
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
fi

AGENT_BASE_URL=${AGENT_BASE_URL:-http://localhost:${AGENT_API_PORT:-8000}}
AUTH_BASE_URL=${AUTH_BASE_URL:-http://localhost:${AUTH_SERVICE_PORT:-5001}}
USER_BASE_URL=${USER_BASE_URL:-http://localhost:${USER_SERVICE_PORT:-5002}}
INGEST_BASE_URL=${INGEST_BASE_URL:-http://localhost:${INGESTION_SERVICE_PORT:-8085}}
SMOKE_COUNTRY_CODE=${SMOKE_COUNTRY_CODE:-MEX}
SMOKE_LANGUAGE=${SMOKE_LANGUAGE:-en}
SMOKE_OUTPUT=${SMOKE_OUTPUT:-"$ROOT_DIR/local_smoke_report.json"}
SMOKE_UPLOAD_DIR=${SMOKE_UPLOAD_DIR:-"$ROOT_DIR/services/agent-api/evals/data"}
SMOKE_MAX_POLL_ATTEMPTS=${SMOKE_MAX_POLL_ATTEMPTS:-30}
SMOKE_POLL_INTERVAL_SEC=${SMOKE_POLL_INTERVAL_SEC:-4}
RUN_ID=$(date +%s)

for required in OPENAI_API_KEY VOYAGE_API_KEY JWT_SECRET_KEY; do
  if [[ -z "${!required:-}" ]]; then
    log "Missing required env var: $required"
    exit 1
  fi
done

health_check() {
  local name="$1" url="$2"
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" "$url" || true)
  if [[ "$status" != "200" ]]; then
    log "Health check failed for $name ($url) status=$status"
    exit 1
  fi
  log "$name healthy"
}

stat_size() {
  python3 - <<'PY' "$1"
import os, sys
path = sys.argv[1]
print(os.path.getsize(path))
PY
}

mime_type() {
  python3 - <<'PY' "$1"
import mimetypes, sys
mime, _ = mimetypes.guess_type(sys.argv[1])
print(mime or "application/octet-stream")
PY
}

ensure_files() {
  if [[ ! -d "$SMOKE_UPLOAD_DIR" ]]; then
    log "Upload dir not found: $SMOKE_UPLOAD_DIR"
    exit 1
  fi
  mapfile -d '' FILES < <(find "$SMOKE_UPLOAD_DIR" -maxdepth 1 -type f -print0)
  if [[ ${#FILES[@]} -eq 0 ]]; then
    log "No files found in $SMOKE_UPLOAD_DIR"
    exit 1
  fi
}

health_check "auth-service" "${AUTH_BASE_URL%/}/health"
health_check "user-service" "${USER_BASE_URL%/}/v1/health"
health_check "ingestion-service" "${INGEST_BASE_URL%/}/health"
health_check "agent-api" "${AGENT_BASE_URL%/}/health"
ensure_files

TMP_DOCS=$(mktemp)
TMP_QAS=$(mktemp)
trap 'rm -f "$TMP_DOCS" "$TMP_QAS"' EXIT

USER_EMAIL="smoke_${RUN_ID}@example.com"
USER_PASSWORD="TestPass123!"
USER_USERNAME="smoke_${RUN_ID}"

register_user() {
  local payload
  payload=$(jq -n \
    --arg email "$USER_EMAIL" \
    --arg username "$USER_USERNAME" \
    --arg password "$USER_PASSWORD" \
    '{
      email:$email,
      username:$username,
      password:$password,
      first_name:"Smoke",
      last_name:"Tester",
      country_code:"USA",
      role:"public"
    }')
  local resp status body
  resp=$(curl -s -w "\n%{http_code}" -X POST "${AUTH_BASE_URL%/}/v1/auth/register" \
    -H 'Content-Type: application/json' \
    -d "$payload")
  status=$(echo "$resp" | tail -n1)
  body=$(echo "$resp" | head -n-1)
  if [[ "$status" != "200" && "$status" != "201" && "$status" != "409" ]]; then
    log "Registration failed status=$status body=$body"
    exit 1
  fi
  log "User registration status=$status"
}

login_user() {
  local payload
  payload=$(jq -n --arg login "$USER_EMAIL" --arg password "$USER_PASSWORD" '{login:$login,password:$password}')
  local resp status body
  resp=$(curl -s -w "\n%{http_code}" -X POST "${AUTH_BASE_URL%/}/v1/auth/login" \
    -H 'Content-Type: application/json' -d "$payload")
  status=$(echo "$resp" | tail -n1)
  body=$(echo "$resp" | head -n-1)
  if [[ "$status" != "200" ]]; then
    log "Login failed status=$status body=$body"
    exit 1
  fi
  ACCESS_TOKEN=$(echo "$body" | jq -r '.access_token // empty')
  if [[ -z "$ACCESS_TOKEN" ]]; then
    log "No access_token in login response"
    exit 1
  fi
  log "Login ok; token acquired"
}

fetch_profile() {
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" "${USER_BASE_URL%/}/v1/users/me" \
    -H "Authorization: Bearer $ACCESS_TOKEN")
  if [[ "$status" != "200" ]]; then
    log "Profile fetch failed status=$status"
    exit 1
  fi
  log "Profile retrieved"
}

request_upload() {
  local file="$1"
  local doc_name="$2"
  local source_type="$3"
  local size mime payload resp status body
  size=$(stat_size "$file")
  mime=$(mime_type "$file")
  payload=$(jq -n \
    --arg name "$doc_name" \
    --arg source "$source_type" \
    --arg country "$SMOKE_COUNTRY_CODE" \
    --arg lang "$SMOKE_LANGUAGE" \
    --argjson size "$size" \
    --arg relpath "${file#$ROOT_DIR/}" \
    '{
      document_name:$name,
      source_type:$source,
      country_code:$country,
      language:$lang,
      tags:["local-smoke","eval"],
      file_size_bytes:$size,
      access_scope:"user_private",
      metadata:{run_id:'"$RUN_ID"', source:$relpath}
    }')
  resp=$(curl -s -w "\n%{http_code}" -X POST "${INGEST_BASE_URL%/}/v1/documents/upload" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "$payload")
  status=$(echo "$resp" | tail -n1)
  body=$(echo "$resp" | head -n-1)
  if [[ "$status" != "200" && "$status" != "201" ]]; then
    log "Ingestion init failed for $file status=$status body=$body"
    exit 1
  fi
  local upload_url fields doc_id ingestion_id
  upload_url=$(echo "$body" | jq -r '.upload.url // empty')
  fields=$(echo "$body" | jq -c '.upload.fields // {}')
  doc_id=$(echo "$body" | jq -r '.document_id // empty')
  ingestion_id=$(echo "$body" | jq -r '.ingestion_id // empty')
  if [[ -z "$upload_url" || -z "$doc_id" ]]; then
    log "Missing upload fields for $file: $body"
    exit 1
  fi
  complete_upload "$file" "$mime" "$upload_url" "$fields" "$doc_id" "$ingestion_id"
}

complete_upload() {
  local file="$1" mime="$2" upload_url="$3" fields_json="$4" doc_id="$5" ingestion_id="$6"
  local -a form_args=()
  while IFS=$'\t' read -r key value; do
    form_args+=(-F "$key=$value")
  done < <(echo "$fields_json" | jq -r 'to_entries[] | [.key, .value] | @tsv')
  form_args+=(-F "file=@${file};type=${mime}")
  local resp status body
  resp=$(curl -s -w "\n%{http_code}" -X POST "$upload_url" "${form_args[@]}")
  status=$(echo "$resp" | tail -n1)
  body=$(echo "$resp" | head -n-1)
  if [[ "$status" != "200" ]]; then
    log "Upload completion failed for $file status=$status body=$body"
    exit 1
  fi
  local content_hash status_field
  content_hash=$(echo "$body" | jq -r '.content_hash // empty')
  status_field=$(echo "$body" | jq -r '.status // empty')
  if [[ "$status_field" != "active" ]]; then
    log "Document $doc_id not active after ingestion (status=$status_field)"
    exit 1
  fi
  poll_document "$doc_id" "$content_hash"
}

poll_document() {
  local doc_id="$1" content_hash="$2"
  local attempt=1 body status
  local query="page=1&page_size=10&content_hash=$content_hash"
  while (( attempt <= SMOKE_MAX_POLL_ATTEMPTS )); do
    resp=$(curl -s -w "\n%{http_code}" "${AGENT_BASE_URL%/}/v1/documents?${query}" \
      -H "Authorization: Bearer $ACCESS_TOKEN")
    status=$(echo "$resp" | tail -n1)
    body=$(echo "$resp" | head -n-1)
    if [[ "$status" == "200" ]]; then
      local match
      match=$(echo "$body" | jq -c --arg id "$doc_id" '.documents[] | select(.document_id == $id)')
      if [[ -n "$match" ]]; then
        local state stage name
        state=$(echo "$match" | jq -r '.status')
        stage=$(echo "$match" | jq -r '.ingestion_stage // ""')
        name=$(echo "$match" | jq -r '.canonical_name // ""')
        if [[ "$state" == "active" ]]; then
          jq -c <<<"$match" >>"$TMP_DOCS"
          log "Document $doc_id active (stage=${stage:-n/a}) name=${name:-n/a}"
          return
        fi
        log "Waiting for document $doc_id status=$state stage=$stage attempt=$attempt"
      else
        log "Document $doc_id not listed yet attempt=$attempt"
      fi
    else
      log "Poll failed status=$status body=$body"
    fi
    sleep "$SMOKE_POLL_INTERVAL_SEC"
    attempt=$((attempt + 1))
  done
  log "Document $doc_id did not reach active state"
  exit 1
}

create_conversation() {
  local payload resp status body
  payload=$(jq -n \
    --arg country "$SMOKE_COUNTRY_CODE" \
    --arg title "Local Smoke $RUN_ID" \
    '{
      country_code:$country,
      namespace:"local-smoke",
      title:$title,
      tags:["local-smoke","eval"]
    }')
  resp=$(curl -s -w "\n%{http_code}" -X POST "${AGENT_BASE_URL%/}/v1/conversations" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "$payload")
  status=$(echo "$resp" | tail -n1)
  body=$(echo "$resp" | head -n-1)
  if [[ "$status" != "201" ]]; then
    log "Conversation create failed status=$status body=$body"
    exit 1
  fi
  CONVERSATION_ID=$(echo "$body" | jq -r '.conversation.conversation_id // empty')
  if [[ -z "$CONVERSATION_ID" ]]; then
    log "Conversation id missing"
    exit 1
  fi
  log "Conversation $CONVERSATION_ID ready"
}

attach_documents() {
  local doc_ids_json
  doc_ids_json=$(jq -s '[.[].document_id]' "$TMP_DOCS")
  resp=$(curl -s -w "\n%{http_code}" -X POST "${AGENT_BASE_URL%/}/v1/conversations/$CONVERSATION_ID/attachments/bulk" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "$(jq -n --argjson ids "$doc_ids_json" '{document_ids:$ids, visibility:"visible", role:"primary"}')")
  status=$(echo "$resp" | tail -n1)
  body=$(echo "$resp" | head -n-1)
  if [[ "$status" != "200" ]]; then
    log "Bulk attach failed status=$status body=$body"
    exit 1
  fi
  local attached_count
  attached_count=$(echo "$body" | jq -r '.attached | length')
  log "Attached $attached_count documents to $CONVERSATION_ID"
}

ask_question() {
  local question="$1"
  local payload resp status body answer citations_count
  payload=$(jq -n \
    --arg thread "$CONVERSATION_ID" \
    --arg question "$question" \
    --arg country "$SMOKE_COUNTRY_CODE" \
    '{
      thread_id:$thread,
      message:{type:"user",content:$question},
      constraints:{country_code:$country,auto_attach_base_docs:false},
      response_mode:"blocking"
    }')
  resp=$(curl -s -w "\n%{http_code}" -X POST "${AGENT_BASE_URL%/}/v1/chat" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "$payload")
  status=$(echo "$resp" | tail -n1)
  body=$(echo "$resp" | head -n-1)
  if [[ "$status" != "200" ]]; then
    log "Chat failed status=$status body=$body"
    exit 1
  fi
  answer=$(echo "$body" | jq -r '.done.answer // .done.payload.answer // empty')
  citations_count=$(echo "$body" | jq -r '(.done.citations // .done.payload.citations // []) | length')
  if [[ -z "$answer" || ${#answer} -lt 20 || "$citations_count" -eq 0 ]]; then
    log "Answer invalid or missing citations: $answer"
    log "Raw response: $body"
    exit 1
  fi
  local citations_json
  citations_json=$(echo "$body" | jq -c '.done.citations // .done.payload.citations // []')
  jq -n -c --arg q "$question" --arg a "$answer" \
    --argjson citations "$citations_json" \
    --argjson raw "$body" \
    '{question:$q, answer:$a, citations:$citations, raw:$raw}' >>"$TMP_QAS"
  log "Answered: $question"
}

register_user
login_user
fetch_profile

for file in "${FILES[@]}"; do
  base=$(basename "$file")
  ext="${base##*.}"
  doc_name="${base%.*}"
  log "Uploading $base"
  request_upload "$file" "$doc_name" "${ext,,}"
done

create_conversation
attach_documents

QUESTIONS=(
  "Summarize the main housing finance vulnerabilities highlighted in the Mexico 2016 FSAP report and cite the evidence."
  "List two policy recommendations from the report to strengthen Mexico's mortgage market and mention why each matters."
  "What risks did the report note about housing-related funding sources, and how should they be mitigated?"
)

for q in "${QUESTIONS[@]}"; do
  ask_question "$q"
done

DOCS_JSON=$(jq -s '.' "$TMP_DOCS")
QAS_JSON=$(jq -s '.' "$TMP_QAS")

jq -n \
  --arg run_id "$RUN_ID" \
  --arg conversation_id "$CONVERSATION_ID" \
  --arg user_email "$USER_EMAIL" \
  --arg agent_url "$AGENT_BASE_URL" \
  --arg ingest_url "$INGEST_BASE_URL" \
  --argjson documents "$DOCS_JSON" \
  --argjson questions "$QAS_JSON" \
  '{
    run_id:$run_id,
    conversation_id:$conversation_id,
    user_email:$user_email,
    agent_base_url:$agent_url,
    ingest_base_url:$ingest_url,
    documents:$documents,
    questions:$questions
  }' >"$SMOKE_OUTPUT"

log "Smoke complete; report written to $SMOKE_OUTPUT"
