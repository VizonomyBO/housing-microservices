#!/usr/bin/env bash
# End-to-end smoke: login -> ingest -> attach -> chat (local or prod targets).
set -euo pipefail

log() { echo "[local_smoke] $*" >&2; }
require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "Missing required command: $1"
    exit 1
  fi
}

TARGET=${TARGET:-local}
ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ENV_FILE="${ENV_FILE:-}"
SMOKE_UPLOAD_FILE="${SMOKE_UPLOAD_FILE:-}"
SMOKE_OUTPUT=${SMOKE_OUTPUT:-"$ROOT_DIR/local_smoke_report.json"}
SMOKE_UPLOAD_DIR_DEFAULT="$ROOT_DIR/services/agent-api/evals/data"
SMOKE_UPLOAD_DIR=${SMOKE_UPLOAD_DIR:-"$SMOKE_UPLOAD_DIR_DEFAULT"}
SMOKE_MAX_POLL_ATTEMPTS=${SMOKE_MAX_POLL_ATTEMPTS:-30}
SMOKE_POLL_INTERVAL_SEC=${SMOKE_POLL_INTERVAL_SEC:-4}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --smoke-output) SMOKE_OUTPUT="$2"; shift 2 ;;
    --upload-file) SMOKE_UPLOAD_FILE="$2"; shift 2 ;;
    *) log "Unknown argument: $1"; exit 1 ;;
  esac
done

if [[ -z "$ENV_FILE" ]]; then
  ENV_FILE="$("$ROOT_DIR"/scripts/use_env.sh "$TARGET")"
fi

if [[ -f "$ENV_FILE" ]]; then
  log "Loading env from $ENV_FILE"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

require_cmd curl
require_cmd jq
require_cmd python3

