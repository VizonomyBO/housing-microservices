#!/usr/bin/env bash
# Regenerate chat response cache via SSH tunnel to EC2.
# Opens a tunnel so localhost:${TUNNEL_LOCAL_PORT} forwards to the DB on EC2,
# then runs the regeneration script with DATABASE_URL pointing at the tunnel.
#
# Usage (prod):
#   env_file=$(scripts/use_env.sh prod); set -a && source "$env_file" && set +a
#   ENV_FILE="$env_file" ./scripts/regenerate_country_cache_via_tunnel.sh BOL ARG MOZ TUR
#
# Or with default countries (BOL, ARG, MOZ, TUR):
#   ./scripts/regenerate_country_cache_via_tunnel.sh
#
# Requires in env: EC2_HOST (or POSTGRES_HOST), SSH_KEY (or terraform output / ~/.ssh/id_rsa),
#   DB_HOST_INTERNAL (DB hostname as seen from EC2, default 127.0.0.1),
#   POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
AGENT_API_DIR="$ROOT_DIR/services/agent-api"
TF_DIR="$ROOT_DIR/ArchaaS"
TUNNEL_LOCAL_PORT="${TUNNEL_LOCAL_PORT:-}"
SSH_USER="${SSH_USER:-ec2-user}"
SSH_PORT="${SSH_PORT:-22}"

require() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing required tool: $1" >&2; exit 1; }
}

require lsof
require ssh
require uv

pick_available_port() {
  local base=15432
  local max_tries=20
  for i in $(seq 0 $((max_tries - 1))); do
    local p=$((base + i))
    if ! lsof -Pi ":$p" -sTCP:LISTEN -t >/dev/null 2>&1; then
      echo "$p"
      return 0
    fi
  done
  echo "$base"
  return 1
}

# Load env (need EC2_HOST, SSH_KEY, DB vars, and OPENAI/VOYAGE for regeneration)
env_file="${ENV_FILE:-$ROOT_DIR/.env.prod}"
if [[ -f "$env_file" ]]; then
  set -a
  source "$env_file"
  set +a
fi

# Resolve EC2 host (for SSH)
EC2_HOST="${EC2_HOST:-${POSTGRES_HOST:-}}"
if [[ -z "$EC2_HOST" && -d "$TF_DIR" ]]; then
  EC2_HOST=$(terraform -chdir="$TF_DIR" output -raw ec2_public_ip 2>/dev/null || true)
fi
if [[ -z "$EC2_HOST" ]]; then
  echo "ERROR: EC2_HOST (or POSTGRES_HOST) not set and terraform output not available. Set in env or .env.prod." >&2
  exit 1
fi

# Resolve SSH key
SSH_KEY="${SSH_KEY:-}"
if [[ -z "$SSH_KEY" && -d "$TF_DIR" ]]; then
  tf_key=$(terraform -chdir="$TF_DIR" output -raw ec2_private_key_path 2>/dev/null || true)
  if [[ -n "$tf_key" ]]; then
    if [[ "$tf_key" == ./* ]]; then tf_key="$TF_DIR/${tf_key#./}"; elif [[ "$tf_key" != /* ]]; then tf_key="$TF_DIR/$tf_key"; fi
    [[ -f "$tf_key" ]] && SSH_KEY="$tf_key"
  fi
fi
[[ -z "$SSH_KEY" && -f "$HOME/.ssh/id_rsa" ]] && SSH_KEY="$HOME/.ssh/id_rsa"
# Fallback: key in ArchaaS/dist (terraform writes <project>-ec2-<env>.pem there)
if [[ -z "$SSH_KEY" && -d "$ROOT_DIR/ArchaaS/dist" ]]; then
  first_pem=$(find "$ROOT_DIR/ArchaaS/dist" -maxdepth 1 -name "*.pem" -type f 2>/dev/null | head -1)
  [[ -n "$first_pem" && -f "$first_pem" ]] && SSH_KEY="$first_pem"
fi
if [[ -z "$SSH_KEY" || ! -f "$SSH_KEY" ]]; then
  echo "ERROR: SSH_KEY not set or file not found. Set SSH_KEY or add a .pem key in ArchaaS/dist/ or ~/.ssh/id_rsa." >&2
  exit 1
fi

# DB as seen from the EC2 host running the SSH tunnel.
# In the current prod topology, Postgres is published on the host at 127.0.0.1:5432.
DB_HOST_INTERNAL="${DB_HOST_INTERNAL:-127.0.0.1}"
DB_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-vizonomy_user}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-housing}"

if [[ -z "$POSTGRES_PASSWORD" || "$POSTGRES_PASSWORD" == "CHANGE_ME" ]]; then
  echo "ERROR: POSTGRES_PASSWORD not set or placeholder. Set in env or .env.prod." >&2
  exit 1
fi

if [[ -z "$TUNNEL_LOCAL_PORT" ]]; then
  TUNNEL_LOCAL_PORT=$(pick_available_port)
  if [[ -z "$TUNNEL_LOCAL_PORT" ]]; then
    echo "ERROR: Could not find an available local port (tried 15432–15451)." >&2
    exit 1
  fi
fi

if [[ ! -d "$AGENT_API_DIR" ]]; then
  echo "ERROR: Agent API directory not found at $AGENT_API_DIR." >&2
  exit 1
fi

ssh_args=(
  -N
  -o StrictHostKeyChecking=no
  -o ServerAliveInterval=60
  -L "${TUNNEL_LOCAL_PORT}:${DB_HOST_INTERNAL}:${DB_PORT}"
  -i "$SSH_KEY"
)
if [[ -n "$SSH_PORT" ]]; then
  ssh_args+=(-p "$SSH_PORT")
fi

ssh "${ssh_args[@]}" "$SSH_USER@$EC2_HOST" &
SSH_PID=$!
cleanup() { kill "$SSH_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

sleep 2
if ! kill -0 "$SSH_PID" 2>/dev/null; then
  echo "ERROR: SSH tunnel failed to start. Check EC2_HOST, SSH_KEY, and network." >&2
  exit 1
fi

echo "Tunnel: localhost:${TUNNEL_LOCAL_PORT} -> ${EC2_HOST}:${DB_HOST_INTERNAL}:${DB_PORT}"
export DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:${TUNNEL_LOCAL_PORT}/${POSTGRES_DB}"
(
  cd "$AGENT_API_DIR"
  uv run python scripts/regenerate_country_cache.py "$@"
)
