#!/bin/bash

# Lightweight smoke script for the simplified stack (auth, user, ingestion, agent, LocalStack)
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_info() { echo -e "${YELLOW}ℹ $1${NC}"; }

AUTH_BASE_URL=${AUTH_BASE_URL:-http://localhost:5001}
USER_BASE_URL=${USER_BASE_URL:-http://localhost:5002}
AGENT_BASE_URL=${AGENT_BASE_URL:-http://localhost:8000}
INGEST_BASE_URL=${INGEST_BASE_URL:-http://localhost:8085}
LOCALSTACK_EDGE_PORT=${LOCALSTACK_EDGE_PORT:-4566}
USE_LOCALSTACK=${USE_LOCALSTACK:-1}

TEST_EMAIL="smoke_$(date +%s)@example.com"
TEST_USERNAME="smoke_user_$(date +%s)"
TEST_PASSWORD="TestPass123!"
TEST_FIRST_NAME="Smoke"
TEST_LAST_NAME="User"

call_endpoint() {
    local description=$1
    local method=$2
    local url=$3
    local data=${4:-}
    local expected=$5
    shift 5
    local headers=("$@")

    print_info "Testing: $description"

    local response
    if [ -z "$data" ]; then
        response=$(curl -s -w "\n%{http_code}" -X "$method" "$url" "${headers[@]}")
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" "$url" \
            -H "Content-Type: application/json" \
            "${headers[@]}" \
            -d "$data")
    fi

    local http_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | head -n-1)

    if [[ "$expected" == *",$http_code,"* ]]; then
        print_success "$description - Status: $http_code"
        echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
        echo ""
        return 0
    fi

    print_error "$description - Expected: ${expected//,/, } Got: $http_code"
    echo "$body"
    echo ""
    return 1
}

format_expected_list() {
    local expected=$1
    echo ",$expected,"  # wrap to simplify membership test
}

expected_200=$(format_expected_list "200")
expected_200_201=$(format_expected_list "200,201")
expected_200_201_409=$(format_expected_list "200,201,409")

print_info "Service health checks"
if [[ "$USE_LOCALSTACK" == "1" ]]; then
    call_endpoint "LocalStack health" "GET" "http://localhost:${LOCALSTACK_EDGE_PORT}/_localstack/health" "" "$expected_200"
fi
call_endpoint "Auth service health" "GET" "${AUTH_BASE_URL%/}/health" "" "$expected_200"
call_endpoint "User service health" "GET" "${USER_BASE_URL%/}/v1/health" "" "$expected_200"
call_endpoint "Ingestion service health" "GET" "${INGEST_BASE_URL%/}/health" "" "$expected_200"

if [[ -n "${OPENAI_API_KEY:-}" && -n "${VOYAGE_API_KEY:-}" ]]; then
    call_endpoint "Agent API health" "GET" "${AGENT_BASE_URL%/}/health" "" "$expected_200"
else
    print_info "Skipping agent-api health check (set OPENAI_API_KEY and VOYAGE_API_KEY to enable)."
fi

auth_payload=$(cat <<EOF_JSON
{
  "email": "$TEST_EMAIL",
  "username": "$TEST_USERNAME",
  "password": "$TEST_PASSWORD",
  "first_name": "$TEST_FIRST_NAME",
  "last_name": "$TEST_LAST_NAME",
  "country_code": "USA",
  "role": "public"
}
EOF_JSON
)
call_endpoint "Register user" "POST" "${AUTH_BASE_URL%/}/v1/auth/register" "$auth_payload" "$expected_200_201_409"

login_payload=$(cat <<EOF_JSON
{
  "login": "$TEST_EMAIL",
  "password": "$TEST_PASSWORD"
}
EOF_JSON
)
login_response=$(curl -s -w "\n%{http_code}" -X POST "${AUTH_BASE_URL%/}/v1/auth/login" \
  -H "Content-Type: application/json" -d "$login_payload")
login_code=$(echo "$login_response" | tail -n1)
login_body=$(echo "$login_response" | head -n-1)
if [[ "$login_code" != "200" ]]; then
    print_error "User login failed - Expected 200 Got: $login_code"
    echo "$login_body"
    exit 1
fi
print_success "User login - Status: $login_code"
access_token=$(echo "$login_body" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)
refresh_token=$(echo "$login_body" | python3 -c "import sys, json; print(json.load(sys.stdin).get('refresh_token',''))" 2>/dev/null || true)
if [[ -z "$access_token" ]]; then
    print_error "No access_token returned from login"
    echo "$login_body"
    exit 1
fi

call_endpoint "User profile" "GET" "${USER_BASE_URL%/}/v1/users/me" "" "$expected_200" -H "Authorization: Bearer $access_token"

print_success "Smoke checks complete"
print_info "Created user: $TEST_EMAIL / $TEST_USERNAME"
print_info "Access token (truncated): ${access_token:0:8}..."
if [[ -n "$refresh_token" ]]; then
  print_info "Refresh token (truncated): ${refresh_token:0:8}..."
fi
