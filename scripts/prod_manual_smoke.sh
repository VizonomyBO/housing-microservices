#!/usr/bin/env bash
# Prod-friendly manual smoke: attach an existing document (or optionally upload one) and ask the standard FSAP questions.
set -euo pipefail

log() { echo "[prod_manual_smoke] $*" >&2; }
require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "Missing required command: $1"
    exit 1
  fi
}

TARGET=${TARGET:-prod}
ENV_FILE=${ENV_FILE:-}
DOC_ID=${DOC_ID:-}
UPLOAD_FILE=${UPLOAD_FILE:-}
SMOKE_OUTPUT=${SMOKE_OUTPUT:-"/tmp/prod_manual_smoke_$(date +%s).json"}
SMOKE_COUNTRY_CODE=${SMOKE_COUNTRY_CODE:-MEX}
SMOKE_TAG=${SMOKE_TAG:-${TARGET}-manual-smoke}
SMOKE_NAMESPACE=${SMOKE_NAMESPACE:-${SMOKE_TAG}}
STAMP_UPLOAD=${STAMP_UPLOAD:-$( [[ "$TARGET" == "prod" ]] && echo 1 || echo 0 )}
RUN_ID=$(date +%s)

usage() {
  cat <<'USAGE'
Usage: ./scripts/prod_manual_smoke.sh [--env-file PATH] [--doc-id UUID] [--upload-file PATH] [--smoke-output PATH]

Options:
  --env-file PATH     Env file to load (defaults to scripts/use_env.sh prod)
  --doc-id UUID       Existing document_id to attach (recommended for prod to skip ingestion time)
  --upload-file PATH  Upload and ingest this file first (takes time); doc-id is derived from upload
  --smoke-output PATH Where to write the JSON report (default: /tmp/prod_manual_smoke_<ts>.json)

Environment overrides:
  DOC_ID, UPLOAD_FILE, SMOKE_COUNTRY_CODE, SMOKE_TAG, SMOKE_NAMESPACE, STAMP_UPLOAD
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --doc-id) DOC_ID="$2"; shift 2 ;;
    --upload-file) UPLOAD_FILE="$2"; shift 2 ;;
    --smoke-output) SMOKE_OUTPUT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) log "Unknown argument: $1"; usage; exit 1 ;;
  esac
done

require_cmd curl
require_cmd jq
require_cmd python3

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ -z "$ENV_FILE" ]]; then
  ENV_FILE="$ROOT_DIR/scripts/use_env.sh $TARGET"
  ENV_FILE=$(bash -c "$ENV_FILE")
fi

if [[ -f "$ENV_FILE" ]]; then
  log "Loading env from $ENV_FILE"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

