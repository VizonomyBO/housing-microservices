#!/usr/bin/env bash
# Regenerate housing PDF reports for given country codes by calling the reports
# API with skip_cache=true. Logs in before each report using credentials from
# .env.prod (or ENV_FILE).
#
# Usage:
#   env_file=$(scripts/use_env.sh prod); set -a && source "$env_file" && set +a
#   ./scripts/regenerate_pdf_reports.sh [--no-validate] [--strict] ARG NGA MEX IDN PAK ZAF MOZ TUR
#
# Options:
#   --no-validate   Skip PDF validation (only checks HTTP status code).
#   --strict        Treat citation/length warnings as failures during validation.
#
# Countries must be passed as positional parameters (no default list).
#
# Requires: .env.prod (or ENV_FILE) with PROD_DEMO_EMAIL, PROD_DEMO_PASSWORD,
#   AUTH_BASE_URL, and REPORTS_BASE_URL (or EC2_HOST for default).
#
# PDF validation requires Python 3 with pymupdf installed:
#   pip install -r scripts/requirements-validate.txt

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

VALIDATE=true
STRICT_FLAG=""
COUNTRIES=()

for arg in "$@"; do
  case "$arg" in
    --no-validate) VALIDATE=false ;;
    --strict)      STRICT_FLAG="--strict" ;;
    *)             COUNTRIES+=("$arg") ;;
  esac
done

