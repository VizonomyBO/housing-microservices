#!/usr/bin/env bash
set -euo pipefail

# Recreates the remote AWS stack (EC2 + Postgres) via Terraform, captures the
# generated SSH key, patches .env.prod with the latest public IP, and runs
# the remote database bootstrap script.

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
TF_DIR="$ROOT_DIR/ArchaaS"
DEFAULT_ENV_FILE="$ROOT_DIR/.env.prod"
ENV_FILE=${ENV_FILE:-}
if [[ -z "$ENV_FILE" ]]; then
  ENV_FILE="$DEFAULT_ENV_FILE"
fi
TF_VARS_FILE=${TF_VARS_FILE:-terraform.v2.tfvars}
WORKSPACE_NAME=${TF_WORKSPACE:-prod}
DESTROY_FIRST=0

usage() {
  cat <<'EOF'
Usage: scripts/provision_remote_stack.sh [options]

Options:
  --destroy-first        Run 'terraform destroy' before apply (default: rely on apply-driven replacement).
  --tfvars FILE          Override the tfvars file (default: terraform.v2.tfvars).
  --workspace NAME       Override terraform workspace (default: prod).
  -h, --help             Show this help text.

Environment:
  ENV_FILE               Path to env file to source for AWS creds (default: .env.prod).
  TF_VARS_FILE           Same as --tfvars.
  TF_WORKSPACE           Same as --workspace (input only; script unsets before running terraform).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --destroy-first)
      DESTROY_FIRST=1
      shift
      ;;
    --tfvars)
      TF_VARS_FILE="$2"
      shift 2
      ;;
    --workspace)
      WORKSPACE_NAME="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

# Capture input workspace but clear TF_WORKSPACE from the environment so terraform
# does not warn about an override.
if [[ -n "${TF_WORKSPACE:-}" ]]; then
  unset TF_WORKSPACE
fi

for cmd in terraform jq python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Required command '$cmd' not found in PATH." >&2
    exit 1
  fi
done

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file $ENV_FILE not found." >&2
  exit 1
fi

echo "Loading AWS credentials and stack env vars from $ENV_FILE"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ -z "${AWS_ACCESS_KEY_ID:-}" || -z "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
  echo "AWS credentials missing in $ENV_FILE (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)." >&2
  exit 1
fi

TF_VARS_PATH="$TF_DIR/$TF_VARS_FILE"
if [[ ! -f "$TF_VARS_PATH" ]]; then
  echo "tfvars file $TF_VARS_PATH not found." >&2
  exit 1
fi

echo "Initializing Terraform in $TF_DIR"
terraform -chdir="$TF_DIR" init -upgrade >/dev/null

if terraform -chdir="$TF_DIR" workspace list | grep -q "$WORKSPACE_NAME"; then
  terraform -chdir="$TF_DIR" workspace select "$WORKSPACE_NAME" >/dev/null
else
  terraform -chdir="$TF_DIR" workspace new "$WORKSPACE_NAME" >/dev/null
fi

if [[ "$DESTROY_FIRST" -eq 1 ]]; then
  echo "Destroying existing stack (workspace=$WORKSPACE_NAME)..."
  terraform -chdir="$TF_DIR" destroy -auto-approve -var-file="$TF_VARS_FILE"
else
  echo "Skipping standalone terraform destroy (apply will handle replacements)."
fi

echo "Applying Terraform stack (workspace=$WORKSPACE_NAME)..."
terraform -chdir="$TF_DIR" apply -auto-approve -var-file="$TF_VARS_FILE"

SUMMARY_JSON=$(terraform -chdir="$TF_DIR" output -json summary)
PUBLIC_IP=$(jq -r '.ec2.public_ip' <<<"$SUMMARY_JSON")
if [[ -z "$PUBLIC_IP" || "$PUBLIC_IP" == "null" ]]; then
  echo "Failed to capture EC2 public IP from terraform outputs." >&2
  exit 1
fi

PRIVATE_KEY_PATH=$(terraform -chdir="$TF_DIR" output -raw ec2_private_key_path 2>/dev/null || true)
if [[ -n "$PRIVATE_KEY_PATH" ]]; then
  echo "Generated SSH key stored at: $PRIVATE_KEY_PATH"
else
  echo "Using pre-existing EC2 key pair (no local PEM generated)."
fi

echo "Updating POSTGRES_HOST in $ENV_FILE → $PUBLIC_IP"
python3 - "$ENV_FILE" "$PUBLIC_IP" <<'PY'
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
public_ip = sys.argv[2]
lines = env_path.read_text().splitlines()
for idx, line in enumerate(lines):
    if line.startswith("POSTGRES_HOST="):
        lines[idx] = f"POSTGRES_HOST={public_ip}"
        break
else:
    lines.append(f"POSTGRES_HOST={public_ip}")
env_path.write_text("\n".join(lines) + "\n")
PY

echo "Re-running remote database bootstrap..."
REMOTE_DB_HOST="$PUBLIC_IP" POSTGRES_HOST="$PUBLIC_IP" "$ROOT_DIR/scripts/setup_remote_databases.sh"

echo "Remote stack provisioning complete."
