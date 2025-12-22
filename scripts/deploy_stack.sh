#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
TF_DIR="$ROOT_DIR/ArchaaS"

MODE=""
ENV_FILE=${ENV_FILE:-"$ROOT_DIR/.env.prod"}
TF_VARS_FILE=${TF_VARS_FILE:-terraform.v2.tfvars}
TF_WORKSPACE=${TF_WORKSPACE:-prod}
REMOTE_DIR=${REMOTE_DIR:-/opt/housing-microservices}
REMOTE_COMPOSE_FILE=${REMOTE_COMPOSE_FILE:-docker-compose.ec2.yml}
REMOTE_ENV_FILE=${REMOTE_ENV_FILE:-.env.prod}
SSH_USER=${SSH_USER:-ec2-user}
SSH_PORT=${SSH_PORT:-22}
SSH_KEY=${SSH_KEY:-}
DESTROY_FIRST=0
NO_SYNC=0
NO_BUILD=0
HOST=""
PATCH_FILE=""
TARGET_PATH=""
PATCH_SERVICE=""

log() { echo "[deploy_stack] $*" >&2; }
die() { log "ERROR: $*"; exit 1; }

usage() {
  cat <<'EOF'
Usage: scripts/deploy_stack.sh --mode MODE [options]

Modes (required):
  full-redeploy   Run terraform apply (optionally destroy first) and redeploy services via docker compose.
  services-only   Sync code/env + rebuild/restart services only (no terraform).
  hot-patch       Copy a local file into a running service container and restart it.

Options:
  --env-file PATH       Env file to source/ship (default: .env.prod).
  --tfvars FILE         Terraform tfvars file (default: terraform.v2.tfvars).
  --workspace NAME      Terraform workspace (default: prod).
  --host HOST           Override remote host/IP (defaults to POSTGRES_HOST from env file or terraform output).
  --ssh-user USER       SSH user (default: ec2-user).
  --ssh-key PATH        SSH key path (default: terraform output or ~/.ssh/id_rsa if present).
  --ssh-port PORT       SSH port (default: 22).
  --remote-dir PATH     Remote deployment directory (default: /opt/housing-microservices).
  --remote-env PATH     Remote env filename (default: .env.prod).
  --remote-compose PATH Remote compose filename (default: docker-compose.ec2.yml).
  --destroy-first       (full-redeploy) Run terraform destroy before apply (confirmation required).
  --no-sync             Skip code/env sync (use existing remote checkout).
  --no-build            Skip docker compose build step (reuse existing images).
  --patch-file PATH     (hot-patch) Local file to copy into the container.
  --target-path PATH    (hot-patch) Absolute target path inside the container.
  --service NAME        (hot-patch) Compose service name to patch/restart.
  -h, --help            Show this help.

Examples:
  scripts/deploy_stack.sh --mode full-redeploy
  scripts/deploy_stack.sh --mode services-only --host 1.2.3.4 --no-build
  scripts/deploy_stack.sh --mode hot-patch --service agent-api --patch-file services/agent-api/src/main.py --target-path /app/services/agent-api/src/main.py
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --mode) MODE="$2"; shift 2 ;;
      --env-file) ENV_FILE="$2"; shift 2 ;;
      --tfvars) TF_VARS_FILE="$2"; shift 2 ;;
      --workspace) TF_WORKSPACE="$2"; shift 2 ;;
      --host) HOST="$2"; shift 2 ;;
      --ssh-user) SSH_USER="$2"; shift 2 ;;
      --ssh-key) SSH_KEY="$2"; shift 2 ;;
      --ssh-port) SSH_PORT="$2"; shift 2 ;;
      --remote-dir) REMOTE_DIR="$2"; shift 2 ;;
      --remote-env) REMOTE_ENV_FILE="$2"; shift 2 ;;
      --remote-compose) REMOTE_COMPOSE_FILE="$2"; shift 2 ;;
      --destroy-first) DESTROY_FIRST=1; shift ;;
      --no-sync) NO_SYNC=1; shift ;;
      --no-build) NO_BUILD=1; shift ;;
      --patch-file) PATCH_FILE="$2"; shift 2 ;;
      --target-path) TARGET_PATH="$2"; shift 2 ;;
      --service) PATCH_SERVICE="$2"; shift 2 ;;
      -h|--help) usage; exit 0 ;;
      *) die "Unknown argument: $1" ;;
    esac
  done

  [[ -n "$MODE" ]] || die "--mode is required"
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
    name = name.strip()
    value = value.strip().strip('"').strip("'")
    values[name] = value

print(values.get(key, default))
PY
}

ensure_local_prereqs() {
  local cmds=(ssh scp tar python3)
  [[ "$MODE" == "full-redeploy" ]] && cmds+=(terraform)
  for cmd in "${cmds[@]}"; do
    command -v "$cmd" >/dev/null 2>&1 || die "Required command '$cmd' not found"
  done
}

