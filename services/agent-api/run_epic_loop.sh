#!/usr/bin/env bash
set -euo pipefail

# Wrapper that repeatedly invokes run_tasks.sh for a given epic until every
# checklist item is checked. After each run it re-reads the checklist so
# newly inserted fix tasks are executed automatically.

usage() {
  cat <<'EOF'
Usage: ./run_epic_loop.sh --epic <DIR> [options]

Options:
  --epic <DIR>        Path to the epic directory (must contain CHECKLIST.md). Required.
  --sleep <SECONDS>   Seconds to wait before retrying after a failure (default: 5).
  --max-retries <N>   Maximum consecutive failures before exiting (default: unlimited).
  --run-tasks <PATH>  Path to run_tasks.sh (default: ./run_tasks.sh next to this script).
  --dry-run           Print the next task and exit without running Codex.
  --help              Show this message.

Examples:
  ./run_epic_loop.sh --epic epic-reduced-e2e
  ./run_epic_loop.sh --epic epic-root-compose --sleep 10 --max-retries 3
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_TASKS_SCRIPT="${SCRIPT_DIR}/run_tasks.sh"
EPIC_DIR=""
SLEEP_SECONDS=5
MAX_RETRIES=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --epic)
      shift
      [[ $# -gt 0 ]] || { echo "❌ --epic requires a directory." >&2; exit 1; }
      EPIC_DIR="$1"
      ;;
    --sleep)
      shift
      [[ $# -gt 0 ]] || { echo "❌ --sleep requires a value." >&2; exit 1; }
      SLEEP_SECONDS="$1"
      ;;
    --max-retries)
      shift
      [[ $# -gt 0 ]] || { echo "❌ --max-retries requires a value." >&2; exit 1; }
      MAX_RETRIES="$1"
      ;;
    --run-tasks)
      shift
      [[ $# -gt 0 ]] || { echo "❌ --run-tasks requires a path." >&2; exit 1; }
      RUN_TASKS_SCRIPT="$1"
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "❌ Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
  shift || true
done

if [[ -z "$EPIC_DIR" ]]; then
  echo "❌ --epic <DIR> is required." >&2
  usage
  exit 1
fi

if [[ ! "$EPIC_DIR" = /* ]]; then
  EPIC_DIR="${SCRIPT_DIR}/${EPIC_DIR}"
fi

if [[ ! -d "$EPIC_DIR" ]]; then
  echo "❌ Epic directory not found: $EPIC_DIR" >&2
  exit 1
fi

CHECKLIST_FILE="${EPIC_DIR}/CHECKLIST.md"
if [[ ! -f "$CHECKLIST_FILE" ]]; then
  echo "❌ Checklist not found: $CHECKLIST_FILE" >&2
  exit 1
fi

if [[ ! -x "$RUN_TASKS_SCRIPT" ]]; then
  echo "❌ run_tasks.sh not executable at $RUN_TASKS_SCRIPT" >&2
  exit 1
fi

next_task_number() {
  python3 - "$CHECKLIST_FILE" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
try:
  lines = path.read_text().splitlines()
except FileNotFoundError:
  sys.exit(1)

pattern_task = re.compile(r'Task\s+(\d+)')
pattern_any = re.compile(r'(\d+)')

for raw in lines:
  if "- [ ]" not in raw:
    continue
  match = pattern_task.search(raw)
  if not match:
    match = pattern_any.search(raw)
  if not match:
    continue
  number = int(match.group(1))
  print(f"{number:02d}")
  sys.exit(0)

sys.exit(1)
PY
}

failure_count=0

while true; do
  if ! task="$(next_task_number)"; then
    echo "✅ All tasks in $(basename "$EPIC_DIR") are complete."
    break
  fi

  echo "➡️  Executing task ${task} per $(basename "$CHECKLIST_FILE")"
  if (( DRY_RUN )); then
    echo "[dry-run] Would run: $RUN_TASKS_SCRIPT --epic $EPIC_DIR $task"
    break
  fi

  if "$RUN_TASKS_SCRIPT" --epic "$EPIC_DIR" "$task"; then
    failure_count=0
    continue
  fi

  failure_count=$((failure_count + 1))
  echo "⚠️  run_tasks.sh failed for task ${task} (attempt ${failure_count})."
  if (( MAX_RETRIES > 0 && failure_count >= MAX_RETRIES )); then
    echo "❌ Reached max retries (${MAX_RETRIES}). Exiting."
    exit 1
  fi
  echo "🔁 Sleeping ${SLEEP_SECONDS}s before re-checking the checklist."
  sleep "$SLEEP_SECONDS"
done
