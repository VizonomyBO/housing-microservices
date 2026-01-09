#!/usr/bin/env bash
# ==============================================================================
# generate_reports_all.sh
# ==============================================================================
# Generate housing assessment PDF reports for ALL countries.
# Uses the complete ISO 3166-1 alpha-3 code list, allowing report generation
# even for countries without direct documents (regional/global docs provide content).
#
# Usage:
#   ./scripts/generate_reports_all.sh
#   ./scripts/generate_reports_all.sh --target-month 2026-02
#   ./scripts/generate_reports_all.sh --only-with-docs
#
# Options:
#   --target-month    Target month in YYYY-MM format for caching (optional)
#   --skip-cache      Force regeneration even if cached (optional)
#   --only-with-docs  Only process countries that have documents in DB (optional)
#   --output-dir      Directory to save downloaded PDFs (optional, default: ./reports)
#   --env-file        Path to env file (optional, uses scripts/use_env.sh)
#   --target          Target environment: local|dev|prod (default: local)
#   --dry-run         Print what would be done without executing
#   --limit           Max number of countries to process (optional)
#   --start-from      Start from a specific country code (optional, for resuming)
#
# Environment Variables:
#   AGENT_BASE_URL   Agent API base URL (auto-detected from env)
#   AUTH_BASE_URL    Auth service URL for login
#   SMOKE_USER_EMAIL / SMOKE_USER_PASSWORD  Credentials for API access
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()  { echo -e "${BLUE}[INFO]${NC} $*" >&2; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $*" >&2; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*" >&2; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ==============================================================================
# ISO 3166-1 alpha-3 country codes
# Source: https://raw.githubusercontent.com/lukes/ISO-3166-Countries-with-Regional-Codes/master/all/all.json
# This allows generating reports for any country, even without direct documents,
# since regional (LAC, ECA, AFR, etc.) and global (GLO) documents provide content.
# ==============================================================================
ISO_ALPHA3_CODES=(
    "ABW" "AFG" "AGO" "AIA" "ALA" "ALB" "AND" "ARE" "ARG" "ARM"
    "ASM" "ATA" "ATF" "ATG" "AUS" "AUT" "AZE" "BDI" "BEL" "BEN"
    "BES" "BFA" "BGD" "BGR" "BHR" "BHS" "BIH" "BLM" "BLR" "BLZ"
    "BMU" "BOL" "BRA" "BRB" "BRN" "BTN" "BVT" "BWA" "CAF" "CAN"
    "CCK" "CHE" "CHL" "CHN" "CIV" "CMR" "COD" "COG" "COK" "COL"
    "COM" "CPV" "CRI" "CUB" "CUW" "CXR" "CYM" "CYP" "CZE" "DEU"
    "DJI" "DMA" "DNK" "DOM" "DZA" "ECU" "EGY" "ERI" "ESH" "ESP"
    "EST" "ETH" "FIN" "FJI" "FLK" "FRA" "FRO" "FSM" "GAB" "GBR"
    "GEO" "GGY" "GHA" "GIB" "GIN" "GLP" "GMB" "GNB" "GNQ" "GRC"
    "GRD" "GRL" "GTM" "GUF" "GUM" "GUY" "HKG" "HMD" "HND" "HRV"
    "HTI" "HUN" "IDN" "IMN" "IND" "IOT" "IRL" "IRN" "IRQ" "ISL"
    "ISR" "ITA" "JAM" "JEY" "JOR" "JPN" "KAZ" "KEN" "KGZ" "KHM"
    "KIR" "KNA" "KOR" "KWT" "LAO" "LBN" "LBR" "LBY" "LCA" "LIE"
    "LKA" "LSO" "LTU" "LUX" "LVA" "MAC" "MAF" "MAR" "MCO" "MDA"
    "MDG" "MDV" "MEX" "MHL" "MKD" "MLI" "MLT" "MMR" "MNE" "MNG"
    "MNP" "MOZ" "MRT" "MSR" "MTQ" "MUS" "MWI" "MYS" "MYT" "NAM"
    "NCL" "NER" "NFK" "NGA" "NIC" "NIU" "NLD" "NOR" "NPL" "NRU"
    "NZL" "OMN" "PAK" "PAN" "PCN" "PER" "PHL" "PLW" "PNG" "POL"
    "PRI" "PRK" "PRT" "PRY" "PSE" "PYF" "QAT" "REU" "ROU" "RUS"
    "RWA" "SAU" "SDN" "SEN" "SGP" "SGS" "SHN" "SJM" "SLB" "SLE"
    "SLV" "SMR" "SOM" "SPM" "SRB" "SSD" "STP" "SUR" "SVK" "SVN"
    "SWE" "SWZ" "SXM" "SYC" "SYR" "TCA" "TCD" "TGO" "THA" "TJK"
    "TKL" "TKM" "TLS" "TON" "TTO" "TUN" "TUR" "TUV" "TWN" "TZA"
    "UGA" "UKR" "UMI" "URY" "USA" "UZB" "VAT" "VCT" "VEN" "VGB"
    "VIR" "VNM" "VUT" "WLF" "WSM" "YEM" "ZAF" "ZMB" "ZWE"
)

# Defaults
TARGET_MONTH=""
SKIP_CACHE="false"
ONLY_WITH_DOCS="false"
OUTPUT_DIR="$ROOT_DIR/reports"
ENV_FILE=""
TARGET="local"
DRY_RUN="false"
LIMIT=""
START_FROM=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --target-month)
            TARGET_MONTH="$2"
            shift 2
            ;;
        --skip-cache)
            SKIP_CACHE="true"
            shift
            ;;
        --only-with-docs)
            ONLY_WITH_DOCS="true"
            shift
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
        --start-from)
            START_FROM="$2"
            shift 2
            ;;
        -h|--help)
            head -35 "$0" | tail -33
            exit 0
            ;;
        *)
            log_error "Unknown argument: $1"
            exit 1
            ;;
    esac