if [[ ${#COUNTRIES[@]} -eq 0 ]]; then
  echo "Usage: $0 [--no-validate] [--strict] COUNTRY_CODE [COUNTRY_CODE ...]" >&2
  echo "Example: $0 ARG NGA MEX IDN PAK ZAF MOZ TUR" >&2
  exit 1
fi

env_file="${ENV_FILE:-$ROOT_DIR/.env.prod}"
if [[ -f "$env_file" ]]; then
  set -a
  source "$env_file"
  set +a
fi

AUTH_LOGIN="${AUTH_LOGIN:-${PROD_DEMO_EMAIL:-}}"
AUTH_PASSWORD="${AUTH_PASSWORD:-${PROD_DEMO_PASSWORD:-}}"
AUTH_BASE_URL="${AUTH_BASE_URL:-http://52.207.140.87:5001}"
REPORTS_BASE_URL="${REPORTS_BASE_URL:-}"
if [[ -z "$REPORTS_BASE_URL" && -n "${EC2_HOST:-}" ]]; then
  REPORTS_BASE_URL="http://${EC2_HOST}"
fi
REPORTS_BASE_URL="${REPORTS_BASE_URL:-http://52.207.140.87}"

if [[ -z "$AUTH_LOGIN" || -z "$AUTH_PASSWORD" ]]; then
  echo "ERROR: AUTH_LOGIN/PROD_DEMO_EMAIL and AUTH_PASSWORD/PROD_DEMO_PASSWORD must be set (e.g. from .env.prod)." >&2
  exit 1
fi

require() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing required tool: $1" >&2; exit 1; }
}
require jq
require curl

VENV_PYTHON="$ROOT_DIR/.venv/bin/python"

if [[ "$VALIDATE" == "true" ]]; then
  VALIDATOR_SCRIPT="$SCRIPT_DIR/validate_pdf_report.py"
  if [[ ! -f "$VALIDATOR_SCRIPT" ]]; then
    echo "ERROR: Validator script not found at $VALIDATOR_SCRIPT" >&2
    exit 1
  fi
  if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "ERROR: venv python not found at $VENV_PYTHON. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.tooling.txt" >&2
    exit 1
  fi
  if ! "$VENV_PYTHON" -c "import fitz" 2>/dev/null; then
    echo "WARNING: pymupdf not in venv. Run: uv add pymupdf in services/agent-api" >&2
    echo "WARNING: Falling back to --no-validate mode." >&2
    VALIDATE=false
  fi
fi

TOKEN=""

get_token() {
  echo "Logging in as $AUTH_LOGIN..."
  local response
  response=$(curl -sS -X POST "${AUTH_BASE_URL%/}/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"login\":\"$AUTH_LOGIN\",\"password\":\"$AUTH_PASSWORD\"}" 2>&1)
  TOKEN=$(echo "$response" | jq -r '.access_token // empty')
  if [[ -z "$TOKEN" || "$TOKEN" == "null" ]]; then
    echo "ERROR: Login failed. Response: $response" >&2
    exit 1
  fi
  echo "Token obtained."
}

fetch_report_to_file() {
  local code="$1"
  local out_file="$2"
  local url="${REPORTS_BASE_URL%/}/api/chat/v1/reports/housing/${code}?skip_cache=true"
  local http_code
  http_code=$(curl -sS -o "$out_file" -w "%{http_code}" --request GET \
    --url "$url" \
    --header "Accept: */*" \
    --header "Authorization: Bearer $TOKEN")
  echo "$http_code"
}

validate_report() {
  local code="$1"
  local pdf_file="$2"
  local attempt="$3"
  echo "  [validate] attempt $attempt: running PDF validator on $pdf_file..."
  local validation_output exit_code
  validation_output=$("$VENV_PYTHON" "$VALIDATOR_SCRIPT" "$pdf_file" --country "$code" $STRICT_FLAG 2>&1) || exit_code=$?
  exit_code="${exit_code:-0}"

  echo "$validation_output" | "$VENV_PYTHON" -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print('  [validate] ' + data.get('summary', '(no summary)'))
    for s in data.get('sections', []):
        if s['status'] != 'passed':
            reasons = '; '.join(s.get('reasons', []))
            print(f\"  [validate]   SECTION {s['number']}. {s['title']}: {s['status'].upper()} — {reasons}\")
            if s.get('content_preview'):
                print(f\"  [validate]     preview: {s['content_preview'][:100]}\")
except Exception:
    print(sys.stdin.read())
" 2>/dev/null || echo "$validation_output"

  return "$exit_code"
}

regenerate_report() {
  local code="$1"
  local max_attempts=3
  local attempt
  local tmp_dir
  tmp_dir=$(mktemp -d)
  local last_output=""
  local last_output_ext="txt"
  local success=false

  for attempt in $(seq 1 "$max_attempts"); do
    echo "[$code] attempt $attempt/$max_attempts: fetching report..."
    get_token

    local pdf_file="$tmp_dir/${code}_attempt${attempt}.pdf"
    local http_code
    http_code=$(fetch_report_to_file "$code" "$pdf_file")
    last_output="$pdf_file"
    last_output_ext="txt"

    if [[ $http_code -lt 200 || $http_code -ge 300 ]]; then
      echo "  [$code] HTTP $http_code on attempt $attempt — skipping validation." >&2
      if [[ -s "$pdf_file" ]]; then
        local response_preview
        response_preview=$(head -c 400 "$pdf_file" | tr '\n' ' ')
        echo "  [$code] Response preview: $response_preview" >&2
      fi
      if [[ $attempt -lt $max_attempts ]]; then
        echo "  [$code] Retrying..."
        continue
      fi
      echo "  [$code] All $max_attempts attempts failed (HTTP errors)." >&2
      break
    fi

    echo "  [$code] HTTP $http_code OK, PDF downloaded ($(wc -c < "$pdf_file") bytes)."
    last_output_ext="pdf"

    if [[ "$VALIDATE" == "false" ]]; then
      echo "  [$code] Validation skipped (--no-validate)."
      success=true
      break
    fi

    if validate_report "$code" "$pdf_file" "$attempt"; then
      echo "  [$code] Validation passed on attempt $attempt."
      success=true
      break
    else
      echo "  [$code] Validation FAILED on attempt $attempt." >&2
      if [[ $attempt -lt $max_attempts ]]; then
        echo "  [$code] Retrying report generation..."
      fi
    fi
  done

  if [[ "$success" == "true" ]]; then
    rm -rf "$tmp_dir"
    return 0
  fi

  local keep_path="${ROOT_DIR}/${code}_failed_report.${last_output_ext}"
  if [[ -n "$last_output" && -f "$last_output" ]]; then
    cp "$last_output" "$keep_path"
    echo "  [$code] All $max_attempts attempts failed. Last response saved to: $keep_path" >&2
  else
    echo "  [$code] All $max_attempts attempts failed (no PDF produced)." >&2
  fi
  rm -rf "$tmp_dir"
  return 1
}

failed=0
for code in "${COUNTRIES[@]}"; do
  if ! regenerate_report "$code"; then
    ((failed++)) || true
  fi
done

if [[ $failed -gt 0 ]]; then
  echo "Done with $failed failure(s)." >&2
  exit 1
fi
echo "Done. All ${#COUNTRIES[@]} report(s) regenerated successfully."