AGENT_BASE_URL=${AGENT_BASE_URL:-http://localhost:${AGENT_API_PORT:-8000}}
AUTH_BASE_URL=${AUTH_BASE_URL:-http://localhost:${AUTH_SERVICE_PORT:-5001}}
INGEST_BASE_URL=${INGEST_BASE_URL:-http://localhost:${INGESTION_SERVICE_PORT:-8085}}

for required in PROD_DEMO_EMAIL PROD_DEMO_PASSWORD; do
  if [[ -z "${!required:-}" ]]; then
    log "Missing required env var: $required"
    exit 1
  fi
done

stat_size() {
  python3 - <<'PY' "$1"
import os, sys
print(os.path.getsize(sys.argv[1]))
PY
}

mime_type() {
  python3 - <<'PY' "$1"
import mimetypes, sys
mime, _ = mimetypes.guess_type(sys.argv[1])
print(mime or "application/octet-stream")
PY
}

login_user() {
  local payload status body
  payload=$(jq -n --arg login "$PROD_DEMO_EMAIL" --arg password "$PROD_DEMO_PASSWORD" '{login:$login,password:$password}')
  resp=$(curl -s -w "\n%{http_code}" -X POST "${AUTH_BASE_URL%/}/v1/auth/login" -H 'Content-Type: application/json' -d "$payload")
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
  log "Login ok"
}

upload_and_wait() {
  local file="$1"; local ext="${file##*.}"; local doc_name
  doc_name=$(basename "${file%.*}")
  local size mime payload resp status body upload_url fields content_hash
  size=$(stat_size "$file")
  mime=$(mime_type "$file")
  payload=$(jq -n \
    --arg name "$doc_name" \
    --arg source "${ext,,}" \
    --arg country "$SMOKE_COUNTRY_CODE" \
    --arg lang "en" \
    --arg tag "$SMOKE_TAG" \
    --argjson size "$size" \
    --arg scope "user_private" \
    --arg run_id "$RUN_ID" \
    '{document_name:$name, source_type:$source, country_code:$country, language:$lang, tags:[$tag,"eval"], file_size_bytes:$size, access_scope:$scope, metadata:{run_id:$run_id}}'
  )
  resp=$(curl -s -w "\n%{http_code}" -X POST "${INGEST_BASE_URL%/}/v1/documents/upload" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "$payload")
  status=$(echo "$resp" | tail -n1)
  body=$(echo "$resp" | head -n-1)
  if [[ "$status" != "200" && "$status" != "201" ]]; then
    log "Upload init failed status=$status body=$body"
    exit 1
  fi
  upload_url=$(echo "$body" | jq -r '.upload.url')
  fields=$(echo "$body" | jq -c '.upload.fields')
  DOC_ID=$(echo "$body" | jq -r '.document_id')
  INGESTION_ID=$(echo "$body" | jq -r '.ingestion_id')
  if [[ -z "$upload_url" || -z "$DOC_ID" ]]; then
    log "Upload init missing fields"
    exit 1
  fi
  log "Completing upload for $DOC_ID"
  local -a form_args=()
  while IFS=$'\t' read -r key value; do
    form_args+=(-F "$key=$value")
  done < <(echo "$fields" | jq -r 'to_entries[] | [.key, .value] | @tsv')
  form_args+=(-F "file=@${file};type=${mime}")
  resp=$(curl -s -w "\n%{http_code}" -X POST "$upload_url" "${form_args[@]}")
  status=$(echo "$resp" | tail -n1)
  body=$(echo "$resp" | head -n-1)
  if [[ "$status" != "200" ]]; then
    log "Upload completion failed status=$status body=$body"
    exit 1
  fi
  content_hash=$(echo "$body" | jq -r '.content_hash // empty')
  log "Upload complete; polling for activation (hash=${content_hash:-n/a})"
  poll_document "$content_hash"
}

poll_document() {
  local content_hash="$1"; local attempt=1; local max_attempts=45; local delay=20
  while (( attempt <= max_attempts )); do
    resp=$(curl -s -w "\n%{http_code}" "${AGENT_BASE_URL%/}/v1/documents?page=1&page_size=10&content_hash=$content_hash" \
      -H "Authorization: Bearer $ACCESS_TOKEN")
    status=$(echo "$resp" | tail -n1)
    body=$(echo "$resp" | head -n-1)
    if [[ "$status" == "200" ]]; then
      match=$(echo "$body" | jq -c --arg id "$DOC_ID" '.documents[] | select(.document_id == $id)')
      if [[ -n "$match" ]]; then
        state=$(echo "$match" | jq -r '.status')
        if [[ "$state" == "active" ]]; then
          log "Document $DOC_ID active"
          return
        fi
        log "Waiting for document $DOC_ID status=$state attempt=$attempt"
      else
        log "Document $DOC_ID not listed yet attempt=$attempt"
      fi
    else
      log "Poll failed status=$status body=$body"
    fi
    sleep "$delay"
    attempt=$((attempt + 1))
  done
  log "Document $DOC_ID did not reach active state"
  exit 1
}

create_conversation() {
  local payload resp status body
  payload=$(jq -n --arg country "$SMOKE_COUNTRY_CODE" --arg title "Smoke $TARGET $RUN_ID" --arg namespace "$SMOKE_NAMESPACE" --arg tag "$SMOKE_TAG" '{country_code:$country, namespace:$namespace, title:$title, tags:[$tag, "eval"]}')
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
  CONVERSATION_ID=$(echo "$body" | jq -r '.conversation.conversation_id // .conversation_id')
  echo "$body" >"$TMP_DIR/conversation.json"
  log "Conversation $CONVERSATION_ID created"
}

attach_document() {
  local payload resp status body
  payload=$(jq -n --arg id "$DOC_ID" '{document_ids:[$id], visibility:"visible", role:"primary"}')
  resp=$(curl -s -w "\n%{http_code}" -X POST "${AGENT_BASE_URL%/}/v1/conversations/$CONVERSATION_ID/attachments/bulk" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "$payload")
  status=$(echo "$resp" | tail -n1)
  body=$(echo "$resp" | head -n-1)
  if [[ "$status" != "200" ]]; then
    log "Attachment failed status=$status body=$body"
    exit 1
  fi
  echo "$body" >"$TMP_DIR/attachments.json"
  log "Attached document $DOC_ID"
}

ask_question() {
  local question="$1" expected_tool="$2" idx="$3"
  local payload resp status body citations tool_calls
  payload=$(jq -n --arg thread "$CONVERSATION_ID" --arg q "$question" --arg country "$SMOKE_COUNTRY_CODE" '{thread_id:$thread, message:{type:"user",content:$q}, constraints:{country_code:$country,auto_attach_base_docs:false}, response_mode:"blocking"}')
  resp=$(curl -s -w "\n%{http_code}" -X POST "${AGENT_BASE_URL%/}/v1/chat" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "$payload")
  status=$(echo "$resp" | tail -n1)
  body=$(echo "$resp" | head -n-1)
  printf "%s" "$body" >"$TMP_DIR/q${idx}.json"
  citations=$(echo "$body" | jq '(.done.citations // .done.payload.citations // []) | length')
  tool_calls=$(echo "$body" | jq -c '.done.tool_calls // .done.payload.tool_calls // []')
  log "Q${idx} status=$status citations=$citations tool_calls=$tool_calls"
  if [[ "$status" != "200" ]]; then
    log "Question $idx failed"
    exit 1
  fi
  if [[ "$citations" -eq 0 ]]; then
    log "Question $idx missing citations"
    exit 1
  fi
  if [[ -n "$expected_tool" ]]; then
    if ! echo "$tool_calls" | jq -e --arg tool "$expected_tool" 'map(select(.name == $tool)) | length > 0' >/dev/null; then
      log "Question $idx missing expected tool $expected_tool"
      exit 1
    fi
  fi
}

cleanup_tmp() {
  [[ -d "$TMP_DIR" ]] && rm -rf "$TMP_DIR"
}
trap cleanup_tmp EXIT
TMP_DIR=$(mktemp -d)

if [[ -n "$UPLOAD_FILE" && -z "$DOC_ID" ]]; then
  if [[ ! -f "$UPLOAD_FILE" ]]; then
    log "Upload file not found: $UPLOAD_FILE"
    exit 1
  fi
  upload_path="$UPLOAD_FILE"
  if [[ "$STAMP_UPLOAD" -eq 1 ]]; then
    tmp_copy=$(mktemp /tmp/prod_manual_upload_XXXX."${UPLOAD_FILE##*.}")
    cp "$UPLOAD_FILE" "$tmp_copy"
    printf '\n%% prod-manual-smoke %s\n' "$(date -Iseconds)" >>"$tmp_copy"
    upload_path="$tmp_copy"
  fi
  login_user
  upload_and_wait "$upload_path"
elif [[ -z "$DOC_ID" ]]; then
  log "Either --doc-id or --upload-file is required"
  exit 1
else
  login_user
fi

create_conversation
attach_document

QUESTIONS=(
  "Summarize the main housing finance vulnerabilities highlighted in the Mexico 2016 FSAP report and cite the evidence."
  "List two policy recommendations from the report to strengthen Mexico's mortgage market and mention why each matters."
  "What risks did the report note about housing-related funding sources, and how should they be mitigated?"
  "Using evidence from the Mexico 2016 FSAP housing finance report, use the pyodide_sandbox code execution tool to calculate the compound annual growth rate (CAGR) for a mortgage portfolio growing from 520 billion MXN in 2010 to 1.2 trillion MXN in 2015. Show the Python code you executed and cite the report sections you relied on."
)
EXPECTED_TOOLS=("" "" "" "pyodide_sandbox")

for i in "${!QUESTIONS[@]}"; do
  ask_question "${QUESTIONS[$i]}" "${EXPECTED_TOOLS[$i]}" "$((i+1))"
done

jq -n \
  --arg run_id "$RUN_ID" \
  --arg target "$TARGET" \
  --arg conversation_id "$CONVERSATION_ID" \
  --arg user_email "$PROD_DEMO_EMAIL" \
  --arg agent_url "$AGENT_BASE_URL" \
  --arg ingest_url "$INGEST_BASE_URL" \
  --arg doc_id "$DOC_ID" \
  --argjson conversation "$(cat "$TMP_DIR/conversation.json")" \
  --argjson attachments "$(cat "$TMP_DIR/attachments.json")" \
  --slurpfile q1 "$TMP_DIR/q1.json" \
  --slurpfile q2 "$TMP_DIR/q2.json" \
  --slurpfile q3 "$TMP_DIR/q3.json" \
  --slurpfile q4 "$TMP_DIR/q4.json" \
  '{run_id:$run_id,target:$target,conversation_id:$conversation_id,document_id:$doc_id,user_email:$user_email,agent_base_url:$agent_url,ingest_base_url:$ingest_url,conversation:$conversation,attachments:$attachments,questions:[ $q1[0], $q2[0], $q3[0], $q4[0] ]}' \
  >"$SMOKE_OUTPUT"

log "Smoke complete; report written to $SMOKE_OUTPUT"