done

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

# Fetch list of countries with documents (only used with --only-with-docs)
fetch_countries_with_docs() {
    local query_params="?exclude_regions=true"
    
    local url="${AGENT_BASE_URL%/}/v1/documents/countries${query_params}"
    log_info "Fetching countries with documents from: $url"
    
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
    
    # Extract countries array into COUNTRIES_WITH_DOCS
    COUNTRIES_WITH_DOCS=$(echo "$body" | jq -r '.countries[]' 2>/dev/null || echo "")
    local count
    count=$(echo "$body" | jq -r '.count // 0')
    log_ok "Found $count countries with documents in DB"
}

# Generate report for a single country
generate_report() {
    local country_code="$1"
    local query_params=""
    local output_file
    
    # Build query parameters
    if [[ -n "$TARGET_MONTH" ]]; then
        query_params="?target_month=$TARGET_MONTH"
    fi
    if [[ "$SKIP_CACHE" == "true" ]]; then
        if [[ -n "$query_params" ]]; then
            query_params="${query_params}&skip_cache=true"
        else
            query_params="?skip_cache=true"
        fi
    fi
    
    local url="${AGENT_BASE_URL%/}/v1/reports/housing/${country_code}${query_params}"
    
    if [[ -n "$TARGET_MONTH" ]]; then
        output_file="${OUTPUT_DIR}/${country_code}_Housing_Report_${TARGET_MONTH}.pdf"
    else
        output_file="${OUTPUT_DIR}/${country_code}_Housing_Report_$(date +%Y-%m).pdf"
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would generate: $country_code -> $output_file"
        return 0
    fi
    
    log_info "Generating report for $country_code..."
    
    local http_code
    http_code=$(curl -s -w "%{http_code}" -o "$output_file" \
        --max-time 600 \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        "$url")
    
    if [[ "$http_code" == "200" ]]; then
        local size
        size=$(stat -c%s "$output_file" 2>/dev/null || stat -f%z "$output_file" 2>/dev/null || echo "unknown")
        log_ok "Generated $country_code -> $output_file ($size bytes)"
        return 0
    else
        log_error "Failed to generate report for $country_code (HTTP $http_code)"
        if file "$output_file" 2>/dev/null | grep -q text; then
            cat "$output_file" >&2
        fi
        rm -f "$output_file"
        return 1
    fi
}

