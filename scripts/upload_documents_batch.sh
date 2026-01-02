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
#   SKIP_COUNT (default 0) - skip first N documents, MAX_COUNT - limit total uploads
#   VACUUM_EVERY (default 20) - run VACUUM every N uploads to prevent disk bloat
#   MIN_DISK_FREE_PCT (default 15) - pause if disk free % drops below this
#   SSH_KEY_PATH (default ~/.ssh/house2.pem) - SSH key for remote VACUUM/disk checks
#   PG_CONTAINER (default housing-microservices-postgres-1) - PostgreSQL container name

set -euo pipefail

DOCUMENTS_ROOT=${DOCUMENTS_ROOT:-Documents}
LOG_FILE=${LOG_FILE:-Documents/upload_results.jsonl}
INTERVAL_SECONDS=${INTERVAL_SECONDS:-120}
DEFAULT_LANGUAGE=${DEFAULT_LANGUAGE:-en}
MAX_COUNT=${MAX_COUNT:-0}
SKIP_COUNT=${SKIP_COUNT:-122}
# Run VACUUM every N uploads to prevent orphaned file accumulation (0=disabled)
# Recommended: 10-20 for large batches, lower if disk issues occur
VACUUM_EVERY=${VACUUM_EVERY:-1}
# Minimum free disk % before pausing uploads
MIN_DISK_FREE_PCT=${MIN_DISK_FREE_PCT:-15}
# SSH key for remote server access (for VACUUM and disk checks)
SSH_KEY_PATH=${SSH_KEY_PATH:-~/.ssh/house2.pem}
# PostgreSQL container name
PG_CONTAINER=${PG_CONTAINER:-vizonomy-prod-postgres-1}

