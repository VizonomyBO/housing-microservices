#!/usr/bin/env bash
set -euo pipefail

# Deploy the ingestion-first prod stack (agent-api, ingestion-service, auth-service,
# user-service, Postgres) and run the production smoke (ingestion -> activation ->
# attachment -> chat) against the specified PDF.

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

DEFAULT_ENV_FILE="$ROOT_DIR/.env.prod"
DEFAULT_SSH_KEY="${SSH_KEY:-$ROOT_DIR/ArchaaS/dist/vizonomy-v2-ec2-dev2.pem}"
DEFAULT_REMOTE_DIR="/opt/housing-microservices"
DEFAULT_REMOTE_ENV=".env.prod"
DEFAULT_REMOTE_COMPOSE="docker-compose.ec2.yml"
DEFAULT_SMOKE_FILE="$ROOT_DIR/services/agent-api/evals/data/MEX_2016_Mexico Financial Sector Assessment Program Housing Finance.pdf"
DEFAULT_LOG_FILE="/tmp/prod_deploy_and_smoke_$(date +%s).log"
DEFAULT_OUTPUT_FILE="$ROOT_DIR/prod_sample_run.json"

ENV_FILE=""
HOST=""
SSH_USER="${SSH_USER:-ec2-user}"
SSH_PORT="${SSH_PORT:-22}"
SSH_KEY="$DEFAULT_SSH_KEY"
DEPLOY_MODE="services-only"
NO_BUILD=0
NO_SYNC=0
REMOTE_DIR="$DEFAULT_REMOTE_DIR"
REMOTE_ENV_FILE="$DEFAULT_REMOTE_ENV"
REMOTE_COMPOSE_FILE="$DEFAULT_REMOTE_COMPOSE"
SKIP_DEPLOY=0
SKIP_SMOKE=0
SMOKE_FILE="$DEFAULT_SMOKE_FILE"
LOG_FILE="$DEFAULT_LOG_FILE"
OUTPUT_FILE="$DEFAULT_OUTPUT_FILE"

log() { echo "[prod_deploy_and_smoke] $*" >&2; }
die() { log "ERROR: $*"; exit 1; }

usage() {
  cat <<'EOF'
Usage: scripts/prod_deploy_and_smoke.sh [options]

Deploys the prod stack (agent-api, ingestion-service, auth-service, user-service, Postgres) on EC2
and runs the ingestion->activation->attachment->chat smoke using the FastAPI ingestion path.

Options:
  --env-file PATH       Env file to source/ship (default: .env.prod or use_env.sh prod).
  --host HOST           Override remote host/IP (defaults to POSTGRES_HOST from env file).
  --ssh-key PATH        SSH key path (default: ArchaaS/dist/vizonomy-v2-ec2-dev2.pem).
  --ssh-user USER       SSH user (default: ec2-user).
  --ssh-port PORT       SSH port (default: 22).
  --deploy-mode MODE    full-redeploy | services-only | skip (default: services-only).
  --no-build            Skip docker compose rebuild (reuse images).
  --no-sync             Skip code/env sync (use existing remote checkout).
  --remote-dir PATH     Remote checkout directory (default: /opt/housing-microservices).
  --remote-env FILE     Remote env filename (default: .env.prod).
  --remote-compose FILE Remote compose filename (default: docker-compose.ec2.yml).
  --smoke-file PATH     PDF/TXT/etc. to ingest for smoke (default: provided FSAP PDF).
  --skip-smoke          Deploy only; do not run smoke.
  --log-file PATH       Path for combined deploy+smoke log (default: /tmp/prod_deploy_and_smoke_<ts>.log).
  --output-file PATH    Path for prod smoke JSON output (default: prod_sample_run.json).
  -h, --help            Show this help.

Examples:
  scripts/prod_deploy_and_smoke.sh
  scripts/prod_deploy_and_smoke.sh --deploy-mode services-only --no-build --host 52.207.140.87
  scripts/prod_deploy_and_smoke.sh --skip-smoke --deploy-mode full-redeploy
EOF
}

read_env_value() {
  local file="$1" key="$2" default="${3:-}"
  python3 - "$file" "$key" "$default" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
default = sys.argv[3]
if not path.exists():
    print(default)
    sys.exit(0)

values = {}
for line in path.read_text().splitlines():
    if not line or line.lstrip().startswith("#") or "=" not in line:
        continue
    name, value = line.split("=", 1)
    values[name.strip()] = value.strip().strip('"').strip("'")

print(values.get(key, default))
PY
}

