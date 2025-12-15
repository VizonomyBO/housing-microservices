#!/usr/bin/env bash
set -euo pipefail

# Ensures the shared automation Python environment exists and is up to date.
# This environment powers root-level scripts (Terraform orchestration, remote DB setup, etc.).

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
TOOL_ENV="${ROOT_DIR}/.venv.tooling"
PYTHON_VERSION=${PYTHON_VERSION:-3.13}
UV_BIN=${UV_BIN:-$(command -v uv || true)}

if [[ -z "$UV_BIN" ]]; then
  echo "ERROR: uv not found on PATH. Install uv (https://github.com/astral-sh/uv) first." >&2
  exit 1
fi

if [[ ! -x "${TOOL_ENV}/bin/python" ]]; then
  echo "Creating tooling virtualenv at ${TOOL_ENV} (Python ${PYTHON_VERSION})..."
  "$UV_BIN" venv --python "$PYTHON_VERSION" "$TOOL_ENV"
fi

echo "Syncing tooling dependencies from requirements.tooling.txt..."
(
  cd "$ROOT_DIR"
  "$UV_BIN" pip sync -p "${TOOL_ENV}/bin/python" requirements.tooling.txt
  "$UV_BIN" pip install -p "${TOOL_ENV}/bin/python" -e packages/shared_data_layer >/dev/null
)

echo "Tooling environment ready at ${TOOL_ENV}"
