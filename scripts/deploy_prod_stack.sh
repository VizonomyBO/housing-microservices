#!/usr/bin/env bash
set -euo pipefail

# Idempotent prod deployment helper.
# - Applies Terraform (ArchaaS) using the selected tfvars/workspace.
# - Updates env with the latest EC2 host and reboots services on the EC2 box via docker-compose.ec2.yml.
# - Leaves AWS resources intact on repeat runs; pass --destroy-first for a fresh apply.

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
DEFAULT_ENV="$ROOT_DIR/.env.prod"
PROVISION_SCRIPT="$ROOT_DIR/scripts/provision_remote_stack.sh"
DEPLOY_SCRIPT="$ROOT_DIR/scripts/deploy_ec2_services.sh"

ENV_FILE=${ENV_FILE:-}
TF_VARS_FILE=${TF_VARS_FILE:-terraform.v2.tfvars}
TF_WORKSPACE=${TF_WORKSPACE:-prod}
RUN_TERRAFORM=1
RUN_DEPLOY=1
DESTROY_FIRST=0
INCLUDE_SWAGGER=0
OPEN_PORTS=0
NO_BUILD=0
NO_SYNC=0

log() { echo "[deploy_prod_stack] $*" >&2; }
die() { log "ERROR: $*"; exit 1; }

usage() {
  cat <<'EOF'
Usage: scripts/deploy_prod_stack.sh [options]

Idempotent prod deploy: terraform apply + EC2 compose restart. Defaults to .env.prod.

Options:
  --env-file PATH       Env file to source (default: .env.prod).
  --tfvars FILE         Terraform tfvars file (default: terraform.v2.tfvars).
  --workspace NAME      Terraform workspace (default: prod).
  --skip-terraform      Skip terraform apply (only redeploy services).
  --skip-deploy         Skip EC2 compose deploy (only terraform).
  --destroy-first       Run terraform destroy before apply (use sparingly).
  --open-ports          Open EC2 SG ports for agent/auth/user (uses AWS CLI).
  --include-swagger     Include swagger-service in the EC2 compose run.
  --no-build            Skip compose build/pull on EC2 (re-use existing images).
  --no-sync             Skip rsync/tar upload to EC2 (code already present).
  -h, --help            Show this help text.
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --env-file)
        ENV_FILE="$2"
        shift 2
        ;;
      --tfvars)
        TF_VARS_FILE="$2"
        shift 2
        ;;
      --workspace)
        TF_WORKSPACE="$2"
        shift 2
        ;;
      --skip-terraform)
        RUN_TERRAFORM=0
        shift
        ;;
      --skip-deploy)
        RUN_DEPLOY=0
        shift
        ;;
      --destroy-first)
        DESTROY_FIRST=1
        shift
        ;;
      --open-ports)
        OPEN_PORTS=1
        shift
        ;;
      --include-swagger)
        INCLUDE_SWAGGER=1
        shift
        ;;
      --no-build)
        NO_BUILD=1
        shift
        ;;
      --no-sync)
        NO_SYNC=1
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

resolve_env_file() {
  if [[ -n "$ENV_FILE" ]]; then
    [[ -f "$ENV_FILE" ]] || die "Env file $ENV_FILE not found."
    return
  fi

  if [[ -f "$DEFAULT_ENV" ]]; then
    ENV_FILE="$DEFAULT_ENV"
    return
  fi

  die "Unable to resolve env file (.env.prod)."
}

ensure_scripts() {
  [[ -x "$PROVISION_SCRIPT" ]] || die "Missing helper: $PROVISION_SCRIPT"
  [[ -x "$DEPLOY_SCRIPT" ]] || die "Missing helper: $DEPLOY_SCRIPT"
}

main() {
  parse_args "$@"
  ensure_scripts
  resolve_env_file

  # Load env for helper defaults (helpers re-source as needed).
  set +u
  set -a && source "$ENV_FILE" && set +a
  set -u

  log "Using env file: $ENV_FILE"
  log "Terraform: workspace=$TF_WORKSPACE tfvars=$TF_VARS_FILE (destroy_first=$DESTROY_FIRST run=$RUN_TERRAFORM)"
  log "Deploy: run=$RUN_DEPLOY include_swagger=$INCLUDE_SWAGGER open_ports=$OPEN_PORTS no_build=$NO_BUILD no_sync=$NO_SYNC"

  if [[ "$RUN_TERRAFORM" -eq 1 ]]; then
    tf_args=(--tfvars "$TF_VARS_FILE" --workspace "$TF_WORKSPACE")
    [[ "$DESTROY_FIRST" -eq 1 ]] && tf_args=(--destroy-first "${tf_args[@]}")
    ENV_FILE="$ENV_FILE" TF_VARS_FILE="$TF_VARS_FILE" "$PROVISION_SCRIPT" "${tf_args[@]}"
  else
    log "Skipping terraform apply (--skip-terraform)"
  fi

  if [[ "$RUN_DEPLOY" -eq 1 ]]; then
    deploy_args=(--env-file "$ENV_FILE")
    [[ "$INCLUDE_SWAGGER" -eq 1 ]] && deploy_args+=(--include-swagger)
    [[ "$OPEN_PORTS" -eq 1 ]] && deploy_args+=(--open-ports)
    [[ "$NO_BUILD" -eq 1 ]] && deploy_args+=(--no-build)
    [[ "$NO_SYNC" -eq 1 ]] && deploy_args+=(--no-sync)
    "$DEPLOY_SCRIPT" "${deploy_args[@]}"
  else
    log "Skipping EC2 compose deploy (--skip-deploy)"
  fi

  log "Done. Recommended checks:"
  log "  set -a && source \"$ENV_FILE\" && set +a"
  log "  curl -fsS \"$AUTH_BASE_URL/v1/health\""
  log "  curl -fsS \"$AUTH_BASE_URL/v1/auth/login\" -X POST -H 'Content-Type: application/json' -d '{\"login\":\"'$PROD_DEMO_EMAIL'\",\"password\":\"'$PROD_DEMO_PASSWORD'\"}'"
  log "  curl -fsS \"$AGENT_BASE_URL/health\""
}

main "$@"
