#!/usr/bin/env bash
set -euo pipefail

echo "[deprecated] Use scripts/deploy_stack.sh --mode full-redeploy \"\$@\""
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/deploy_stack.sh" --mode full-redeploy "$@"
