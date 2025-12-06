#!/usr/bin/env bash
set -euo pipefail

# Switch between AWS and LocalStack env files and emit a single active env
# (`.env.active`) that compose/scripts can source without manual edits.

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ACTIVE_ENV_FILE="$ROOT_DIR/.env.active"
MODE_FILE="$ROOT_DIR/.env.active.mode"
AWS_ENV_FILE=${AWS_ENV_FILE:-"$ROOT_DIR/.env.prod.aws"}
LOCAL_ENV_FILE=${LOCAL_ENV_FILE:-"$ROOT_DIR/.env.prod"}
TEMPLATE_ENV_FILE="$ROOT_DIR/env.example"

log() { echo "[use_env] $*" >&2; }

usage() {
  cat >&2 <<'EOF'
Usage: scripts/use_env.sh <aws|localstack|local|current>

Switches the active environment by copying the selected env file into
.env.active (and records the mode). Logs next steps to stderr and prints the
active env file path to stdout so callers can use command substitution:

  env_file=$(scripts/use_env.sh aws)
  set -a && source "$env_file" && set +a
  docker compose --env-file "$env_file" ...

Modes:
  aws         Use .env.prod.aws (or AWS_ENV_FILE override), force USE_LOCALSTACK=0.
  localstack  Use .env.prod (or LOCAL_ENV_FILE override), force USE_LOCALSTACK=1 and LocalStack defaults.
  local       Alias for localstack.
  current     Print the currently selected env file path if .env.active exists.
EOF
}

apply_overrides() {
  local file="$1"; shift
  if [[ $# -eq 0 ]]; then
    return
  fi
  python3 - "$file" "$@" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
pairs = sys.argv[2:]
overrides = dict(zip(pairs[::2], pairs[1::2]))
if not path.exists():
    sys.stderr.write(f"[use_env] ERROR: {path} missing while applying overrides.\n")
    sys.exit(1)

lines = path.read_text().splitlines()
updated = []
seen = set()
for line in lines:
    if line.strip().startswith("#") or "=" not in line:
        updated.append(line)
        continue
    key, _, _ = line.partition("=")
    if key in overrides:
        updated.append(f"{key}={overrides[key]}")
        seen.add(key)
    else:
        updated.append(line)

for key, value in overrides.items():
    if key not in seen:
        updated.append(f"{key}={value}")

path.write_text("\n".join(updated) + "\n")
PY
}

ensure_local_env() {
  if [[ -f "$LOCAL_ENV_FILE" ]]; then
    return
  fi
  if [[ ! -f "$TEMPLATE_ENV_FILE" ]]; then
    log "ERROR: Local env $LOCAL_ENV_FILE is missing and $TEMPLATE_ENV_FILE not found."
    exit 1
  fi
  log "Seeding $LOCAL_ENV_FILE from $TEMPLATE_ENV_FILE"
  cp "$TEMPLATE_ENV_FILE" "$LOCAL_ENV_FILE"
}

print_current() {
  if [[ -f "$ACTIVE_ENV_FILE" ]]; then
    cat "$ACTIVE_ENV_FILE"
  else
    log "No active env set (.env.active missing)."
    exit 1
  fi
}

warn_if_empty() {
  local key="$1"
  if [[ -z "${2:-}" ]]; then
    log "WARNING: $key is empty in $ACTIVE_ENV_FILE"
  fi
}

MODE=${1:-}
if [[ -z "$MODE" ]]; then
  usage
  exit 1
fi

case "$MODE" in
  -h|--help)
    usage
    exit 0
    ;;
  current)
    if [[ -f "$ACTIVE_ENV_FILE" ]]; then
      echo "$ACTIVE_ENV_FILE"
      exit 0
    else
      log "No active env set (.env.active missing)."
      exit 1
    fi
    ;;
  aws)
    if [[ ! -f "$AWS_ENV_FILE" ]]; then
      log "ERROR: AWS env file $AWS_ENV_FILE not found. Set AWS_ENV_FILE or create .env.prod.aws."
      exit 1
    fi
    cp "$AWS_ENV_FILE" "$ACTIVE_ENV_FILE"
    apply_overrides "$ACTIVE_ENV_FILE" \
      USE_LOCALSTACK 0 \
      AWS_ENDPOINT_URL ""
    echo "aws" >"$MODE_FILE"
    log "Activated AWS env from $AWS_ENV_FILE → $ACTIVE_ENV_FILE"
    ;;
  local|localstack)
    ensure_local_env
    cp "$LOCAL_ENV_FILE" "$ACTIVE_ENV_FILE"
    LOCAL_AUTH_DB_URL='postgresql://${POSTGRES_USER:-vizonomy_user}:${POSTGRES_PASSWORD:-change-me-in-local-dev}@postgres:5432/${AUTH_DB:-auth_db}'
    apply_overrides "$ACTIVE_ENV_FILE" \
      USE_LOCALSTACK 1 \
      AWS_ACCESS_KEY_ID localstack \
      AWS_SECRET_ACCESS_KEY localstack \
      AWS_ENDPOINT_URL http://localhost.localstack.cloud:4566 \
      AGENT_BASE_URL http://localhost:8000 \
      AUTH_BASE_URL http://localhost:5001 \
      POSTGRES_HOST postgres \
      AUTH_DATABASE_URL "$LOCAL_AUTH_DB_URL" \
      INGEST_BASE_URL http://localhost:8085 \
      INGEST_UPLOAD_API_KEY "" \
      RAW_DOCUMENTS_BUCKET vizonomy-raw-docs-dev \
      PROCESSED_BUCKET vizonomy-processed-dev
    echo "localstack" >"$MODE_FILE"
    log "Activated LocalStack env from $LOCAL_ENV_FILE → $ACTIVE_ENV_FILE"
    ;;
  *)
    usage
    exit 1
    ;;
esac

if [[ -f "$MODE_FILE" ]]; then
  log "Mode recorded in $MODE_FILE ($(cat "$MODE_FILE"))"
fi

if [[ -f "$ACTIVE_ENV_FILE" ]]; then
  # Surfacing a few key vars for quick sanity checks without forcing them.
  set +u
  source "$ACTIVE_ENV_FILE"
  warn_if_empty "AGENT_BASE_URL" "${AGENT_BASE_URL:-}"
  warn_if_empty "AUTH_BASE_URL" "${AUTH_BASE_URL:-}"
  warn_if_empty "DATABASE_URL" "${DATABASE_URL:-}"
  warn_if_empty "AUTH_DATABASE_URL" "${AUTH_DATABASE_URL:-}"
  warn_if_empty "INGEST_BASE_URL" "${INGEST_BASE_URL:-}"
  set -u
fi

log "Next: set -a && source \"$ACTIVE_ENV_FILE\" && set +a"
log "Compose example: docker compose --env-file \"$ACTIVE_ENV_FILE\" -f docker-compose.yml -f docker-compose.prod.override.yml up -d --build"

# Print the active env path to stdout for command substitution.
echo "$ACTIVE_ENV_FILE"
