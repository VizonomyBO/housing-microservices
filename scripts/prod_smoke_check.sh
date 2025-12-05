#!/usr/bin/env bash
set -euo pipefail

log() { echo "[prod_smoke_check] $*" >&2; }

require_var() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    log "Missing required env var: $name"
    exit 1
  fi
}

require_var AGENT_BASE_URL
require_var AUTH_BASE_URL
require_var PROD_DEMO_EMAIL
require_var PROD_DEMO_PASSWORD
require_var PROD_DEMO_COUNTRY
require_var PROD_DEMO_TAG

SMOKE_UPLOAD_FILE=${SMOKE_UPLOAD_FILE:-services/agent-api/tests/data/reduced_e2e/doc_policy.md}
if [[ ! -f "$SMOKE_UPLOAD_FILE" ]]; then
  log "Upload file $SMOKE_UPLOAD_FILE not found"
  exit 1
fi

USE_INGEST_API=0
if [[ -n "${INGEST_BASE_URL:-}" ]]; then
  USE_INGEST_API=1
  INGEST_UPLOAD_URL="${INGEST_BASE_URL%/}/v1/documents/upload"
  log "INGEST_BASE_URL detected; smoke test will upload via $INGEST_UPLOAD_URL"
fi

get_file_size() {
  local path="$1"
  if stat --version >/dev/null 2>&1; then
    stat -c%s "$path"
  else
    stat -f%z "$path"
  fi
}

compute_file_hash() {
  local path="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$path" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$path" | awk '{print $1}'
  else
    python3 - "$path" <<'PY'
import hashlib, sys
path = sys.argv[1]
with open(path, "rb") as fp:
    data = fp.read()
print(hashlib.sha256(data).hexdigest())
PY
  fi
}

perform_presigned_upload() {
  local upload_url="$1"
  local fields_json="$2"
  local file_path="$3"
  local -a form_args=()
  local content_type
  content_type=$(echo "$fields_json" | jq -r '.["Content-Type"] // empty')
  while IFS=$'\t' read -r key value; do
    form_args+=(-F "$key=$value")
  done < <(echo "$fields_json" | jq -r 'to_entries[] | [.key, (.value|tostring)] | @tsv')
  if [[ -n "$content_type" ]]; then
    form_args+=(-F "file=@${file_path};type=${content_type}")
  else
    form_args+=(-F "file=@$file_path")
  fi
  curl -sSf -X POST "$upload_url" "${form_args[@]}" >/dev/null
}

poll_document_activation() {
  local document_id="$1"
  local content_hash="${2:-}"
  local max_attempts=${INGEST_MAX_POLL_ATTEMPTS:-40}
  local sleep_seconds=${INGEST_POLL_INTERVAL_SEC:-5}
  local attempt=1
  local last_resp=""
  while (( attempt <= max_attempts )); do
    local query="page=1&page_size=50"
    if [[ -n "$content_hash" ]]; then
      query="$query&content_hash=$content_hash"
    else
      query="$query&tags=$PROD_DEMO_TAG"
    fi
    last_resp=$(curl -sS "$AGENT_URL/v1/documents?$query" \
      -H "Authorization: Bearer $access_token")
    local status stage
    local match
    match=$(echo "$last_resp" | jq -c --arg doc "$document_id" '.documents[] | select(.document_id == $doc)')
    if [[ -n "$match" ]]; then
      status=$(echo "$match" | jq -r '.status // empty')
      stage=$(echo "$match" | jq -r '.ingestion_stage // empty')
      if [[ "$status" == "active" ]]; then
        log "Document $document_id active (stage=${stage:-unknown})"
        return 0
      fi
      log "Waiting for document $document_id (status=${status:-pending}, stage=${stage:-pending}) attempt $attempt/$max_attempts"
    else
      log "Document $document_id not yet listed (attempt $attempt/$max_attempts)"
    fi
    sleep "$sleep_seconds"
    attempt=$((attempt + 1))
  done
  echo "$last_resp" | jq '.' >&2
  log "Document $document_id did not reach active state in time"
  exit 1
}

