#!/usr/bin/env bash
# ==============================================================================
# schedule_report_pregeneration.sh
# ==============================================================================
# Scheduled job that pre-generates housing reports for the NEXT month.
# 
# This script should be run via cron/systemd timer before the end of each month
# (e.g., on the 25th) to ensure reports are ready when the new month begins.
#
# The script:
#   1. Calculates the next month automatically
#   2. Queries all countries with documents
#   3. Generates reports for each country, caching them under the next month's key
#
# Cron Example (run on the 25th of each month at 2 AM):
#   0 2 25 * * /path/to/scripts/schedule_report_pregeneration.sh --target prod
#
# Systemd Timer Example:
#   See schedule_report_pregeneration.timer and schedule_report_pregeneration.service
#
# Usage:
#   ./scripts/schedule_report_pregeneration.sh
#   ./scripts/schedule_report_pregeneration.sh --target prod
#   ./scripts/schedule_report_pregeneration.sh --target prod --notify-email ops@example.com
#
# Options:
#   --env-file       Path to env file (optional, uses scripts/use_env.sh)
#   --target         Target environment: local|dev|prod (default: prod)
#   --access-scope   Filter documents by access scope (default: base)
#   --output-dir     Directory to save downloaded PDFs (optional, default: ./reports)
#   --dry-run        Print what would be done without executing
#   --limit          Max number of countries to process (optional, for testing)
#   --notify-email   Email address for completion notification (requires mail command)
#   --log-file       Path to log file (default: /tmp/report_pregen_YYYYMM.log)
#
# Environment Variables:
#   AGENT_BASE_URL   Agent API base URL (auto-detected from env)
#   AUTH_BASE_URL    Auth service URL for login
#   SMOKE_USER_EMAIL / SMOKE_USER_PASSWORD  Credentials for API access
#   PROD_DEMO_EMAIL / PROD_DEMO_PASSWORD    Alternative credential names
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

# Colors for output (disabled in non-interactive mode)
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    NC=''
fi

# Calculate next month
get_next_month() {
    # Cross-platform: works on both GNU date and BSD date
    if date --version >/dev/null 2>&1; then
        # GNU date
        date -d "+1 month" +%Y-%m
    else
        # BSD date (macOS)
        date -v+1m +%Y-%m
    fi
}

NEXT_MONTH=$(get_next_month)
RUN_ID=$(date +%Y%m%d_%H%M%S)

log_info()  { echo -e "${BLUE}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"; }
log_error() { echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"; }

# Defaults
ACCESS_SCOPE="base"
OUTPUT_DIR="$ROOT_DIR/reports"
ENV_FILE=""
TARGET="prod"
DRY_RUN="false"
LIMIT=""
NOTIFY_EMAIL=""
LOG_FILE="/tmp/report_pregen_${NEXT_MONTH//-/}.log"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --access-scope)
            ACCESS_SCOPE="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --env-file)
            ENV_FILE="$2"
            shift 2
            ;;
        --target)
            TARGET="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --notify-email)
            NOTIFY_EMAIL="$2"
            shift 2
            ;;
        --log-file)
            LOG_FILE="$2"
            shift 2
            ;;
        -h|--help)
            head -50 "$0" | tail -48
            exit 0
            ;;
        *)
            log_error "Unknown argument: $1"
            exit 1
            ;;
    esac
done

# Initialize log file
mkdir -p "$(dirname "$LOG_FILE")"
echo "" > "$LOG_FILE"

# Load environment
if [[ -z "$ENV_FILE" ]]; then
    ENV_FILE="$("$ROOT_DIR/scripts/use_env.sh" "$TARGET" 2>/dev/null || echo "")"
fi

if [[ -n "$ENV_FILE" && -f "$ENV_FILE" ]]; then
    log_info "Loading env from $ENV_FILE"
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

# Set URLs from env or defaults
AGENT_BASE_URL="${AGENT_BASE_URL:-http://localhost:${AGENT_API_PORT:-8000}}"
AUTH_BASE_URL="${AUTH_BASE_URL:-http://localhost:${AUTH_SERVICE_PORT:-5001}}"

