#!/usr/bin/env bash

# Batch-upload documents from Documents/ to the ingestion FastAPI service.
# Follows the exact flow from docs/runbooks/prod_setup.md section 5.
#
# Usage:
#   env_file=$(scripts/use_env.sh aws) && set -a && source "$env_file" && set +a
#   ./scripts/upload_documents_batch.sh
#
# Required env (from .env.prod or exported):
#   AUTH_BASE_URL, INGEST_BASE_URL
#   PROD_DEMO_EMAIL, PROD_DEMO_PASSWORD (or AUTH_LOGIN, AUTH_PASSWORD)
# Optional:
#   INGEST_UPLOAD_API_KEY, INTERVAL_SECONDS (default 120), DOCUMENTS_ROOT, LOG_FILE

set -euo pipefail

DOCUMENTS_ROOT=${DOCUMENTS_ROOT:-Documents}
LOG_FILE=${LOG_FILE:-Documents/upload_results.jsonl}
INTERVAL_SECONDS=${INTERVAL_SECONDS:-120}
DEFAULT_LANGUAGE=${DEFAULT_LANGUAGE:-en}
MAX_COUNT=${MAX_COUNT:-0}

# URLs - use defaults if not set
AUTH_BASE_URL=${AUTH_BASE_URL:-http://52.207.140.87:5001}
INGEST_BASE_URL=${INGEST_BASE_URL:-http://52.207.140.87:8085}

# Auth credentials - support both naming conventions
AUTH_LOGIN=${AUTH_LOGIN:-${PROD_DEMO_EMAIL:-demo_client}}
AUTH_PASSWORD=${AUTH_PASSWORD:-${PROD_DEMO_PASSWORD:-ChangeMe!123}}

# Token expires in 900s (15 min); refresh when 60s from expiry
TOKEN_REFRESH_THRESHOLD=840

SKIP_DIRS=("# All Countries" "# UNKNOWN" "All countries" "unknown")

# Global token state
TOKEN=""
TOKEN_OBTAINED_AT=0

require() { command -v "$1" >/dev/null 2>&1 || { echo "Missing required tool: $1" >&2; exit 1; }; }
require jq
require curl

mkdir -p "$(dirname "$LOG_FILE")"

log() {
  echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*"
}

log_json() {
  jq -n "$@" >>"$LOG_FILE"
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

should_skip_dir() {
  local dir_name=$1
  for skip in "${SKIP_DIRS[@]}"; do
    [[ "$dir_name" == "$skip" ]] && return 0
  done
  return 1
}

# Build file list
targets_files=()
targets_countries=()
while IFS= read -r -d '' file_path; do
  rel=${file_path#"$DOCUMENTS_ROOT"/}
  country=${rel%%/*}

  # Skip files not nested under a country dir
  [[ "$rel" == "$file_path" ]] && continue
  [[ "$rel" == "$country" ]] && continue
  [[ "$country" == .* ]] && continue
  should_skip_dir "$country" && continue

  # Expect ISO-like codes (3 letters)
  if ! [[ "$country" =~ ^[A-Za-z]{3}$ ]]; then
    continue
  fi

  targets_files+=("$file_path")
  targets_countries+=("$country")
done < <(find "$DOCUMENTS_ROOT" -type f ! -name '.DS_Store' -print0 | sort -z)

if (( MAX_COUNT > 0 )) && (( ${#targets_files[@]} > MAX_COUNT )); then
  targets_files=("${targets_files[@]:0:MAX_COUNT}")
  targets_countries=("${targets_countries[@]:0:MAX_COUNT}")
fi

total=${#targets_files[@]}
if (( total == 0 )); then
  echo "No files found under $DOCUMENTS_ROOT (after skips/filters)." >&2
  exit 1
fi

log "Prepared $total files from $DOCUMENTS_ROOT (interval ${INTERVAL_SECONDS}s)"
for i in "${!targets_files[@]}"; do
  printf "  [%d/%d] %s :: %s\n" "$((i+1))" "$total" "${targets_countries[$i]}" "$(basename "${targets_files[$i]}")"
done

# Get initial token
if ! ensure_token; then
  log "FATAL: Cannot obtain initial token. Exiting."
  exit 1
fi

# Main upload loop
for i in "${!targets_files[@]}"; do
  file=${targets_files[$i]}
  country=${targets_countries[$i]}
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  name=$(basename "$file")
  
  log "[$((i+1))/$total] Processing: $country :: $name"
  
  # Ensure token is valid (refresh if needed)
  if ! ensure_token; then
    log "  ERROR: Token refresh failed. Skipping $name"
    continue
  fi
  
  # Step 2: Get file size (per runbook step 2)
  FILE_SIZE=$(get_file_size "$file")
  log "  File size: $FILE_SIZE bytes"
  
  # Step 3: Request presigned upload (per runbook step 3)
  log "  Requesting presign from $INGEST_BASE_URL/v1/documents/upload..."
  
  UPLOAD_RESP=$(jq -n \
    --arg name "$name" \
    --arg country "$country" \
    --argjson size "$FILE_SIZE" \
    '{document_name:$name, source_type:"pdf", country_code:$country, language:"en",
      file_size_bytes:$size, tags:["bulk-upload"], metadata:{scenario:"batch_upload"}}' | \
    curl -sS -X POST "$INGEST_BASE_URL/v1/documents/upload" \
      -H 'Content-Type: application/json' \
      -H "Authorization: Bearer $TOKEN" \
      ${INGEST_UPLOAD_API_KEY:+-H "x-api-key: $INGEST_UPLOAD_API_KEY"} \
      -d @- 2>&1) || true
  
  log "  Presign response: $UPLOAD_RESP"
  
  DOC_ID=$(echo "$UPLOAD_RESP" | jq -r '.document_id // empty')
  UPLOAD_URL=$(echo "$UPLOAD_RESP" | jq -r '.upload.url // empty')
  UPLOAD_FIELDS=$(echo "$UPLOAD_RESP" | jq -c '.upload.fields // {}')
  
  if [[ -z "$DOC_ID" || -z "$UPLOAD_URL" ]]; then
    log "  ERROR: Presign failed. Response: $UPLOAD_RESP"
    log_json --arg ts "$ts" --arg status "error" --arg step "presign" \
      --arg file_path "$file" --arg country_code "$country" --arg response "$UPLOAD_RESP" \
      '{timestamp:$ts, status:$status, step:$step, file_path:$file_path, country_code:$country_code, response:$response}'
    
    if (( i + 1 < total )); then sleep "$INTERVAL_SECONDS"; fi
    continue
  fi
  
  log "  Presign OK: doc_id=$DOC_ID, upload_url=$UPLOAD_URL"
  
  # Step 4: POST the binary (per runbook step 4)
  log "  Uploading file to $UPLOAD_URL..."
  
  FORM_ARGS=()
  while IFS=$'\t' read -r key val; do
    FORM_ARGS+=(-F "$key=$val")
  done < <(echo "$UPLOAD_FIELDS" | jq -r 'to_entries[] | [.key, (.value|tostring)] | @tsv')
  FORM_ARGS+=(-F "file=@${file}")
  
  UPLOAD_RESULT=$(curl -sS -X POST "$UPLOAD_URL" \
    -H "Authorization: Bearer $TOKEN" \
    "${FORM_ARGS[@]}" 2>&1) || true
  
  log "  Upload response: $UPLOAD_RESULT"
  
  # Check if upload succeeded
  UPLOAD_STATUS=$(echo "$UPLOAD_RESULT" | jq -r '.status // empty')
  INGESTION_ID=$(echo "$UPLOAD_RESULT" | jq -r '.ingestion_id // empty')
  
  if [[ "$UPLOAD_STATUS" == "active" ]] || [[ -n "$INGESTION_ID" ]]; then
    status_label="success"
    log "  SUCCESS: $name uploaded (doc_id=$DOC_ID, ingestion_id=$INGESTION_ID)"
  else
    status_label="error"
    log "  FAILED: $name upload error. Response: $UPLOAD_RESULT"
  fi
  
  # Log result
  log_json --arg ts "$ts" \
    --arg status "$status_label" \
    --arg doc_id "$DOC_ID" \
    --arg ingestion_id "$INGESTION_ID" \
    --arg file_path "$file" \
    --arg country_code "$country" \
    --arg upload_url "$UPLOAD_URL" \
    --arg response "$UPLOAD_RESULT" \
    '{timestamp:$ts, status:$status, document_id:$doc_id, ingestion_id:$ingestion_id,
      file_path:$file_path, country_code:$country_code, upload_url:$upload_url, response:$response}'
  
  printf "[%d/%d] %s %s :: %s (doc_id=%s)\n" \
    "$((i+1))" "$total" \
    "$( [[ "$status_label" == "success" ]] && echo "OK" || echo "FAIL")" \
    "$country" "$name" "$DOC_ID"
  
  # Wait before next file
  if (( i + 1 < total )); then
    log "  Waiting ${INTERVAL_SECONDS}s before next file..."
    sleep "$INTERVAL_SECONDS"
  fi
done

log "Done. Log written to $LOG_FILE"