ingest_upload_document() {
  local file_path="$1"
  local document_name="$2"
  local source_type="${3:-md}"
  local file_size
  file_size=$(get_file_size "$file_path")
  local file_hash
  file_hash=$(compute_file_hash "$file_path")
  local ingest_payload
  ingest_payload=$(jq -n \
    --arg name "$document_name" \
    --arg source "$source_type" \
    --arg country "$PROD_DEMO_COUNTRY" \
    --argjson size "$file_size" \
    '{
        document_name:$name,
        source_type:$source,
        country_code:$country,
        language:"en",
        file_size_bytes:$size,
        tags:["demo","prod_smoke"],
        access_scope:"user_private",
        metadata:{smoke_test:true}
     }')

  local -a ingest_headers=(-H "Authorization: Bearer $access_token" -H 'Content-Type: application/json')
  if [[ -n "${INGEST_UPLOAD_API_KEY:-}" ]]; then
    ingest_headers+=(-H "x-api-key: $INGEST_UPLOAD_API_KEY")
  fi

  log "Requesting presigned upload from ingestion API"
  local ingest_resp
  ingest_resp=$(curl -sS -X POST "$INGEST_UPLOAD_URL" \
    "${ingest_headers[@]}" \
    -d "$ingest_payload")
  local document_id upload_url fields_json status
  document_id=$(echo "$ingest_resp" | jq -r '.document_id // empty')
  upload_url=$(echo "$ingest_resp" | jq -r '.upload.url // empty')
  fields_json=$(echo "$ingest_resp" | jq -c '.upload.fields // {}')
  status=$(echo "$ingest_resp" | jq -r '.status // empty')
  if [[ -z "$document_id" ]]; then
    echo "$ingest_resp" | jq '.' >&2
    log "Failed to request presigned upload"
    exit 1
  fi
  if [[ "$status" == "DEDUPED" ]]; then
    log "Document $document_id already ingested; skipped presigned upload"
    poll_document_activation "$document_id" "$file_hash"
    echo "$document_id"
    return 0
  fi
  if [[ -z "$upload_url" ]]; then
    echo "$ingest_resp" | jq '.' >&2
    log "Failed to obtain presigned fields"
    exit 1
  fi
  perform_presigned_upload "$upload_url" "$fields_json" "$file_path"
  poll_document_activation "$document_id" "$file_hash"
  echo "$document_id"
}

agent_upload_document() {
  local file_path="$1"
  local document_name="$2"
  local chunk_type="${3:-text}"
  local file_hash
  file_hash=$(compute_file_hash "$file_path")
  local payload
  payload=$(jq -n \
    --rawfile content "$file_path" \
    --arg name "$document_name" \
    --arg chunk "$chunk_type" \
    --arg country "$PROD_DEMO_COUNTRY" \
    '{
        document_name:$name,
        content:$content,
        content_type:"text/markdown",
        chunk_type:$chunk,
        access_scope:"user_private",
        country_code:$country,
        language:"en",
        tags:["demo","prod_smoke"],
        metadata:{smoke_test:true}
     }')
  log "Uploading document via Agent API"
  local resp
  resp=$(curl -sS -X POST "$AGENT_URL/v1/documents/upload" \
    -H "Authorization: Bearer $access_token" \
    -H 'Content-Type: application/json' \
    -d "$payload")
  local status document_id
  status=$(echo "$resp" | jq -r '.status // empty')
  document_id=$(echo "$resp" | jq -r '.document_id // empty')
  if [[ -z "$document_id" ]]; then
    echo "$resp" | jq '.' >&2
    log "Agent API upload failed"
    exit 1
  fi
  case "$status" in
    COMPLETED)
      poll_document_activation "$document_id" "$file_hash"
      ;;
    DEDUPED)
      log "Document $document_id already ingested; reusing existing record"
      ;;
    *)
      echo "$resp" | jq '.' >&2
      log "Agent API upload failed (status=$status)"
      exit 1
      ;;
  esac
  echo "$document_id"
}

AUTH_URL="${AUTH_BASE_URL%/}"
AGENT_URL="${AGENT_BASE_URL%/}"
OUT_FILE="${PROD_SAMPLE_OUTPUT:-prod_sample_run.json}"
TMP_JSON="$(mktemp)"
trap 'rm -f "$TMP_JSON"' EXIT

login_payload=$(jq -n \
  --arg login "$PROD_DEMO_EMAIL" \
  --arg password "$PROD_DEMO_PASSWORD" \
  '{login:$login,password:$password}')