# Main execution
log_info "=== Housing Report Generator (All Countries) ==="
log_info "Target: $TARGET"
log_info "Agent API: $AGENT_BASE_URL"
log_info "Output directory: $OUTPUT_DIR"
[[ -n "$TARGET_MONTH" ]] && log_info "Target month: $TARGET_MONTH"
[[ "$SKIP_CACHE" == "true" ]] && log_info "Skip cache: enabled"
[[ "$ONLY_WITH_DOCS" == "true" ]] && log_info "Mode: Only countries with documents"
[[ "$ONLY_WITH_DOCS" != "true" ]] && log_info "Mode: All ISO-3 countries (${#ISO_ALPHA3_CODES[@]} total)"
[[ -n "$LIMIT" ]] && log_info "Limit: $LIMIT countries"
[[ -n "$START_FROM" ]] && log_info "Starting from: $START_FROM"
[[ "$DRY_RUN" == "true" ]] && log_warn "DRY RUN MODE - no reports will be generated"

# Login
login_user

# Determine which countries to process
COUNTRIES_TO_PROCESS=()

if [[ "$ONLY_WITH_DOCS" == "true" ]]; then
    # Fetch from API
    fetch_countries_with_docs
    if [[ -n "$COUNTRIES_WITH_DOCS" ]]; then
        while IFS= read -r code; do
            [[ -n "$code" ]] && COUNTRIES_TO_PROCESS+=("$code")
        done <<< "$COUNTRIES_WITH_DOCS"
    fi
else
    # Use full ISO-3 list
    COUNTRIES_TO_PROCESS=("${ISO_ALPHA3_CODES[@]}")
fi

TOTAL_COUNT=${#COUNTRIES_TO_PROCESS[@]}

if [[ $TOTAL_COUNT -eq 0 ]]; then
    log_warn "No countries to process"
    exit 0
fi

log_info "Total countries to process: $TOTAL_COUNT"

# Process each country sequentially
SUCCEEDED=0
FAILED=0
SKIPPED=0
PROCESSED=0
FAILED_CODES=()
STARTED="false"

for code in "${COUNTRIES_TO_PROCESS[@]}"; do
    # Skip until we reach START_FROM
    if [[ -n "$START_FROM" && "$STARTED" == "false" ]]; then
        if [[ "$code" == "$START_FROM" ]]; then
            STARTED="true"
        else
            ((SKIPPED++))
            continue
        fi
    fi
    
    # Check limit
    if [[ -n "$LIMIT" && $PROCESSED -ge $LIMIT ]]; then
        log_info "Reached limit of $LIMIT countries"
        break
    fi
    
    ((PROCESSED++))
    log_info "[$PROCESSED/$TOTAL_COUNT] Processing $code..."
    
    if generate_report "$code"; then
        ((SUCCEEDED++))
    else
        ((FAILED++))
        FAILED_CODES+=("$code")
    fi
    
    # Small delay between requests to be nice to the API
    if [[ "$DRY_RUN" != "true" ]]; then
        sleep 2
    fi
done

# Summary
echo ""
log_info "=== Summary ==="
log_info "Total available: $TOTAL_COUNT"
[[ $SKIPPED -gt 0 ]] && log_info "Skipped (before start-from): $SKIPPED"
log_info "Processed: $PROCESSED"
log_ok "Succeeded: $SUCCEEDED"
if [[ $FAILED -gt 0 ]]; then
    log_error "Failed: $FAILED (${FAILED_CODES[*]})"
    exit 1
else
    log_ok "All reports generated successfully!"
fi
