#!/usr/bin/env bash
set -uo pipefail

origin=${ORIGIN:-"https://frontend.example"}
access_headers=${ACCESS_HEADERS:-"Authorization,Content-Type"}

print_headers() {
  awk 'BEGIN{IGNORECASE=1} /^HTTP/ || tolower($1) ~ /^access-control-allow/' || true
}

probe() {
  local name=$1
  local url=$2
  echo "\n=== ${name} :: ${url} ==="

  echo "-- Preflight (OPTIONS) --"
  (curl -isk -X OPTIONS "$url" \
    -H "Origin: ${origin}" \
    -H "Access-Control-Request-Method: GET" \
    -H "Access-Control-Request-Headers: ${access_headers}" \
    || true) | print_headers

  echo "-- Actual (GET) --"
  (curl -isk "$url" -H "Origin: ${origin}" || true) | print_headers
}

probe "Local agent-api" "${LOCAL_AGENT_API_URL:-http://localhost:8000/health}"
probe "Local auth-service" "${LOCAL_AUTH_URL:-http://localhost:5001/health}"
probe "AWS agent-api" "${AGENT_BASE_URL:-http://52.207.140.87:8000}/health"
probe "AWS auth-service" "${AUTH_BASE_URL:-http://52.207.140.87:5001}/health"
