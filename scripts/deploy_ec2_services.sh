#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
DEFAULT_ENV_FILE="$ROOT_DIR/.env.active"
FALLBACK_ENV_FILE="$ROOT_DIR/.env.prod.aws"
TF_DIR="$ROOT_DIR/ArchaaS"

REMOTE_DIR=${REMOTE_DIR:-/opt/housing-microservices}
REMOTE_COMPOSE_FILE=${REMOTE_COMPOSE_FILE:-docker-compose.ec2.yml}
REMOTE_ENV_FILE=${REMOTE_ENV_FILE:-.env.ec2}
REMOTE_ACTIVE_ENV=${REMOTE_ACTIVE_ENV:-.env.active}

HOUSING_FRONTEND_REPO_URL=${HOUSING_FRONTEND_REPO_URL:-https://github.com/VizonomyBO/housing-frontend.git}
HOUSING_FRONTEND_BRANCH=${HOUSING_FRONTEND_BRANCH:-start-conversation}
HOUSING_FRONTEND_PATH=${HOUSING_FRONTEND_PATH:-/housing-frontend}
HOUSING_FRONTEND_BUILD_DIR=${HOUSING_FRONTEND_BUILD_DIR:-dist}

SSH_USER=${SSH_USER:-ec2-user}
SSH_PORT=${SSH_PORT:-22}
SSH_KEY=${SSH_KEY:-}

ENV_FILE=${ENV_FILE:-}
ACTION=deploy
OPEN_PORTS=0
INCLUDE_SWAGGER=0
NO_SYNC=0
NO_BUILD=0

log() { echo "[deploy_ec2] $*" >&2; }
die() { log "ERROR: $*"; exit 1; }

usage() {
  cat <<'EOF'
Deploy auth-service, user-service, and agent-api onto the EC2 host that also runs Postgres (marker-service removed/legacy).

Usage:
  scripts/deploy_ec2_services.sh [options]

Options:
  --host HOST              EC2 public host/IP (defaults to POSTGRES_HOST from env or terraform output).
  --env-file PATH          Base env file to ship to EC2 (default: .env.active if present else .env.prod.aws).
  --remote-dir PATH        Remote deployment directory (default: /opt/housing-microservices).
  --ssh-user USER          SSH user (default: ec2-user).
  --ssh-key PATH           SSH key (default: ArchaaS terraform output if present).
  --ssh-port PORT          SSH port (default: 22).
  --action ACTION          deploy (default), stop, or restart.
  --open-ports             Use AWS CLI to open required ports (8000,5001,5002,8085,3000) on the EC2 security group.
  --include-swagger        Include swagger-service (port 3000).
  --no-sync                Skip rsync/tar upload (assumes code already on the host).
  --no-build               Skip docker compose build/pull (use existing images).
  -h, --help               Show this help text.

Env vars (optional):
  HOUSING_FRONTEND_REPO_URL   Repo to clone (default: VizonomyBO/housing-frontend.git).
  HOUSING_FRONTEND_BRANCH     Branch/ref to deploy (default: main).
  HOUSING_FRONTEND_PATH       Path on EC2 host (default: /housing-frontend).

Examples:
  scripts/use_env.sh aws
  scripts/deploy_ec2_services.sh --host 52.207.140.87 --open-ports
  scripts/deploy_ec2_services.sh --action stop
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
    name = name.strip()
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]
    values[name] = value

print(values.get(key, default))
PY
}

resolve_env_file() {
  if [[ -n "$ENV_FILE" ]]; then
    [[ -f "$ENV_FILE" ]] || die "Env file $ENV_FILE not found."
    return
  fi
  if [[ -f "$DEFAULT_ENV_FILE" ]]; then
    ENV_FILE="$DEFAULT_ENV_FILE"
  elif [[ -f "$FALLBACK_ENV_FILE" ]]; then
    ENV_FILE="$FALLBACK_ENV_FILE"
  else
    die "No env file found (.env.active or .env.prod.aws)."
  fi
}