log "Logging in as $PROD_DEMO_EMAIL"
login_resp=$(curl -sS -X POST "$AUTH_URL/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d "$login_payload")
access_token=$(echo "$login_resp" | jq -r '.access_token // empty')
if [[ -z "$access_token" ]]; then
  echo "$login_resp" | jq '.' >&2
  echo "[prod_smoke_check] Failed to obtain access token" >&2
  exit 1
fi

# Create or reuse a conversation for this run
conversation_payload=$(jq -n \
  --arg country "$PROD_DEMO_COUNTRY" \
  --arg tag "$PROD_DEMO_TAG" \
  '{country_code:$country, namespace:"prod-demo", tags:[$tag, "prod_demo"]}')
log "Ensuring conversation exists"
conversation_resp=$(curl -sS -X POST "$AGENT_URL/v1/conversations" \
  -H "Authorization: Bearer $access_token" \
  -H 'Content-Type: application/json' \
  -d "$conversation_payload")
conversation_id=$(echo "$conversation_resp" | jq -r '.conversation.conversation_id // empty')
if [[ -z "$conversation_id" ]]; then
  echo "$conversation_resp" | jq '.' >&2
  echo "[prod_smoke_check] Failed to create conversation" >&2
  exit 1
fi
log "Using conversation $conversation_id"

uploaded_doc_ids=()
source_ext="${SMOKE_UPLOAD_FILE##*.}"
upload_name="Prod Smoke Upload $(date +%s)"
if [[ $USE_INGEST_API -eq 1 ]]; then
  new_doc_id=$(ingest_upload_document "$SMOKE_UPLOAD_FILE" "$upload_name" "$source_ext")
  log "Uploaded document via ingestion API: $new_doc_id"
else
  new_doc_id=$(agent_upload_document "$SMOKE_UPLOAD_FILE" "$upload_name")
  log "Uploaded document via Agent API: $new_doc_id"
fi
uploaded_doc_ids+=("$new_doc_id")

# Fetch seeded documents matching the reduced-e2e tags
log "Fetching seeded documents"
docs_resp=$(curl -sS "$AGENT_URL/v1/documents?page=1&page_size=50&tags=$PROD_DEMO_TAG&tags=demo" \
  -H "Authorization: Bearer $access_token")
existing_doc_ids=($(echo "$docs_resp" | jq -r '.documents[].document_id'))
if [[ ${#existing_doc_ids[@]} -eq 0 && ${#uploaded_doc_ids[@]} -eq 0 ]]; then
  echo "$docs_resp" | jq '.' >&2
  log "No documents found. Seed the reduced fixtures before running."
  exit 1
fi

doc_ids=()
if [[ ${#uploaded_doc_ids[@]} -gt 0 ]]; then
  doc_ids+=("${uploaded_doc_ids[@]}")
fi
if [[ ${#existing_doc_ids[@]} -gt 0 ]]; then
  doc_ids+=("${existing_doc_ids[@]}")
fi

for doc_id in "${doc_ids[@]}"; do
  attach_payload=$(jq -n --arg doc "$doc_id" '{document_id:$doc, auto_attach_base_docs:false}')
  curl -sS -X POST "$AGENT_URL/v1/conversations/$conversation_id/attachments" \
    -H "Authorization: Bearer $access_token" \
    -H 'Content-Type: application/json' \
    -d "$attach_payload" >/dev/null
  log "Attached $doc_id"
done

questions=(
  "What two guardrails did the latest housing memo add for voucher expansion?"
  "Suggest two interventions that combine the policy memo and ledger insights to help District 9 renters."
  "While reviewing the KPI dashboard for our cities, point out anyone crossing the 80-point stability trigger and explain what action they need."
)
prompts=(
  "PROD_SIMPLE_RAG"
  "PROD_REASONING"
  "PROD_TABLE_SQL"
)

for i in "${!questions[@]}"; do
  question="${questions[$i]}"
  prompt_id="${prompts[$i]}"
payload=$(jq -n \
  --arg thread "$conversation_id" \
  --arg question "$question" \
  --arg country "$PROD_DEMO_COUNTRY" \
  '{
      thread_id:$thread,
      message:{type:"user",content:$question},
      constraints:{country_code:$country,auto_attach_base_docs:false},
      response_mode:"blocking"
    }')

  log "Asking: $question"
  response=$(curl -sS -X POST "$AGENT_URL/v1/chat" \
    -H "Authorization: Bearer $access_token" \
    -H 'Content-Type: application/json' \
    -d "$payload")

  echo "$response" | jq --arg question "$question" --arg prompt "$prompt_id" '{
    question:$question,
    prompt_id:$prompt,
    answer:(.done.answer // .done.payload.answer // ""),
    citations:(.done.citations // .done.payload.citations // []),
    requires_sql:(.done.requires_sql // .done.payload.requires_sql // false),
    sql_queries:(.done.sql_queries // .done.payload.sql_queries // []),
    sql_row_count:(
      .done.sql_row_count //
      .done.payload.sql_row_count //
      .done.numerical_trace.executor.row_count //
      .done.payload.numerical_trace.executor.row_count //
      null
    ),
    table_results:(.done.table_results // .done.payload.table_results // []),
    raw_response:.
  }' >> "$TMP_JSON"

done

jq -s --arg conversation_id "$conversation_id" \
  --arg timestamp "$(date -Iseconds)" \
  --arg backend "$AGENT_URL" \
  --arg mode "${USE_LOCALSTACK:-1}" '{
    timestamp:$timestamp,
    conversation_id:$conversation_id,
    agent_base_url:$backend,
    localstack_mode:$mode,
    questions:.
  }' "$TMP_JSON" > "$OUT_FILE"

log "Responses written to $OUT_FILE"