AGENT_BASE_URL=${AGENT_BASE_URL:-http://localhost:${AGENT_API_PORT:-8000}}
AUTH_BASE_URL=${AUTH_BASE_URL:-http://localhost:${AUTH_SERVICE_PORT:-5001}}
USER_BASE_URL=${USER_BASE_URL:-http://localhost:${USER_SERVICE_PORT:-5002}}
INGEST_BASE_URL=${INGEST_BASE_URL:-http://localhost:${INGESTION_SERVICE_PORT:-8085}}
SMOKE_COUNTRY_CODE=${SMOKE_COUNTRY_CODE:-MEX}
SMOKE_LANGUAGE=${SMOKE_LANGUAGE:-en}
SMOKE_TAG=${SMOKE_TAG:-$( [[ "$TARGET" == "prod" ]] && echo "prod-smoke" || echo "local-smoke" )}
SMOKE_NAMESPACE=${SMOKE_NAMESPACE:-$SMOKE_TAG}
SMOKE_ACCESS_SCOPE=${SMOKE_ACCESS_SCOPE:-user_private}
STAMP_UPLOAD=${STAMP_UPLOAD:-$( [[ "$TARGET" == "prod" ]] && echo 1 || echo 0 )}
RUN_ID=$(date +%s)
SMOKE_SKIP_REGISTRATION=${SMOKE_SKIP_REGISTRATION:-$( [[ "$TARGET" == "prod" ]] && echo 1 || echo 0 )}
if [[ "$SMOKE_SKIP_REGISTRATION" -eq 1 ]]; then
  SMOKE_USER_EMAIL=${SMOKE_USER_EMAIL:-${PROD_DEMO_EMAIL:-}}
  SMOKE_USER_PASSWORD=${SMOKE_USER_PASSWORD:-${PROD_DEMO_PASSWORD:-}}
  SMOKE_USER_USERNAME=${SMOKE_USER_USERNAME:-${PROD_DEMO_USERNAME:-smoke_demo}}
  if [[ -z "$SMOKE_USER_EMAIL" || -z "$SMOKE_USER_PASSWORD" ]]; then
    log "SMOKE_SKIP_REGISTRATION=1 requires SMOKE_USER_EMAIL/SMOKE_USER_PASSWORD (or PROD_DEMO_EMAIL/PROD_DEMO_PASSWORD)"
    exit 1
  fi
else
  SMOKE_USER_EMAIL=${SMOKE_USER_EMAIL:-"smoke_${RUN_ID}@example.com"}
  SMOKE_USER_PASSWORD=${SMOKE_USER_PASSWORD:-"TestPass123!"}
  SMOKE_USER_USERNAME=${SMOKE_USER_USERNAME:-"smoke_${RUN_ID}"}
fi

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
  if [[ -n "$SMOKE_UPLOAD_FILE" ]]; then
    if [[ ! -f "$SMOKE_UPLOAD_FILE" ]]; then
      log "Upload file not found: $SMOKE_UPLOAD_FILE"
      exit 1
    fi
    FILES=("$SMOKE_UPLOAD_FILE")
    return
  fi
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
QUESTION_TMP_FILES=()
UPLOAD_TMP_FILES=()
trap 'rm -f "$TMP_DOCS" "$TMP_QAS" "${QUESTION_TMP_FILES[@]:-}" "${UPLOAD_TMP_FILES[@]:-}"' EXIT

register_user() {
  if [[ "$SMOKE_SKIP_REGISTRATION" -eq 1 ]]; then
    log "Skipping registration; using existing user $SMOKE_USER_EMAIL"
    return
  fi
  local payload
  payload=$(jq -n \
    --arg email "$SMOKE_USER_EMAIL" \
    --arg username "$SMOKE_USER_USERNAME" \
    --arg password "$SMOKE_USER_PASSWORD" \
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
  payload=$(jq -n --arg login "$SMOKE_USER_EMAIL" --arg password "$SMOKE_USER_PASSWORD" '{login:$login,password:$password}')
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
    --arg tag "$SMOKE_TAG" \
    --argjson size "$size" \
    --arg relpath "${file#$ROOT_DIR/}" \
    --arg run_id "$RUN_ID" \
    --arg scope "$SMOKE_ACCESS_SCOPE" \
    '{
      document_name:$name,
      source_type:$source,
      country_code:$country,
      language:$lang,
      tags:[$tag,"eval"],
      file_size_bytes:$size,
      access_scope:$scope,
      metadata:{run_id:$run_id, source:$relpath}
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
    --arg title "Smoke $TARGET $RUN_ID" \
    --arg namespace "$SMOKE_NAMESPACE" \
    --arg tag "$SMOKE_TAG" \
    '{
      country_code:$country,
      namespace:$namespace,
      title:$title,
      tags:[$tag, "eval"]
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
  local expected_tool="${2:-}"
  local output_file="$3"
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
  tool_calls=$(echo "$body" | jq -c '.done.tool_calls // .done.payload.tool_calls // []')
  if [[ -z "$answer" || ${#answer} -lt 20 || "$citations_count" -eq 0 ]]; then
    log "Answer invalid or missing citations: $answer"
    log "Raw response: $body"
    exit 1
  fi
  if [[ -n "$expected_tool" ]]; then
    if ! echo "$tool_calls" | jq -e --arg tool "$expected_tool" 'map(select(.name == $tool)) | length > 0' >/dev/null; then
      log "Expected tool $expected_tool was not invoked; tool_calls=$tool_calls"
      exit 1
    fi
  fi
  local citations_json
  citations_json=$(echo "$body" | jq -c '.done.citations // .done.payload.citations // []')
  jq -n -c --arg q "$question" --arg a "$answer" \
    --argjson citations "$citations_json" \
    --argjson tool_calls "$tool_calls" \
    --argjson raw "$body" \
    '{question:$q, answer:$a, citations:$citations, tool_calls:$tool_calls, raw:$raw}' >"$output_file"
  log "Answered: $question"
}

register_user
login_user
fetch_profile

for file in "${FILES[@]}"; do
  base=$(basename "$file")
  ext="${base##*.}"
  doc_name="${base%.*}"
  upload_path="$file"
  if [[ "$STAMP_UPLOAD" -eq 1 ]]; then
    tmp_copy="$(mktemp /tmp/smoke_upload_XXXX.${ext})"
    cp "$file" "$tmp_copy"
    stamp="$(date -Iseconds)"
    if [[ "${ext,,}" == "pdf" ]]; then
      printf '\n%% smoke-run %s\n' "$stamp" >>"$tmp_copy"
    else
      printf '\n<!-- smoke-run %s -->\n' "$stamp" >>"$tmp_copy"
    fi
    upload_path="$tmp_copy"
    UPLOAD_TMP_FILES+=("$tmp_copy")
  fi
  log "Uploading $base"
  request_upload "$upload_path" "$doc_name" "${ext,,}"
done

create_conversation
attach_documents

QUESTIONS=(
  "Summarize the main housing finance vulnerabilities highlighted in the Mexico 2016 FSAP report and cite the evidence."
  "List two policy recommendations from the report to strengthen Mexico's mortgage market and mention why each matters."
  "What risks did the report note about housing-related funding sources, and how should they be mitigated?"
  "Using evidence from the Mexico 2016 FSAP housing finance report, use the pyodide_sandbox code execution tool to calculate the compound annual growth rate (CAGR) for a mortgage portfolio growing from 520 billion MXN in 2010 to 1.2 trillion MXN in 2015. Show the Python code you executed and cite the report sections you relied on."
)
QUESTION_EXPECTED_TOOL=("" "" "" "pyodide_sandbox")

pids=()
for idx in "${!QUESTIONS[@]}"; do
  tmp_out=$(mktemp)
  QUESTION_TMP_FILES+=("$tmp_out")
  (
    ask_question "${QUESTIONS[$idx]}" "${QUESTION_EXPECTED_TOOL[$idx]}" "$tmp_out"
  ) &
  pids+=("$!")
done

for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    log "One or more questions failed"
    exit 1
  fi
done

cat "${QUESTION_TMP_FILES[@]}" >>"$TMP_QAS"

jq -n \
  --arg run_id "$RUN_ID" \
  --arg target "$TARGET" \
  --arg conversation_id "$CONVERSATION_ID" \
  --arg user_email "$SMOKE_USER_EMAIL" \
  --arg agent_url "$AGENT_BASE_URL" \
  --arg ingest_url "$INGEST_BASE_URL" \
  --slurpfile documents "$TMP_DOCS" \
  --slurpfile questions "$TMP_QAS" \
  '{
    run_id:$run_id,
    target:$target,
    conversation_id:$conversation_id,
    user_email:$user_email,
    agent_base_url:$agent_url,
    ingest_base_url:$ingest_url,
    documents:$documents,
    questions:$questions
  }' >"$SMOKE_OUTPUT"

log "Smoke complete; report written to $SMOKE_OUTPUT"
