#!/usr/bin/env bash

# Upload a single document (ARG.pdf) to the ingestion FastAPI service.
# Follows the exact flow from docs/runbooks/prod_setup.md section 5.
#
# Usage:
#   env_file=$(scripts/use_env.sh aws) && set -a && source "$env_file" && set +a
#   ./scripts/upload_document_single.sh [path/to/ARG.pdf]
#
# Required env (from .env.prod or exported):
#   AUTH_BASE_URL, INGEST_BASE_URL
#   PROD_DEMO_EMAIL, PROD_DEMO_PASSWORD (or AUTH_LOGIN, AUTH_PASSWORD)
# Optional:
#   INGEST_UPLOAD_API_KEY, DOCUMENT_PATH, COUNTRY_CODE, LANGUAGE

set -euo pipefail

# Document path - use argument or env var or default
DOCUMENT_PATH=${1:-${DOCUMENT_PATH:-ARG.pdf}}
COUNTRY_CODE=${COUNTRY_CODE:-ARG}
LANGUAGE=${LANGUAGE:-en}

# URLs - use defaults if not set
AUTH_BASE_URL=${AUTH_BASE_URL:-http://52.207.140.87:5001}
INGEST_BASE_URL=${INGEST_BASE_URL:-http://52.207.140.87:8085}

# Auth credentials - support both naming conventions
AUTH_LOGIN=${AUTH_LOGIN:-${PROD_DEMO_EMAIL:-demo_client}}
AUTH_PASSWORD=${AUTH_PASSWORD:-${PROD_DEMO_PASSWORD:-ChangeMe!123}}

# Token expires in 900s (15 min); refresh when 60s from expiry
TOKEN_REFRESH_THRESHOLD=840

# Global token state
TOKEN=""
TOKEN_OBTAINED_AT=0

require() { command -v "$1" >/dev/null 2>&1 || { echo "Missing required tool: $1" >&2; exit 1; }; }
require jq
require curl

log() {
  echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*"
}

get_file_size() {
  local file=$1
  # macOS uses -f%z, Linux uses -c%s
  if stat -f%z "$file" >/dev/null 2>&1; then
    stat -f%z "$file"
  else
    stat -c%s "$file"
  fi
}

current_epoch() {
  date +%s
}

# Login and get token (per runbook step 1)
# Only refreshes if token is missing or close to expiry
ensure_token() {
  local now
  now=$(current_epoch)
  local token_age=$((now - TOKEN_OBTAINED_AT))
  
  # If we have a valid token that's not close to expiring, reuse it
  if [[ -n "$TOKEN" ]] && (( token_age < TOKEN_REFRESH_THRESHOLD )); then
    return 0
  fi
  
  log "Logging in as $AUTH_LOGIN to $AUTH_BASE_URL..."
  local resp
  resp=$(curl -sS -X POST "$AUTH_BASE_URL/v1/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"login\":\"$AUTH_LOGIN\",\"password\":\"$AUTH_PASSWORD\"}" 2>&1)
  
  local new_token
  new_token=$(echo "$resp" | jq -r '.access_token // empty')
  
  if [[ -z "$new_token" ]]; then
    log "ERROR: Login failed. Response: $resp"
    return 1
  fi
  
  TOKEN="$new_token"
  TOKEN_OBTAINED_AT=$(current_epoch)
  log "Login successful. Token obtained (valid for ~15 min)."
  return 0
}

# Validate file exists
if [[ ! -f "$DOCUMENT_PATH" ]]; then
  log "ERROR: File not found: $DOCUMENT_PATH"
  exit 1
fi

name=$(basename "$DOCUMENT_PATH")
ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

log "Uploading single document: $name (country: $COUNTRY_CODE)"

# Get initial token
if ! ensure_token; then
  log "FATAL: Cannot obtain initial token. Exiting."
  exit 1
fi

# Step 2: Get file size (per runbook step 2)
FILE_SIZE=$(get_file_size "$DOCUMENT_PATH")
log "File size: $FILE_SIZE bytes"

# Step 3: Request presigned upload (per runbook step 3)
log "Requesting presign from $INGEST_BASE_URL/v1/documents/upload..."

UPLOAD_RESP=$(jq -n \
  --arg name "$name" \
  --arg country "$COUNTRY_CODE" \
  --argjson size "$FILE_SIZE" \
  --arg lang "$LANGUAGE" \
  '{document_name:$name, source_type:"pdf", country_code:$country, language:$lang,
    file_size_bytes:$size, tags:["single-upload"], metadata:{scenario:"single_upload"}}' | \
  curl -sS -X POST "$INGEST_BASE_URL/v1/documents/upload" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $TOKEN" \
    ${INGEST_UPLOAD_API_KEY:+-H "x-api-key: $INGEST_UPLOAD_API_KEY"} \
    -d @- 2>&1) || true

log "Presign response: $UPLOAD_RESP"

DOC_ID=$(echo "$UPLOAD_RESP" | jq -r '.document_id // empty')
UPLOAD_URL=$(echo "$UPLOAD_RESP" | jq -r '.upload.url // empty')
UPLOAD_FIELDS=$(echo "$UPLOAD_RESP" | jq -c '.upload.fields // {}')

if [[ -z "$DOC_ID" || -z "$UPLOAD_URL" ]]; then
  log "ERROR: Presign failed. Response: $UPLOAD_RESP"
  exit 1
fi

log "Presign OK: doc_id=$DOC_ID, upload_url=$UPLOAD_URL"

# Step 4: POST the binary (per runbook step 4)
log "Uploading file to $UPLOAD_URL..."

FORM_ARGS=()
while IFS=$'\t' read -r key val; do
  FORM_ARGS+=(-F "$key=$val")
done < <(echo "$UPLOAD_FIELDS" | jq -r 'to_entries[] | [.key, (.value|tostring)] | @tsv')
FORM_ARGS+=(-F "file=@${DOCUMENT_PATH}")

UPLOAD_RESULT=$(curl -sS -X POST "$UPLOAD_URL" \
  -H "Authorization: Bearer $TOKEN" \
  "${FORM_ARGS[@]}" 2>&1) || true

log "Upload response: $UPLOAD_RESULT"

# Check if upload succeeded
UPLOAD_STATUS=$(echo "$UPLOAD_RESULT" | jq -r '.status // empty')
INGESTION_ID=$(echo "$UPLOAD_RESULT" | jq -r '.ingestion_id // empty')

if [[ "$UPLOAD_STATUS" == "active" ]] || [[ -n "$INGESTION_ID" ]]; then
  log "SUCCESS: $name uploaded (doc_id=$DOC_ID, ingestion_id=$INGESTION_ID)"
  echo "Document ID: $DOC_ID"
  echo "Ingestion ID: $INGESTION_ID"
  exit 0
else
  log "FAILED: $name upload error. Response: $UPLOAD_RESULT"
  exit 1
fi
