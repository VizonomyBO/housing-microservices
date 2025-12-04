#!/usr/bin/env bash
set -euo pipefail

require_var() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "[prod_smoke_check] Missing required env var: $name" >&2
    exit 1
  fi
}

require_var AGENT_BASE_URL
require_var AUTH_BASE_URL
require_var PROD_DEMO_EMAIL
require_var PROD_DEMO_PASSWORD
require_var PROD_DEMO_COUNTRY
require_var PROD_DEMO_TAG

AUTH_URL="${AUTH_BASE_URL%/}"
AGENT_URL="${AGENT_BASE_URL%/}"
OUT_FILE="${PROD_SAMPLE_OUTPUT:-prod_sample_run.json}"
TMP_JSON="$(mktemp)"
trap 'rm -f "$TMP_JSON"' EXIT

log() { echo "[prod_smoke_check] $*"; }

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

# Fetch seeded documents matching the reduced-e2e tags
log "Fetching seeded documents"
docs_resp=$(curl -sS "$AGENT_URL/v1/documents?page=1&page_size=50&tags=$PROD_DEMO_TAG&tags=demo" \
  -H "Authorization: Bearer $access_token")
doc_ids=($(echo "$docs_resp" | jq -r '.documents[].document_id'))
if [[ ${#doc_ids[@]} -eq 0 ]]; then
  echo "$docs_resp" | jq '.' >&2
  echo "[prod_smoke_check] No documents found. Seed the reduced fixtures before running." >&2
  exit 1
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