resolve_env_file() {
  [[ -f "$ENV_FILE" ]] || die "Env file $ENV_FILE not found"
}

resolve_host() {
  if [[ -z "$HOST" ]]; then
    HOST=$(read_env_value "$ENV_FILE" POSTGRES_HOST "")
  fi
  if [[ -z "$HOST" && -d "$TF_DIR" ]]; then
    HOST=$(terraform -chdir="$TF_DIR" output -raw ec2_public_ip 2>/dev/null || true)
  fi
  [[ -n "$HOST" ]] || die "Unable to resolve remote host; set POSTGRES_HOST in env or pass --host"
}

resolve_ssh_key() {
  if [[ -n "$SSH_KEY" ]]; then
    [[ -f "$SSH_KEY" ]] || die "SSH key $SSH_KEY not found"
    return
  fi

  if [[ -d "$TF_DIR" ]]; then
    local tf_key
    tf_key=$(terraform -chdir="$TF_DIR" output -raw ec2_private_key_path 2>/dev/null || true)
    if [[ -n "$tf_key" ]]; then
      # Resolve relative paths relative to TF_DIR
      if [[ "$tf_key" == ./* ]]; then
        tf_key="$TF_DIR/${tf_key#./}"
      elif [[ "$tf_key" != /* ]]; then
        tf_key="$TF_DIR/$tf_key"
      fi
      if [[ -f "$tf_key" ]]; then
        SSH_KEY="$tf_key"
        return
      fi
    fi
  fi

  if [[ -f "$HOME/.ssh/id_rsa" ]]; then
    SSH_KEY="$HOME/.ssh/id_rsa"
  fi
}

ssh_opts() {
  local opts=(-o "StrictHostKeyChecking=no" -p "$SSH_PORT")
  [[ -n "$SSH_KEY" ]] && opts+=(-i "$SSH_KEY")
  echo "${opts[@]}"
}

scp_opts() {
  local opts=(-o "StrictHostKeyChecking=no" -P "$SSH_PORT")
  [[ -n "$SSH_KEY" ]] && opts+=(-i "$SSH_KEY")
  echo "${opts[@]}"
}

ensure_remote_prereqs() {
  log "Ensuring docker and compose exist on $HOST"
  ssh $(ssh_opts) "$SSH_USER@$HOST" bash -s <<'EOF'
set -euo pipefail
sudo dnf update -y >/dev/null
command -v docker >/dev/null 2>&1 || sudo dnf install -y docker >/dev/null
command -v git >/dev/null 2>&1 || sudo dnf install -y git >/dev/null
command -v tar >/dev/null 2>&1 || sudo dnf install -y tar >/dev/null
sudo systemctl enable --now docker >/dev/null
if ! docker compose version >/dev/null 2>&1; then
  sudo mkdir -p /usr/libexec/docker/cli-plugins
  ARCH=$(uname -m)
  OS=$(uname -s)
  sudo curl -sSL "https://github.com/docker/compose/releases/download/v2.31.0/docker-compose-${OS}-${ARCH}" \
    -o /usr/libexec/docker/cli-plugins/docker-compose
  sudo chmod +x /usr/libexec/docker/cli-plugins/docker-compose
fi
sudo usermod -aG docker "$USER" || true
EOF
}

sync_repo() {
  [[ "$NO_SYNC" -eq 0 ]] || { log "Skipping code sync (--no-sync)"; return; }
  log "Syncing repository to $SSH_USER@$HOST:$REMOTE_DIR"
  ssh $(ssh_opts) "$SSH_USER@$HOST" bash -s <<EOF
set -euo pipefail
if [[ -z "$REMOTE_DIR" || "$REMOTE_DIR" == "/" ]]; then
  echo "Refusing to clean unsafe REMOTE_DIR: '$REMOTE_DIR'" >&2
  exit 1
fi
sudo rm -rf "$REMOTE_DIR"
sudo mkdir -p "$REMOTE_DIR"
sudo chown -R "$SSH_USER":"$SSH_USER" "$REMOTE_DIR"
EOF
  local excludes=(
    --exclude ".git"
    --exclude ".venv"
    --exclude ".venv.*"
    --exclude ".mypy_cache"
    --exclude ".pytest_cache"
    --exclude "__pycache__"
    --exclude "node_modules"
    --exclude "dist"
    --exclude "ArchaaS/.terraform"
    --exclude "ArchaaS/terraform.tfstate*"
    --exclude "terraform.tfstate*"
    --exclude ".kilocode"
    --exclude "Documents"
  )
  # Suppress macOS extended attribute warnings (harmless - Linux tar ignores them)
  # Filter LIBARCHIVE.xattr warnings on both local and remote sides
  COPYFILE_DISABLE=1 tar -czf - "${excludes[@]}" -C "$ROOT_DIR" . 2> >(grep -v "LIBARCHIVE.xattr" >&2) | \
    ssh $(ssh_opts) "$SSH_USER@$HOST" "tar --warning=no-unknown-keyword -xzf - -C '$REMOTE_DIR' 2>&1 | grep -v 'LIBARCHIVE.xattr' || tar -xzf - -C '$REMOTE_DIR' 2>&1 | grep -v 'LIBARCHIVE.xattr'"
  scp $(scp_opts) "$ENV_FILE" "$SSH_USER@$HOST:$REMOTE_DIR/$REMOTE_ENV_FILE"
}

prepare_remote_env() {
  log "Updating remote env file with host-aware URLs"
  ssh $(ssh_opts) "$SSH_USER@$HOST" \
    DEPLOY_HOST="$HOST" \
    REMOTE_ENV_FILE="$REMOTE_ENV_FILE" \
    REMOTE_DIR="$REMOTE_DIR" bash -s <<'EOF'
set -euo pipefail
cd "$REMOTE_DIR"
if [[ ! -f "$REMOTE_ENV_FILE" ]]; then
  echo "Missing $REMOTE_ENV_FILE in $REMOTE_DIR" >&2
  exit 1
fi

python3 - <<'PY'
import os
from pathlib import Path

env_path = Path(os.environ["REMOTE_ENV_FILE"])
host = os.environ["DEPLOY_HOST"]

def parse_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        if not raw or raw.lstrip().startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        data[key.strip()] = value.strip()
    return data

env = parse_env(env_path)
pg_user = env.get("POSTGRES_USER", "vizonomy_user")
pg_password = env.get("POSTGRES_PASSWORD", "postgres")
pg_db = env.get("POSTGRES_DB", env.get("AGENT_API_DB", "housing"))
auth_db = env.get("AUTH_DB", "auth_db")
pg_port = env.get("POSTGRES_PORT", "5432")
agent_port = env.get("AGENT_API_PORT", "8000")
auth_port = env.get("AUTH_SERVICE_PORT", "5001")
user_port = env.get("USER_SERVICE_PORT", "5002")
ingest_port = env.get("INGESTION_SERVICE_PORT", "8085")

overrides = {
    "POSTGRES_HOST": host,
    "DATABASE_URL": f"postgresql+asyncpg://{pg_user}:{pg_password}@{host}:{pg_port}/{pg_db}",
    "AUTH_DATABASE_URL": f"postgresql://{pg_user}:{pg_password}@{host}:{pg_port}/{auth_db}",
    "AGENT_BASE_URL": f"http://{host}:{agent_port}",
    "AUTH_BASE_URL": f"http://{host}:{auth_port}",
    "AUTH_SERVICE_URL": f"http://{host}:{auth_port}",
    "USER_SERVICE_URL": f"http://{host}:{user_port}",
    "INGEST_BASE_URL": f"http://{host}:{ingest_port}",
    "INGESTION_SERVICE_PORT": ingest_port,
    "USE_LOCALSTACK": "0",
    "AWS_ENDPOINT_URL": "",
}

lines = env_path.read_text().splitlines()
updated: list[str] = []
seen: set[str] = set()
for line in lines:
    if not line or line.lstrip().startswith("#") or "=" not in line:
        updated.append(line)
        continue
    key, _, _ = line.partition("=")
    key = key.strip()
    if key in overrides:
        updated.append(f"{key}={overrides[key]}")
        seen.add(key)
    else:
        updated.append(line)

for key, value in overrides.items():
    if key not in seen:
        updated.append(f"{key}={value}")

env_path.write_text("\n".join(updated) + "\n")
PY
EOF
}

stop_conflicts() {
  local ports=("80" "5001" "5002" "8000" "8085" "3000" "5432")
  log "Stopping containers and processes bound to service ports (${ports[*]})"
  ssh $(ssh_opts) "$SSH_USER@$HOST" bash -s <<EOF
set -euo pipefail
for port in ${ports[*]}; do
  # Stop Docker containers using the port
  ids=\$(sudo docker ps --filter "publish=\${port}" --format '{{.ID}}')
  if [[ -n "\$ids" ]]; then
    sudo docker stop \$ids >/dev/null 2>&1 || true
    sudo docker rm \$ids >/dev/null 2>&1 || true
  fi
  # Also stop any stopped containers that might be holding the port
  stopped_ids=\$(sudo docker ps -a --filter "publish=\${port}" --format '{{.ID}}')
  if [[ -n "\$stopped_ids" ]]; then
    sudo docker rm \$stopped_ids >/dev/null 2>&1 || true
  fi
  # Kill any processes directly using the port (fallback)
  pids=\$(sudo lsof -ti:\${port} 2>/dev/null || true)
  if [[ -n "\$pids" ]]; then
    sudo kill -9 \$pids >/dev/null 2>&1 || true
  fi
done
EOF
}

deploy_services() {
  ensure_remote_prereqs
  sync_repo
  prepare_remote_env
  stop_conflicts

  local compose_cmd="sudo docker compose --env-file $REMOTE_ENV_FILE -f $REMOTE_COMPOSE_FILE"
  local services="postgres init-migrations agent-api auth-service user-service ingestion-service frontend-service nginx"
  local up_flags="--remove-orphans -d"
  [[ "$NO_BUILD" -eq 1 ]] || up_flags="$up_flags --build --pull always"

  log "Rebuilding and restarting services on $HOST"
  ssh $(ssh_opts) "$SSH_USER@$HOST" bash -s <<EOF
set -euo pipefail
cd "$REMOTE_DIR"
# Ensure compose is fully down and ports are released
$compose_cmd down --remove-orphans || true
sleep 2
# Start services
$compose_cmd up $up_flags $services
EOF

  log "Health checks:"
  log "  curl -fsS http://$HOST/health"
  log "  curl -fsS http://$HOST:5001/health"
  log "  curl -fsS http://$HOST:5002/v1/health"
  log "  curl -fsS http://$HOST:8000/health"
  log "  curl -fsS http://$HOST:8085/health"
  log "  curl -fsS http://$HOST:3000/health"
  log "  psql -h $HOST -p ${POSTGRES_PORT:-5432} -U ${POSTGRES_USER:-vizonomy_user} -c 'select 1'"
}

run_terraform() {
  log "Initializing terraform (workspace=$TF_WORKSPACE tfvars=$TF_VARS_FILE)"
  terraform -chdir="$TF_DIR" init -upgrade >/dev/null
  if terraform -chdir="$TF_DIR" workspace list | grep -q "$TF_WORKSPACE"; then
    terraform -chdir="$TF_DIR" workspace select "$TF_WORKSPACE" >/dev/null
  else
    terraform -chdir="$TF_DIR" workspace new "$TF_WORKSPACE" >/dev/null
  fi

  if [[ "$DESTROY_FIRST" -eq 1 ]]; then
    read -r -p "DESTROY will remove infra and likely drop data. Continue? (yes/no): " confirm
    [[ "$confirm" == "yes" ]] || die "Destroy aborted"
    terraform -chdir="$TF_DIR" destroy -auto-approve -var-file="$TF_VARS_FILE"
  fi

  terraform -chdir="$TF_DIR" apply -auto-approve -var-file="$TF_VARS_FILE"
}

hot_patch() {
  [[ -n "$PATCH_FILE" ]] || die "--patch-file is required for hot-patch"
  [[ -n "$TARGET_PATH" ]] || die "--target-path is required for hot-patch"
  [[ -n "$PATCH_SERVICE" ]] || die "--service is required for hot-patch"
  [[ -f "$PATCH_FILE" ]] || die "Patch file $PATCH_FILE not found"

  ensure_remote_prereqs
  local remote_tmp="/tmp/$(basename "$PATCH_FILE")"
  scp $(scp_opts) "$PATCH_FILE" "$SSH_USER@$HOST:$remote_tmp"

  local compose_cmd="sudo docker compose --env-file $REMOTE_ENV_FILE -f $REMOTE_COMPOSE_FILE"
  log "Copying $PATCH_FILE into $PATCH_SERVICE:$TARGET_PATH and restarting service"
  ssh $(ssh_opts) "$SSH_USER@$HOST" bash -s <<EOF
set -euo pipefail
cd "$REMOTE_DIR"
container=\$($compose_cmd ps -q "$PATCH_SERVICE")
if [[ -z "\$container" ]]; then
  echo "Container for $PATCH_SERVICE not found" >&2
  exit 1
fi
sudo docker cp "$remote_tmp" "\$container:$TARGET_PATH"
$compose_cmd restart "$PATCH_SERVICE"
EOF

  log "Hot patch applied and service restarted."
}

main() {
  parse_args "$@"
  ensure_local_prereqs
  resolve_env_file

  if [[ "$MODE" == "full-redeploy" ]]; then
    log "Mode: full-redeploy (terraform apply + service rollout). DB is preserved unless --destroy-first is used."
    run_terraform
    resolve_host
    resolve_ssh_key
    deploy_services
  elif [[ "$MODE" == "services-only" ]]; then
    log "Mode: services-only (no terraform)"
    resolve_host
    resolve_ssh_key
    deploy_services
  elif [[ "$MODE" == "hot-patch" ]]; then
    log "Mode: hot-patch"
    resolve_host
    resolve_ssh_key
    hot_patch
  else
    die "Unsupported mode: $MODE"
  fi

  log "Done."
}

main "$@"
