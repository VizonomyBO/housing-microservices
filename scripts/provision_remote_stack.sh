#!/usr/bin/env bash
set -euo pipefail

echo "[deprecated] Terraform provisioning is handled by scripts/deploy_stack.sh --mode full-redeploy."
echo "Pass --destroy-first if you explicitly need a destroy/apply cycle."
exit 1
