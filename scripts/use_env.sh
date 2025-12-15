#!/usr/bin/env bash
set -euo pipefail

# Lightweight env selector. Prints the path to the requested env file without
# copying or mutating files. Supported modes map to the canonical envs:
# - local:  .env.local      (LocalStack-first)
# - dev:    .env.dev        (services locally, cloud data plane)
# - prod:   .env.prod       (AWS/EC2 deployment)
# The caller can then: `env_file=$(scripts/use_env.sh prod); set -a && source "$env_file" && set +a`

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
LOCAL_ENV_FILE=${LOCAL_ENV_FILE:-"$ROOT_DIR/.env.local"}
DEV_ENV_FILE=${DEV_ENV_FILE:-"$ROOT_DIR/.env.dev"}
PROD_ENV_FILE=${PROD_ENV_FILE:-"$ROOT_DIR/.env.prod"}
TEMPLATE_ENV_FILE="$ROOT_DIR/env.example"

log() { echo "[use_env] $*" >&2; }
die() { log "ERROR: $*"; exit 1; }

usage() {
  cat >&2 <<'EOF'
Usage: scripts/use_env.sh <local|dev|prod|current>

Returns the path to the selected env file (does not create .env.active).
Example:
  env_file=$(scripts/use_env.sh prod)
  set -a && source "$env_file" && set +a
  docker compose --env-file "$env_file" up -d

Modes:
  local      Use .env.local (seeds from env.example if missing).
  dev        Use .env.dev (cloud data plane with local services).
  prod       Use .env.prod (AWS).
  current    Print ENV_FILE if set, else default to .env.local.
EOF
}

ensure_local_env() {
  if [[ -f "$LOCAL_ENV_FILE" ]]; then
    return
  fi
  if [[ -f "$TEMPLATE_ENV_FILE" ]]; then
    cp "$TEMPLATE_ENV_FILE" "$LOCAL_ENV_FILE"
    log "Seeded $LOCAL_ENV_FILE from $TEMPLATE_ENV_FILE (update secrets before use)."
  else
    die "Missing $LOCAL_ENV_FILE and no template $TEMPLATE_ENV_FILE to seed it."
  fi
}

select_env() {
  case "$1" in
    local)
      ensure_local_env
      echo "$LOCAL_ENV_FILE"
      ;;
    dev)
      [[ -f "$DEV_ENV_FILE" ]] || die "Dev env $DEV_ENV_FILE not found."
      echo "$DEV_ENV_FILE"
      ;;
    prod)
      [[ -f "$PROD_ENV_FILE" ]] || die "Prod env $PROD_ENV_FILE not found."
      echo "$PROD_ENV_FILE"
      ;;
    current)
      if [[ -n "${ENV_FILE:-}" ]]; then
        echo "$ENV_FILE"
      else
        ensure_local_env
        echo "$LOCAL_ENV_FILE"
      fi
      ;;
    -h|--help)
      usage
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

MODE=${1:-}
if [[ -z "$MODE" ]]; then
  usage
  exit 1
fi

select_env "$MODE"