# Credentials
SMOKE_USER_EMAIL="${SMOKE_USER_EMAIL:-${PROD_DEMO_EMAIL:-}}"
SMOKE_USER_PASSWORD="${SMOKE_USER_PASSWORD:-${PROD_DEMO_PASSWORD:-}}"

if [[ -z "$SMOKE_USER_EMAIL" || -z "$SMOKE_USER_PASSWORD" ]]; then
    log_error "Missing credentials. Set SMOKE_USER_EMAIL and SMOKE_USER_PASSWORD"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

ACCESS_TOKEN=""
START_TIME=$(date +%s)

# Login and get access token
login_user() {
    local payload resp status body
    payload=$(jq -n --arg login "$SMOKE_USER_EMAIL" --arg password "$SMOKE_USER_PASSWORD" \
        '{login:$login, password:$password}')
    
    resp=$(curl -s -w "\n%{http_code}" -X POST "${AUTH_BASE_URL%/}/v1/auth/login" \
        -H 'Content-Type: application/json' -d "$payload")
    status=$(echo "$resp" | tail -n1)
    body=$(echo "$resp" | head -n-1)
    
    if [[ "$status" != "200" ]]; then
        log_error "Login failed (status=$status): $body"
        exit 1
    fi
    
    ACCESS_TOKEN=$(echo "$body" | jq -r '.access_token // empty')
    if [[ -z "$ACCESS_TOKEN" ]]; then
        log_error "No access_token in login response"
        exit 1
    fi
    log_ok "Logged in as $SMOKE_USER_EMAIL"
}

# Fetch list of countries with documents
fetch_countries() {
    local query_params="?exclude_regions=true"
    if [[ -n "$ACCESS_SCOPE" ]]; then
        query_params="${query_params}&access_scope=${ACCESS_SCOPE}"
    fi
    
    local url="${AGENT_BASE_URL%/}/v1/documents/countries${query_params}"
    log_info "Fetching countries from: $url"
    
    local resp status body
    resp=$(curl -s -w "\n%{http_code}" \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        "$url")
    status=$(echo "$resp" | tail -n1)
    body=$(echo "$resp" | head -n-1)
    
    if [[ "$status" != "200" ]]; then
        log_error "Failed to fetch countries (status=$status): $body"
        exit 1
    fi
    
    COUNTRIES=$(echo "$body" | jq -r '.countries[]')
    COUNTRY_COUNT=$(echo "$body" | jq -r '.count')
    
    if [[ -z "$COUNTRIES" || "$COUNTRY_COUNT" == "0" ]]; then
        log_warn "No countries found with documents (scope: $ACCESS_SCOPE)"
        exit 0
    fi
    
    log_ok "Found $COUNTRY_COUNT countries with documents"
}

# Generate report for a single country (targeting next month)
generate_report() {
    local country_code="$1"
    local query_params="?target_month=${NEXT_MONTH}&skip_cache=true"
    local output_file="${OUTPUT_DIR}/${country_code}_Housing_Report_${NEXT_MONTH}.pdf"
    local url="${AGENT_BASE_URL%/}/v1/reports/housing/${country_code}${query_params}"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would generate: $country_code for month $NEXT_MONTH"
        return 0
    fi
    
    log_info "Generating report for $country_code (target: $NEXT_MONTH)..."
    
    local http_code
    http_code=$(curl -s -w "%{http_code}" -o "$output_file" \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        --max-time 600 \
        "$url")
    
    if [[ "$http_code" == "200" ]]; then
        local size
        size=$(stat -c%s "$output_file" 2>/dev/null || stat -f%z "$output_file" 2>/dev/null || echo "unknown")
        log_ok "Generated $country_code -> $output_file ($size bytes)"
        return 0
    else
        log_error "Failed to generate report for $country_code (HTTP $http_code)"
        if file "$output_file" 2>/dev/null | grep -q text; then
            cat "$output_file" >> "$LOG_FILE"
        fi
        rm -f "$output_file"
        return 1
    fi
}