ssh_opts() {
  local opts=(-o "StrictHostKeyChecking=no" -p "$SSH_PORT")
  [[ -n "$SSH_KEY" ]] && opts+=(-i "$SSH_KEY")
  echo "${opts[@]}"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --env-file) ENV_FILE="$2"; shift 2 ;;
      --host) HOST="$2"; shift 2 ;;
      --ssh-key) SSH_KEY="$2"; shift 2 ;;
      --ssh-user) SSH_USER="$2"; shift 2 ;;
      --ssh-port) SSH_PORT="$2"; shift 2 ;;
      --deploy-mode) DEPLOY_MODE="$2"; shift 2 ;;
      --no-build) NO_BUILD=1; shift ;;
      --no-sync) NO_SYNC=1; shift ;;
      --remote-dir) REMOTE_DIR="$2"; shift 2 ;;
      --remote-env) REMOTE_ENV_FILE="$2"; shift 2 ;;
      --remote-compose) REMOTE_COMPOSE_FILE="$2"; shift 2 ;;
      --smoke-file) SMOKE_FILE="$2"; shift 2 ;;
      --skip-smoke) SKIP_SMOKE=1; shift ;;
      --log-file) LOG_FILE="$2"; shift 2 ;;
      --output-file) OUTPUT_FILE="$2"; shift 2 ;;
      -h|--help) usage; exit 0 ;;
      *) die "Unknown argument: $1" ;;
    esac
  done
}

resolve_env_file() {
  if [[ -z "$ENV_FILE" ]]; then
    if command -v scripts/use_env.sh >/dev/null 2>&1; then
      ENV_FILE=$(scripts/use_env.sh prod)
    else
      ENV_FILE="$DEFAULT_ENV_FILE"
    fi
  fi
  [[ -f "$ENV_FILE" ]] || die "Env file $ENV_FILE not found"
}

resolve_host() {
  [[ -n "$HOST" ]] && return
  HOST=$(read_env_value "$ENV_FILE" POSTGRES_HOST "")
  [[ -n "$HOST" ]] || die "Unable to resolve remote host; set POSTGRES_HOST in env or pass --host"
}

ensure_key() {
  [[ -f "$SSH_KEY" ]] || die "SSH key $SSH_KEY not found"
}

deploy_stack() {
  [[ "$DEPLOY_MODE" == "skip" ]] && { log "Skipping deploy (--deploy-mode skip)"; return; }
  case "$DEPLOY_MODE" in
    services-only|full-redeploy) ;;
    *) die "Invalid --deploy-mode: $DEPLOY_MODE (expected services-only|full-redeploy|skip)" ;;
  esac

  local args=(--mode "$DEPLOY_MODE" --env-file "$ENV_FILE" --host "$HOST" --remote-dir "$REMOTE_DIR" --remote-env "$REMOTE_ENV_FILE" --remote-compose "$REMOTE_COMPOSE_FILE" --ssh-user "$SSH_USER" --ssh-port "$SSH_PORT")
  [[ -n "$SSH_KEY" ]] && args+=(--ssh-key "$SSH_KEY")
  [[ "$NO_BUILD" -eq 1 ]] && args+=(--no-build)
  [[ "$NO_SYNC" -eq 1 ]] && args+=(--no-sync)

  log "Running deploy_stack.sh ${args[*]}"
  ENV_FILE="$ENV_FILE" scripts/deploy_stack.sh "${args[@]}"
}

health_checks() {
  [[ "$DEPLOY_MODE" == "skip" ]] && { log "Skipping health checks (deploy skipped)"; return; }
  log "Running remote health checks on $HOST"
  ssh $(ssh_opts) "$SSH_USER@$HOST" bash -s <<'EOF'
set -euo pipefail
curl -fsS http://localhost:5001/health >/dev/null
curl -fsS http://localhost:5001/v1/health >/dev/null || true  # some builds expose v1/health
curl -fsS http://localhost:5002/v1/health >/dev/null
curl -fsS http://localhost:8000/health >/dev/null
curl -fsS http://localhost:8085/health >/dev/null
echo "all healthy"
EOF
}

run_smoke() {
  [[ "$SKIP_SMOKE" -eq 1 ]] && { log "Skipping smoke (--skip-smoke)"; return; }
  [[ -f "$SMOKE_FILE" ]] || die "Smoke upload file $SMOKE_FILE not found"
  log "Starting prod smoke with upload $SMOKE_FILE"
  log "Writing combined log to $LOG_FILE and output JSON to $OUTPUT_FILE"
  TARGET=prod \
  ENV_FILE="$ENV_FILE" \
  SMOKE_UPLOAD_FILE="$SMOKE_FILE" \
  SMOKE_OUTPUT="$OUTPUT_FILE" \
    ./scripts/local_smoke.sh --target prod --env-file "$ENV_FILE" --upload-file "$SMOKE_FILE" --smoke-output "$OUTPUT_FILE" 2>&1 | tee "$LOG_FILE"
}

main() {
  parse_args "$@"
  resolve_env_file
  resolve_host
  ensure_key

  log "Env file: $ENV_FILE"
  log "Host: $HOST"
  log "SSH key: $SSH_KEY"
  log "Deploy mode: $DEPLOY_MODE (no-build=$NO_BUILD no-sync=$NO_SYNC)"
  log "Remote dir/env/compose: $REMOTE_DIR / $REMOTE_ENV_FILE / $REMOTE_COMPOSE_FILE"
  log "Smoke file: $SMOKE_FILE (skip_smoke=$SKIP_SMOKE)"

  deploy_stack
  health_checks
  run_smoke
}

main "$@"