# URLs - use defaults if not set
AUTH_BASE_URL=${AUTH_BASE_URL:-http://52.207.140.87:5001}
INGEST_BASE_URL=${INGEST_BASE_URL:-http://52.207.140.87:8085}

# Auth credentials - support both naming conventions
AUTH_LOGIN=${AUTH_LOGIN:-${PROD_DEMO_EMAIL:-demo.client@example.com}}
AUTH_PASSWORD=${AUTH_PASSWORD:-${PROD_DEMO_PASSWORD:-DemoPass123!}}

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

# Get disk usage percentage (returns used %)
get_disk_used_pct() {
  local host=${INGEST_BASE_URL#http://}
  host=${host%%:*}
  local used_pct=""
  
  if [[ -f "$SSH_KEY_PATH" ]]; then
    used_pct=$(ssh -i "$SSH_KEY_PATH" -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes \
      ec2-user@"$host" 'df / --output=pcent | tail -1 | tr -d " %"' </dev/null 2>/dev/null) || true
  fi
  echo "${used_pct:-0}"
}

# Check disk free percentage on remote server
check_disk_space() {
  local host=${INGEST_BASE_URL#http://}
  host=${host%%:*}
  local free_pct=""
  
  # Check if SSH key exists
  if [[ ! -f "$SSH_KEY_PATH" ]]; then
    log "  Disk check: skipped (SSH key not found at $SSH_KEY_PATH)"
    return 0
  fi
  
  # Run SSH directly (works from WSL/Linux) - use || true to prevent script exit
  free_pct=$(ssh -i "$SSH_KEY_PATH" -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes \
    ec2-user@"$host" 'df / --output=avail,size | tail -1' </dev/null 2>/dev/null | awk '{printf "%.0f", ($1/$2)*100}') || true
  
  if [[ -n "$free_pct" && "$free_pct" =~ ^[0-9]+$ ]]; then
    if (( free_pct < MIN_DISK_FREE_PCT )); then
      log "WARNING: Server disk only ${free_pct}% free (threshold: ${MIN_DISK_FREE_PCT}%)"
      log "PAUSING uploads. Run 'VACUUM' on PostgreSQL or free disk space, then restart."
      return 1
    fi
    log "  Disk check: ${free_pct}% free"
  else
    log "  Disk check: skipped (SSH failed)"
  fi
  return 0
}

# Trigger VACUUM on the database to clean up dead tuples and free space
run_vacuum() {
  local host=${INGEST_BASE_URL#http://}
  host=${host%%:*}
  log "Running VACUUM on database to prevent orphaned file accumulation..."
  
  # Check if SSH key exists
  if [[ ! -f "$SSH_KEY_PATH" ]]; then
    log "  VACUUM skipped (SSH key not found at $SSH_KEY_PATH)"
    return 0
  fi
  
  # Run SSH with simplified command - use || true to prevent script exit on failure
  local vacuum_cmd="sudo docker exec $PG_CONTAINER psql -U vizonomy_user -d housing -c 'VACUUM ANALYZE;'"
  
  local output exit_code
  output=$(ssh -i "$SSH_KEY_PATH" -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes \
    ec2-user@"$host" "$vacuum_cmd" </dev/null 2>&1) || true
  exit_code=$?
  
  if [[ $exit_code -eq 0 ]] && [[ -z "$output" || "$output" == *"VACUUM"* ]]; then
    log "  VACUUM completed"
  else
    log "  VACUUM skipped (SSH error): ${output:-no output}"
  fi
  return 0
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

# Skip first SKIP_COUNT documents
if (( SKIP_COUNT > 0 )) && (( ${#targets_files[@]} > SKIP_COUNT )); then
  log "Skipping first $SKIP_COUNT documents..."
  targets_files=("${targets_files[@]:SKIP_COUNT}")
  targets_countries=("${targets_countries[@]:SKIP_COUNT}")
fi

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
  
  # Check disk usage before upload
  DISK_BEFORE=$(get_disk_used_pct)
  if [[ -n "$DISK_BEFORE" && "$DISK_BEFORE" -gt 0 ]]; then
    log "  📊 Disk before: ${DISK_BEFORE}% used"
    
    # Wait if disk is above 85%
    while [[ "$DISK_BEFORE" -gt 85 ]]; do
      log "  ⚠️  HIGH DISK USAGE (${DISK_BEFORE}%)! Waiting 60s for cleanup..."
      sleep 60
      DISK_BEFORE=$(get_disk_used_pct)
    done
  fi
  
  # Ensure token is valid (refresh if needed)
  if ! ensure_token; then
    log "  ERROR: Token refresh failed. Skipping $name"
    continue
  fi
  
  # Step 2: Get file size (per runbook step 2)
  FILE_SIZE=$(get_file_size "$file")
  FILE_SIZE_MB=$(awk "BEGIN {printf \"%.1f\", $FILE_SIZE/1024/1024}")
  log "  File size: ${FILE_SIZE_MB} MB"
  
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
  
  # Show progress bar during upload (progress goes to stderr, response to stdout)
  UPLOAD_RESULT=$(curl --progress-bar -X POST "$UPLOAD_URL" \
    -H "Authorization: Bearer $TOKEN" \
    "${FORM_ARGS[@]}" 2>/dev/tty) || true
  
  log "  Upload response: $UPLOAD_RESULT"
  
  # Check if upload succeeded
  UPLOAD_STATUS=$(echo "$UPLOAD_RESULT" | jq -r '.status // empty')
  INGESTION_ID=$(echo "$UPLOAD_RESULT" | jq -r '.ingestion_id // empty')
  
  if [[ "$UPLOAD_STATUS" == "active" ]] || [[ -n "$INGESTION_ID" ]]; then
    status_label="success"
    log "  ✅ SUCCESS: $name uploaded (doc_id=$DOC_ID)"
    
    # Check disk after ingestion completed
    DISK_AFTER=$(get_disk_used_pct)
    if [[ -n "$DISK_AFTER" && "$DISK_AFTER" -gt 0 ]]; then
      DISK_DELTA=$((DISK_AFTER - DISK_BEFORE))
      log "  📊 Disk after: ${DISK_AFTER}% used (${DISK_DELTA:+$DISK_DELTA}% change)"
      
      # Warn if disk jumped significantly
      if [[ "$DISK_DELTA" -gt 10 ]]; then
        log "  ⚠️  Large disk increase detected! Consider running VACUUM."
      fi
    fi
  else
    status_label="error"
    log "  ❌ FAILED: $name upload error. Response: $UPLOAD_RESULT"
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
  
  # Cleanup large variables to release memory
  unset UPLOAD_RESP UPLOAD_RESULT UPLOAD_FIELDS DOC_ID UPLOAD_URL UPLOAD_STATUS INGESTION_ID FORM_ARGS
  
  # Periodic maintenance to prevent orphaned file accumulation
  if (( VACUUM_EVERY > 0 )) && (( (i + 1) % VACUUM_EVERY == 0 )); then
    run_vacuum
  fi
  
  # Wait before next file
  if (( i + 1 < total )); then
    # Check disk space before continuing
    if ! check_disk_space; then
      log "FATAL: Disk space too low. Stopping uploads at file $((i+1))/$total"
      log "Resume with: SKIP_COUNT=$((SKIP_COUNT + i + 1)) ./scripts/upload_documents_batch.sh"
      exit 1
    fi
    log "  Waiting ${INTERVAL_SECONDS}s before next file..."
    sleep "$INTERVAL_SECONDS"
  fi
done

# Final cleanup
if (( VACUUM_EVERY > 0 )); then
  run_vacuum
fi

# Run final materialized view refresh (important if SKIP_VIEW_REFRESH was enabled)
log "Running final cleanup..."
if [[ -f "$SSH_KEY_PATH" ]]; then
  REFRESH_HOST=${INGEST_BASE_URL#http://}
  REFRESH_HOST=${REFRESH_HOST%%:*}
  
  log "  1. Refreshing materialized view..."
  ssh -i "$SSH_KEY_PATH" -o ConnectTimeout=30 -o StrictHostKeyChecking=no -o BatchMode=yes \
    ec2-user@"$REFRESH_HOST" \
    "sudo docker exec $PG_CONTAINER psql -U vizonomy_user -d housing -c 'REFRESH MATERIALIZED VIEW active_chunks;'" \
    </dev/null 2>/dev/null && log "    View refresh completed" || log "    View refresh skipped"
  
  log "  2. Recreating vector index (this may take a while)..."
  ssh -i "$SSH_KEY_PATH" -o ConnectTimeout=600 -o StrictHostKeyChecking=no -o BatchMode=yes \
    ec2-user@"$REFRESH_HOST" \
    "sudo docker exec $PG_CONTAINER psql -U vizonomy_user -d housing -c 'CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_ip_ops) WITH (m = 16, ef_construction = 64);'" \
    </dev/null 2>/dev/null && log "    Index created" || log "    Index creation skipped"
fi

log "Done. Log written to $LOG_FILE"