resolve_host() {
  local env_host
  env_host=$(read_env_value "$ENV_FILE" POSTGRES_HOST "")
  if [[ -n "$env_host" ]]; then
    REMOTE_HOST="$env_host"
  elif [[ -d "$TF_DIR" ]]; then
    REMOTE_HOST=$(terraform -chdir="$TF_DIR" output -raw ec2_public_ip 2>/dev/null || true)
  fi
  [[ -n "${REMOTE_HOST:-}" ]] || die "REMOTE_HOST not set; pass --host or add POSTGRES_HOST to $ENV_FILE."
}

resolve_ssh_key() {
  if [[ -n "$SSH_KEY" ]]; then
    [[ -f "$SSH_KEY" ]] || die "SSH key $SSH_KEY not found."
    return
  fi
  if [[ -d "$TF_DIR" ]]; then
    local tf_key
    tf_key=$(terraform -chdir="$TF_DIR" output -raw ec2_private_key_path 2>/dev/null || true)
    if [[ -n "$tf_key" && -f "$tf_key" ]]; then
      SSH_KEY="$tf_key"
      return
    fi
  fi
  if [[ -f "$HOME/.ssh/id_rsa" ]]; then
    SSH_KEY="$HOME/.ssh/id_rsa"
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --host)
        REMOTE_HOST="$2"
        shift 2
        ;;
      --env-file)
        ENV_FILE="$2"
        shift 2
        ;;
      --remote-dir)
        REMOTE_DIR="$2"
        shift 2
        ;;
      --ssh-user)
        SSH_USER="$2"
        shift 2
        ;;
      --ssh-key)
        SSH_KEY="$2"
        shift 2
        ;;
      --ssh-port)
        SSH_PORT="$2"
        shift 2
        ;;
      --action)
        ACTION="$2"
        shift 2
        ;;
      --open-ports)
        OPEN_PORTS=1
        shift
        ;;
      --include-swagger)
        INCLUDE_SWAGGER=1
        shift
        ;;
      --no-sync)
        NO_SYNC=1
        shift
        ;;
      --no-build)
        NO_BUILD=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "Unknown argument: $1"
        ;;
    esac
  done
}

ensure_local_prereqs() {
  for cmd in ssh scp tar python3; do
    command -v "$cmd" >/dev/null 2>&1 || die "Required command '$cmd' not found."
  done
}