# Send notification email
send_notification() {
    local subject="$1"
    local body="$2"
    
    if [[ -z "$NOTIFY_EMAIL" ]]; then
        return
    fi
    
    if ! command -v mail >/dev/null 2>&1; then
        log_warn "mail command not available, skipping notification"
        return
    fi
    
    echo "$body" | mail -s "$subject" "$NOTIFY_EMAIL" || log_warn "Failed to send notification email"
}

# Main execution
log_info "=============================================="
log_info "Housing Report Pre-Generation Job"
log_info "=============================================="
log_info "Run ID: $RUN_ID"
log_info "Target environment: $TARGET"
log_info "Target month: $NEXT_MONTH (next month)"
log_info "Agent API: $AGENT_BASE_URL"
log_info "Output directory: $OUTPUT_DIR"
log_info "Log file: $LOG_FILE"
log_info "Access scope filter: $ACCESS_SCOPE"
[[ -n "$LIMIT" ]] && log_info "Limit: $LIMIT countries"
[[ -n "$NOTIFY_EMAIL" ]] && log_info "Notification email: $NOTIFY_EMAIL"
[[ "$DRY_RUN" == "true" ]] && log_warn "DRY RUN MODE - no reports will be generated"
log_info "=============================================="

# Login
login_user

# Fetch available countries
fetch_countries

# Process each country sequentially
SUCCEEDED=0
FAILED=0
PROCESSED=0
FAILED_CODES=()

while IFS= read -r code; do
    if [[ -z "$code" ]]; then
        continue
    fi
    
    if [[ -n "$LIMIT" && $PROCESSED -ge $LIMIT ]]; then
        log_info "Reached limit of $LIMIT countries"
        break
    fi
    
    ((PROCESSED++))
    log_info "[$PROCESSED/$COUNTRY_COUNT] Processing $code..."
    
    if generate_report "$code"; then
        ((SUCCEEDED++))
    else
        ((FAILED++))
        FAILED_CODES+=("$code")
    fi
    
    # Delay between requests
    if [[ "$DRY_RUN" != "true" ]]; then
        sleep 5
    fi
done <<< "$COUNTRIES"

# Calculate duration
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
DURATION_MINS=$((DURATION / 60))
DURATION_SECS=$((DURATION % 60))

# Summary
log_info "=============================================="
log_info "JOB COMPLETE"
log_info "=============================================="
log_info "Duration: ${DURATION_MINS}m ${DURATION_SECS}s"
log_info "Target month: $NEXT_MONTH"
log_info "Processed: $PROCESSED / $COUNTRY_COUNT"
log_ok "Succeeded: $SUCCEEDED"

if [[ $FAILED -gt 0 ]]; then
    log_error "Failed: $FAILED (${FAILED_CODES[*]})"
    
    # Send failure notification
    send_notification \
        "[ALERT] Report Pre-Generation Failed - $NEXT_MONTH" \
        "Report pre-generation job completed with failures.

Run ID: $RUN_ID
Target Month: $NEXT_MONTH
Duration: ${DURATION_MINS}m ${DURATION_SECS}s

Results:
- Processed: $PROCESSED / $COUNTRY_COUNT
- Succeeded: $SUCCEEDED
- Failed: $FAILED

Failed countries: ${FAILED_CODES[*]}

Log file: $LOG_FILE"
    
    exit 1
else
    log_ok "All reports pre-generated successfully for $NEXT_MONTH!"
    
    # Send success notification
    send_notification \
        "[OK] Report Pre-Generation Complete - $NEXT_MONTH" \
        "Report pre-generation job completed successfully.

Run ID: $RUN_ID
Target Month: $NEXT_MONTH
Duration: ${DURATION_MINS}m ${DURATION_SECS}s

Results:
- Processed: $PROCESSED / $COUNTRY_COUNT
- Succeeded: $SUCCEEDED

All reports are now cached and ready for $NEXT_MONTH."
fi

log_info "Log file saved to: $LOG_FILE"


