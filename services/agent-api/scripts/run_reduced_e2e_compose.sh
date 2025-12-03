#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SERVICE_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=$(cd "$SERVICE_DIR/../.." && pwd)
ENV_FILE="$REPO_ROOT/.env"
ENV_EXAMPLE="$REPO_ROOT/env.example"
LOG_DIR="$SERVICE_DIR/logs/task_04"
LOG_FILE="$LOG_DIR/codex.log"
mkdir -p "$LOG_DIR"
touch "$LOG_FILE"

# Mirror script output into Codex log file while preserving console streaming.
if [[ -t 1 ]]; then
  exec > >(tee -a "$LOG_FILE") 2>&1
else
  exec >>"$LOG_FILE" 2>&1
fi

info() {
  printf '%s %s\n' "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')]" "$*"
}

warn() {
  printf '%s %s\n' "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')]" "WARN: $*" >&2
}

fail() {
  local message=$1
  local code=${2:-1}
  printf '%s %s\n' "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')]" "ERROR: ${message}" >&2
  exit "$code"
}

ensure_env_file() {
  if [[ ! -f "$ENV_EXAMPLE" ]]; then
    fail "Missing template: $ENV_EXAMPLE"
  fi

  if [[ ! -f "$ENV_FILE" ]]; then
    info "No .env detected — copying env.example"
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    return
  fi

  if [[ "${FORCE_ENV_COPY:-0}" == "1" ]]; then
    warn "FORCE_ENV_COPY=1 set — overwriting existing .env with env.example"
    cp "$ENV_EXAMPLE" "$ENV_FILE"
  else
    info "Using existing $ENV_FILE (set FORCE_ENV_COPY=1 to refresh)"
  fi
}

load_env_files() {
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  if [[ -f "$REPO_ROOT/.env.local" ]]; then
    # shellcheck disable=SC1090
    source "$REPO_ROOT/.env.local"
  fi
  set +a
}

STACK_STARTED=0
COMPOSE_PROFILE="reduced"
SERVICES=(postgres db-init agent-api auth-service user-service localstack)
MAX_HEALTH_ATTEMPTS=${MAX_HEALTH_ATTEMPTS:-40}
HEALTH_SLEEP_SECONDS=${HEALTH_SLEEP_SECONDS:-5}
HEALTH_TIMEOUT_SECONDS=${HEALTH_TIMEOUT_SECONDS:-5}
CLI_REPORT_PATH=${CLI_REPORT_PATH:-/app/logs/reduced_e2e_smoke.json}
CLI_PYTHONPATH=${CLI_PYTHONPATH:-/app/services/agent-api:/app/services/agent-api/src}

ensure_env_file
load_env_files

STACK_PROFILE_VALUE=${STACK_PROFILE:-reduced}
COMPOSE_PROFILES_VALUE=${COMPOSE_PROFILES:-reduced}
if [[ "$COMPOSE_PROFILES_VALUE" != *reduced* ]]; then
  COMPOSE_PROFILES_VALUE="reduced,${COMPOSE_PROFILES_VALUE}"
fi
if [[ "$COMPOSE_PROFILES_VALUE" != *aws-mock* ]]; then
  COMPOSE_PROFILES_VALUE="${COMPOSE_PROFILES_VALUE},aws-mock"
fi
export STACK_PROFILE="$STACK_PROFILE_VALUE"
export COMPOSE_PROFILES="$COMPOSE_PROFILES_VALUE"
export USE_LOCALSTACK="${USE_LOCALSTACK:-1}"

compose() {
  (cd "$REPO_ROOT" && STACK_PROFILE="$STACK_PROFILE_VALUE" COMPOSE_PROFILES="$COMPOSE_PROFILES_VALUE" docker compose --profile "$COMPOSE_PROFILE" "$@")
}

cleanup() {
  exit_code=$?
  if [[ $STACK_STARTED -eq 1 ]]; then
    if [[ "${KEEP_STACK:-0}" == "1" ]]; then
      warn "KEEP_STACK=1 — leaving reduced stack running"
    else
      info "Tearing down reduced stack"
      set +e
      compose down
      local down_status=$?
      set -e
      if [[ $down_status -ne 0 ]]; then
        warn "docker compose down failed"
      fi
    fi
  fi
  exit "$exit_code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

wait_for_http() {
  local name=$1
  local url=$2
  local attempt=1
  while (( attempt <= MAX_HEALTH_ATTEMPTS )); do
    if curl --fail --silent --show-error --max-time "$HEALTH_TIMEOUT_SECONDS" "$url" >/dev/null; then
      info "${name} healthy (${url})"
      return 0
    fi

    info "Waiting for ${name} (attempt ${attempt}/${MAX_HEALTH_ATTEMPTS})"
    sleep "$HEALTH_SLEEP_SECONDS"
    attempt=$((attempt + 1))
  done

  fail "Timed out waiting for ${name} (${url})"
}

wait_for_stack() {
  local agent_port=${AGENT_API_PORT:-8000}
  local auth_port=${AUTH_SERVICE_PORT:-5001}
  local user_port=${USER_SERVICE_PORT:-5002}
  local localstack_port=${LOCALSTACK_EDGE_PORT:-4566}
  declare -a targets=(
    "Agent API /health|http://localhost:${agent_port}/health"
    "Agent API /v1/health|http://localhost:${agent_port}/v1/health"
    "Auth Service|http://localhost:${auth_port}/v1/health"
    "User Service|http://localhost:${user_port}/v1/health"
    "LocalStack|http://localhost:${localstack_port}/_localstack/health"
  )

  local entry name url
  for entry in "${targets[@]}"; do
    IFS='|' read -r name url <<<"$entry"
    wait_for_http "$name" "$url"
  done
}

start_stack() {
  info "Starting reduced compose stack (${SERVICES[*]})"
  compose up --build -d "${SERVICES[@]}"
  STACK_STARTED=1
}

run_cli() {
  info "Running reduced E2E smoke CLI inside agent-api container"
  local tty_flag=()
  if [[ -n "${CI:-}" ]]; then
    tty_flag=(-T)
  fi

  local cli_args=(uv run python scripts/run_reduced_e2e_smoke.py --output "$CLI_REPORT_PATH")
  if [[ $# -gt 0 ]]; then
    cli_args+=("$@")
  fi

  set +e
  compose exec "${tty_flag[@]}" agent-api env "PYTHONPATH=${CLI_PYTHONPATH}" "${cli_args[@]}"
  local cli_exit=$?
  set -e
  return "$cli_exit"
}

main() {
  start_stack
  wait_for_stack
  run_cli "$@"
  local status=$?
  if [[ $status -ne 0 ]]; then
    fail "Reduced E2E smoke CLI reported failures" "$status"
  fi
}

main "$@"