open_security_group_ports() {
  [[ "$OPEN_PORTS" -eq 1 ]] || return 0
  command -v aws >/dev/null 2>&1 || die "aws CLI not found; install awscli or omit --open-ports."

  local aws_env
  AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-$(read_env_value "$ENV_FILE" AWS_ACCESS_KEY_ID "")}
  AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-$(read_env_value "$ENV_FILE" AWS_SECRET_ACCESS_KEY "")}
  AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN:-$(read_env_value "$ENV_FILE" AWS_SESSION_TOKEN "")}
  AWS_REGION=${AWS_REGION:-$(read_env_value "$ENV_FILE" AWS_REGION "us-east-1")}
  [[ -n "$AWS_ACCESS_KEY_ID" && -n "$AWS_SECRET_ACCESS_KEY" ]] || die "AWS credentials missing; set in $ENV_FILE for --open-ports."

  local instance_id sg_id
  if [[ -d "$TF_DIR" ]]; then
    instance_id=$(terraform -chdir="$TF_DIR" output -raw ec2_instance_id 2>/dev/null || true)
  fi
  if [[ -z "$instance_id" ]]; then
    instance_id=$(AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" AWS_SESSION_TOKEN="$AWS_SESSION_TOKEN" AWS_REGION="$AWS_REGION" AWS_DEFAULT_REGION="$AWS_REGION" \
      aws ec2 describe-instances \
      --filters "Name=ip-address,Values=$REMOTE_HOST" "Name=instance-state-name,Values=running" \
      --query 'Reservations[0].Instances[0].InstanceId' --output text 2>/dev/null || true)
  fi
  [[ -n "$instance_id" && "$instance_id" != "None" ]] || die "Unable to resolve instance ID for $REMOTE_HOST (required for --open-ports)."

  sg_id=$(AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" AWS_SESSION_TOKEN="$AWS_SESSION_TOKEN" AWS_REGION="$AWS_REGION" AWS_DEFAULT_REGION="$AWS_REGION" \
    aws ec2 describe-instances --instance-ids "$instance_id" --query 'Reservations[0].Instances[0].SecurityGroups[0].GroupId' --output text 2>/dev/null || true)
  [[ -n "$sg_id" && "$sg_id" != "None" ]] || die "Unable to resolve security group for instance $instance_id."

  local ports=("$AGENT_API_PORT" "$AUTH_SERVICE_PORT" "$USER_SERVICE_PORT" "$INGESTION_SERVICE_PORT")
  [[ "$INCLUDE_SWAGGER" -eq 0 ]] || ports+=("$SWAGGER_SERVICE_PORT")

  # Add port 80 for nginx gateway
  ports+=("80")

  log "Opening inbound ports on SG $sg_id: ${ports[*]}"
  for port in "${ports[@]}"; do
    AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" AWS_SESSION_TOKEN="$AWS_SESSION_TOKEN" AWS_REGION="$AWS_REGION" AWS_DEFAULT_REGION="$AWS_REGION" \
      aws ec2 authorize-security-group-ingress --group-id "$sg_id" --protocol tcp --port "$port" --cidr 0.0.0.0/0 >/dev/null 2>&1 || \
      log "Ingress for port $port already present or could not be added (check manually)."
  done
}

sync_repo_to_remote() {
  [[ "$NO_SYNC" -eq 0 ]] || { log "Skipping code sync (--no-sync)"; return; }
  log "Syncing repo to $SSH_USER@$REMOTE_HOST:$REMOTE_DIR (excluding build artifacts)"
  local tar_excludes=(
    --exclude ".git"
    --exclude ".mypy_cache"
    --exclude ".pytest_cache"
    --exclude "__pycache__"
    --exclude ".venv"
    --exclude ".venv.*"
    --exclude "ArchaaS/.terraform"
    --exclude "ArchaaS/terraform.tfstate.d"
    --exclude "terraform.tfstate*"
    --exclude "node_modules"
    --exclude "dist"
    --exclude "ArchaaS/dist/*.pem"
  )

  tar -czf - "${tar_excludes[@]}" -C "$ROOT_DIR" . | \
    ssh "${SSH_OPTS[@]}" "$SSH_USER@$REMOTE_HOST" "sudo mkdir -p '$REMOTE_DIR' && sudo chown -R '$SSH_USER':'$SSH_USER' '$REMOTE_DIR' && tar -xzf - -C '$REMOTE_DIR'"

  scp "${SCP_OPTS[@]}" "$ENV_FILE" "$SSH_USER@$REMOTE_HOST:$REMOTE_DIR/$REMOTE_ENV_FILE"
}

sync_housing_frontend_repo() {
  [[ "$NO_SYNC" -eq 0 ]] || { log "Skipping housing-frontend sync (--no-sync)"; return; }
  log "Syncing housing-frontend to $SSH_USER@$REMOTE_HOST:$HOUSING_FRONTEND_PATH (branch=$HOUSING_FRONTEND_BRANCH)"

  ssh "${SSH_OPTS[@]}" "$SSH_USER@$REMOTE_HOST" \
    HOUSING_FRONTEND_REPO_URL="$HOUSING_FRONTEND_REPO_URL" \
    HOUSING_FRONTEND_BRANCH="$HOUSING_FRONTEND_BRANCH" \
    HOUSING_FRONTEND_PATH="$HOUSING_FRONTEND_PATH" \
    SSH_USER="$SSH_USER" bash -s <<'EOF'
set -euo pipefail

REPO_URL="$HOUSING_FRONTEND_REPO_URL"
BRANCH="$HOUSING_FRONTEND_BRANCH"
TARGET="$HOUSING_FRONTEND_PATH"
OWNER="$SSH_USER"

if [[ -d "$TARGET/.git" ]]; then
  cd "$TARGET"
  git fetch --prune origin
  git checkout "$BRANCH"
  git reset --hard "origin/$BRANCH"
  git clean -fdx
else
  # Remove old directory if it exists but isn't a git repo
  sudo rm -rf "$TARGET"
  # Create the directory owned by the deploy user so git clone works
  sudo mkdir -p "$TARGET"
  sudo chown "$OWNER":"$OWNER" "$TARGET"
  # Clone into the existing empty directory
  git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$TARGET"
fi
EOF
}

build_housing_frontend() {
  log "Building housing-frontend (branch=$HOUSING_FRONTEND_BRANCH)"
  ssh "${SSH_OPTS[@]}" "$SSH_USER@$REMOTE_HOST" \
    HOUSING_FRONTEND_PATH="$HOUSING_FRONTEND_PATH" \
    HOUSING_FRONTEND_BUILD_DIR="$HOUSING_FRONTEND_BUILD_DIR" bash -s <<'EOF'
set -euo pipefail

TARGET="$HOUSING_FRONTEND_PATH"
BUILD_DIR="$HOUSING_FRONTEND_BUILD_DIR"

if [[ ! -d "$TARGET" || ! -f "$TARGET/package.json" ]]; then
  echo "housing-frontend not present or missing package.json; skipping build"
  exit 0
fi

cd "$TARGET"

if ! command -v node >/dev/null 2>&1 || [[ "$(node -v | sed 's/v//' | cut -d. -f1)" -lt 20 ]]; then
  echo "Installing Node.js 20.x..."
  curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
  sudo dnf install -y nodejs >/dev/null
fi

if command -v npm >/dev/null 2>&1; then
  if [[ -f package-lock.json ]]; then
    npm ci --legacy-peer-deps || npm install --legacy-peer-deps
  else
    npm install --legacy-peer-deps
  fi
  npm run build 2>/dev/null || npm run build:prod 2>/dev/null || echo "No build script found; skipping build step"
else
  echo "npm not available even after Node install; skipping build"
  exit 0
fi

if [[ -d "build" ]]; then
  echo "Build complete: $TARGET/build"
  
  # Kill any existing frontend process
  pkill -f "react-router-serve" 2>/dev/null || true
  
  # Start the frontend SSR server on port 3000
  echo "Starting frontend SSR server on port 3000..."
  cd "$TARGET"
  PORT=3000 nohup npm start > /tmp/frontend.log 2>&1 &
  sleep 3
  
  if curl -s http://localhost:3000 > /dev/null; then
    echo "Frontend server started successfully on port 3000"
  else
    echo "WARNING: Frontend server may not have started. Check /tmp/frontend.log"
    cat /tmp/frontend.log | tail -20
  fi
else
  echo "Build directory 'build' not found after build; check frontend scripts"
fi
EOF
}

prepare_remote_env() {
  log "Preparing remote env file ($REMOTE_ENV_FILE → $REMOTE_ACTIVE_ENV) on $REMOTE_HOST"
  ssh "${SSH_OPTS[@]}" "$SSH_USER@$REMOTE_HOST" bash -s <<EOF
set -euo pipefail
cd "$REMOTE_DIR"
if [[ ! -f "$REMOTE_ENV_FILE" ]]; then
  echo "Missing $REMOTE_ENV_FILE in $REMOTE_DIR" >&2
  exit 1
fi

AWS_ENV_FILE="$REMOTE_ENV_FILE" ./scripts/use_env.sh aws >/dev/null

DEPLOY_HOST="$REMOTE_HOST" \
AGENT_PORT="$AGENT_API_PORT" \
AUTH_PORT="$AUTH_SERVICE_PORT" \
USER_PORT="$USER_SERVICE_PORT" \
SWAGGER_PORT="$SWAGGER_SERVICE_PORT" \
PG_PORT="$POSTGRES_PORT" \
INGEST_PORT="$INGESTION_SERVICE_PORT" \
python3 - <<'PY'
import os
from pathlib import Path

env_path = Path(".env.active")
if not env_path.exists():
    raise SystemExit(".env.active missing after use_env.sh")

host = os.environ["DEPLOY_HOST"]
agent_port = os.environ["AGENT_PORT"]
auth_port = os.environ["AUTH_PORT"]
user_port = os.environ["USER_PORT"]
swagger_port = os.environ["SWAGGER_PORT"]
pg_port = os.environ["PG_PORT"]
ingest_port = os.environ["INGEST_PORT"]

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

overrides = {
    "POSTGRES_HOST": host,
    "DATABASE_URL": f"postgresql+asyncpg://{pg_user}:{pg_password}@{host}:{pg_port}/{pg_db}",
    "AUTH_DATABASE_URL": f"postgresql://{pg_user}:{pg_password}@{host}:{pg_port}/{auth_db}",
    "AGENT_BASE_URL": f"http://{host}:{agent_port}",
    "AUTH_BASE_URL": f"http://{host}:{auth_port}",
    "AUTH_SERVICE_URL": f"http://{host}:{auth_port}",
    "USER_SERVICE_URL": f"http://{host}:{user_port}",
    "ACCOUNT_SERVICE_URL": f"http://{host}:{auth_port}",
    "SWAGGER_BASE_URL": f"http://{host}:{swagger_port}",
    "INGEST_BASE_URL": f"http://{host}:{ingest_port}",
    "INGESTION_SERVICE_PORT": ingest_port,
    "INGESTION_SIGNING_SECRET": env.get("INGESTION_SIGNING_SECRET", env.get("JWT_SECRET_KEY", "")),
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

env_path.write_text("\\n".join(updated) + "\\n")
PY
EOF
}

ensure_remote_prereqs() {
  log "Ensuring docker/python/git are present on $REMOTE_HOST"
  ssh "${SSH_OPTS[@]}" "$SSH_USER@$REMOTE_HOST" bash -s <<'EOF'
set -euo pipefail
sudo dnf update -y >/dev/null
command -v git >/dev/null 2>&1 || sudo dnf install -y git >/dev/null
command -v docker >/dev/null 2>&1 || sudo dnf install -y docker >/dev/null
command -v python3 >/dev/null 2>&1 || sudo dnf install -y python3 >/dev/null
command -v tar >/dev/null 2>&1 || sudo dnf install -y tar >/dev/null
command -v curl >/dev/null 2>&1 || sudo dnf install -y curl >/dev/null
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

compose_services() {
  local services="agent-api auth-service user-service ingestion-service nginx-gateway"
  [[ "$INCLUDE_SWAGGER" -eq 0 ]] || services="$services swagger-service"
  echo "$services"
}

stop_conflicting_containers() {
  local ports=("$AGENT_API_PORT" "$AUTH_SERVICE_PORT" "$USER_SERVICE_PORT" "$INGESTION_SERVICE_PORT" "80")
  [[ "$INCLUDE_SWAGGER" -eq 0 ]] || ports+=("$SWAGGER_SERVICE_PORT")
  log "Stopping containers already bound to: ${ports[*]}"
  ssh "${SSH_OPTS[@]}" "$SSH_USER@$REMOTE_HOST" bash -s <<EOF
set -euo pipefail
for port in ${ports[*]}; do
  ids=\$(sudo docker ps --filter "publish=\${port}" --format '{{.ID}}')
  if [[ -n "\$ids" ]]; then
    echo "Stopping containers on port \$port: \$ids"
    sudo docker stop \$ids >/dev/null
    sudo docker rm \$ids >/dev/null
  fi
done
EOF
}

run_compose() {
  local services
  services=$(compose_services)
  local compose_cmd="sudo docker compose --env-file $REMOTE_ACTIVE_ENV -f $REMOTE_COMPOSE_FILE"
  [[ "$INCLUDE_SWAGGER" -eq 0 ]] || compose_cmd="$compose_cmd --profile swagger"

  case "$ACTION" in
    deploy)
      local up_flags=("--remove-orphans" "-d")
      [[ "$NO_BUILD" -eq 1 ]] || up_flags+=("--build" "--pull" "always")
      log "Starting services on $REMOTE_HOST ($services)"
      ssh "${SSH_OPTS[@]}" "$SSH_USER@$REMOTE_HOST" "cd '$REMOTE_DIR' && { $compose_cmd down --remove-orphans || true; $compose_cmd up ${up_flags[*]} $services; }"
      ;;
    restart)
      log "Restarting services on $REMOTE_HOST ($services)"
      ssh "${SSH_OPTS[@]}" "$SSH_USER@$REMOTE_HOST" "cd '$REMOTE_DIR' && $compose_cmd restart $services"
      ;;
    stop)
      log "Stopping services on $REMOTE_HOST"
      ssh "${SSH_OPTS[@]}" "$SSH_USER@$REMOTE_HOST" "cd '$REMOTE_DIR' && $compose_cmd down"
      ;;
    *)
      die "Unsupported action: $ACTION"
      ;;
  esac
}

main() {
  parse_args "$@"
  ensure_local_prereqs
  resolve_env_file
  resolve_host
  resolve_ssh_key

  AGENT_API_PORT=$(read_env_value "$ENV_FILE" AGENT_API_PORT "8000")
  AUTH_SERVICE_PORT=$(read_env_value "$ENV_FILE" AUTH_SERVICE_PORT "5001")
  USER_SERVICE_PORT=$(read_env_value "$ENV_FILE" USER_SERVICE_PORT "5002")
  INGESTION_SERVICE_PORT=$(read_env_value "$ENV_FILE" INGESTION_SERVICE_PORT "8085")
  SWAGGER_SERVICE_PORT=$(read_env_value "$ENV_FILE" SWAGGER_SERVICE_PORT "3000")
  POSTGRES_PORT=$(read_env_value "$ENV_FILE" POSTGRES_PORT "5432")

  SSH_OPTS=(-o "StrictHostKeyChecking=no" -p "$SSH_PORT")
  SCP_OPTS=(-o "StrictHostKeyChecking=no" -P "$SSH_PORT")
  [[ -z "$SSH_KEY" ]] || { SSH_OPTS+=(-i "$SSH_KEY"); SCP_OPTS+=(-i "$SSH_KEY"); }

  log "Using env file: $ENV_FILE"
  log "Resolved host: $REMOTE_HOST"
  log "SSH user/key: $SSH_USER ${SSH_KEY:-<default>}"
  log "Ports → agent-api:$AGENT_API_PORT auth:$AUTH_SERVICE_PORT user:$USER_SERVICE_PORT ingestion:$INGESTION_SERVICE_PORT swagger:$SWAGGER_SERVICE_PORT"

  open_security_group_ports
  ensure_remote_prereqs
  sync_repo_to_remote
  sync_housing_frontend_repo
  build_housing_frontend
  prepare_remote_env
  stop_conflicting_containers
  run_compose

  log "Done. Health checks (from your machine):"
  log "  curl -fsS http://$REMOTE_HOST/health                          # nginx gateway"
  log "  curl -fsS http://$REMOTE_HOST:$AUTH_SERVICE_PORT/health"
  log "  curl -fsS http://$REMOTE_HOST:$USER_SERVICE_PORT/v1/health"
  log "  curl -fsS http://$REMOTE_HOST:$AGENT_API_PORT/health"
  log "  curl -fsS http://$REMOTE_HOST:$INGESTION_SERVICE_PORT/health"
  [[ "$INCLUDE_SWAGGER" -eq 0 ]] || log "  curl -fsS http://$REMOTE_HOST:$SWAGGER_SERVICE_PORT/health"
  log "Frontend: http://$REMOTE_HOST/"
}

main "$@"
