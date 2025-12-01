#!/usr/bin/env bash
set -euo pipefail

# Runs Codex tasks sequentially using the prompt template + AGENTS instructions.
# Usage:
#   ./run_tasks.sh [--dry-run] [PROMPT_TEMPLATE] [task_number...]
# - If PROMPT_TEMPLATE is omitted, defaults to ./prompt_template.txt.
# - Without task numbers, every task file in epic-03/tasks is processed.

DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --help|-h)
      cat <<'EOF'
Usage: ./run_tasks.sh [--dry-run] [PROMPT_TEMPLATE] [task_number...]

Options:
  --dry-run   Render prompts and log actions without calling Codex
              or running git commands.
EOF
      exit 0
      ;;
    *)
      break
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASKS_DIR="${SCRIPT_DIR}/epic-03/tasks"
CHECKLIST_FILE="${SCRIPT_DIR}/epic-03/CHECKLIST.md"
AGENT_GUIDE="${SCRIPT_DIR}/AGENTS.md"

if [[ $# -gt 0 ]]; then
  PROMPT_TEMPLATE="$1"
  shift
else
  PROMPT_TEMPLATE="${SCRIPT_DIR}/prompt_template.txt"
fi

if [[ ! -f "${PROMPT_TEMPLATE}" ]]; then
  echo "❌ Prompt template not found: ${PROMPT_TEMPLATE}" >&2
  exit 1
fi

if [[ ! -d "${TASKS_DIR}" ]]; then
  echo "❌ Tasks directory not found: ${TASKS_DIR}" >&2
  exit 1
fi

if [[ ! -f "${AGENT_GUIDE}" ]]; then
  echo "❌ Agent guide missing: ${AGENT_GUIDE}" >&2
  exit 1
fi

TASK_SELECTION=("$@")

readarray -t ALL_TASK_FILES < <(ls "${TASKS_DIR}"/task-*.md 2>/dev/null | sort)
if [[ ${#ALL_TASK_FILES[@]} -eq 0 ]]; then
  echo "⚠️  No task files found under ${TASKS_DIR}" >&2
  exit 0
fi

if ! git diff --cached --quiet; then
  echo "❌ Staging area is not clean. Please commit or reset staged changes before running this script." >&2
  exit 1
fi

select_task_files() {
  if [[ ${#TASK_SELECTION[@]} -eq 0 ]]; then
    printf "%s\n" "${ALL_TASK_FILES[@]}"
    return
  fi

  local selected=()
  for identifier in "${TASK_SELECTION[@]}"; do
    if [[ -f "${identifier}" ]]; then
      selected+=("$(cd "$(dirname "${identifier}")" && pwd)/$(basename "${identifier}")")
      continue
    fi

    local matches=()
    while IFS= read -r path; do
      matches+=("$path")
    done < <(ls "${TASKS_DIR}"/task-"${identifier}"*.md 2>/dev/null || true)

    if [[ ${#matches[@]} -eq 0 ]]; then
      echo "⚠️  No task file matched '${identifier}'. Skipping." >&2
      continue
    fi

    selected+=("${matches[@]}")
  done

  if [[ ${#selected[@]} -eq 0 ]]; then
    echo "⚠️  No valid tasks selected." >&2
    exit 1
  fi

  printf "%s\n" "${selected[@]}" | sort
}

render_prompt() {
  local template="$1"
  local task_file="$2"
  local task_basename
  task_basename="$(basename "${task_file}")"
  local task_number
  task_number="$(echo "${task_basename}" | grep -oE '[0-9]+')"

  local prompt="${template//\{\{TASK_FILE\}\}/${task_file}}"
  prompt="${prompt//\{\{TASK_BASENAME\}\}/${task_basename}}"
  prompt="${prompt//\{\{TASK_NUMBER\}\}/${task_number}}"
  prompt="${prompt//\{\{AGENT_GUIDE\}\}/${AGENT_GUIDE}}"
  prompt="${prompt//\{\{CHECKLIST\}\}/${CHECKLIST_FILE}}"

  printf "%s" "${prompt}"
}

collect_status_snapshot() {
  local output_file="$1"
  git status --porcelain=1 -z > "${output_file}"
}

diff_new_files() {
  local before_file="$1"
  local after_file="$2"
  python <<'PY' "${before_file}" "${after_file}"
import sys
from pathlib import Path

def to_set(path: str) -> set[str]:
    data = Path(path).read_bytes()
    entries = [e for e in data.split(b"\0") if e]
    files: set[str] = set()
    i = 0
    while i < len(entries):
        entry = entries[i]
        status = entry[:2].decode("utf-8", errors="replace")
        payload = entry[3:].decode("utf-8", errors="replace")
        if payload:
            files.add(payload)
        if status and status[0] in {"R", "C"}:
            if i + 1 < len(entries):
                files.add(entries[i + 1].decode("utf-8", errors="replace"))
                i += 2
                continue
        i += 1
    return files

before_paths = to_set(sys.argv[1])
after_paths = to_set(sys.argv[2])
new_paths = sorted(p for p in after_paths - before_paths if p)
if new_paths:
    print("\n".join(new_paths))
PY
}

print_changed_files() {
  local list="$1"
  while IFS= read -r path; do
    [[ -z "${path}" ]] && continue
    printf '   • %s\n' "${path}"
  done <<< "${list}"
}

PROMPT_BODY="$(<"${PROMPT_TEMPLATE}")"
if [[ -n "${CODEX_CMD:-}" ]]; then
  read -r -a CODEX_CMD_ARR <<<"${CODEX_CMD}"
else
  CODEX_CMD_ARR=(codex exec)
fi

if [[ -n "${CODEX_FLAGS:-}" ]]; then
  read -r -a CODEX_FLAGS_ARR <<<"${CODEX_FLAGS}"
else
  CODEX_FLAGS_ARR=(
    --model
    "gpt-5.1-codex"
    --config
    'model_reasoning_effort="medium"'
    --sandbox
    danger-full-access
    --ask-for-approval
    never
    --search
  )
fi

if (( DRY_RUN )); then
  echo "🧪 Dry run enabled: Codex invocation and git commits will be skipped."
fi

echo "🔍 Using template: ${PROMPT_TEMPLATE}"
echo "📁 Tasks dir:     ${TASKS_DIR}"
echo "📘 Agent guide:   ${AGENT_GUIDE}"
echo "🤖 Codex cmd:     ${CODEX_CMD_ARR[*]} ${CODEX_FLAGS_ARR[*]}"
echo

while IFS= read -r task_path; do
  [[ -z "${task_path}" ]] && continue
  if [[ ! -f "${task_path}" ]]; then
    echo "⚠️  Skipping missing task file: ${task_path}" >&2
    continue
  fi
  task_name="$(basename "${task_path}")"
  task_number="$(echo "${task_name}" | grep -oE '[0-9]+')"

  echo "---------------------------------------------------"
  echo "🚀 Starting ${task_name}"

  prompt_text="$(render_prompt "${PROMPT_BODY}" "${task_path}")"

  echo "📝 Prompt to Codex:"
  echo "----------------------------------------"
  printf "%s\n" "${prompt_text}"
  echo "----------------------------------------"

  tmp_before="$(mktemp)"
  collect_status_snapshot "${tmp_before}"

  if (( DRY_RUN )); then
    echo "[dry-run] Skipping Codex execution for ${task_name}."
  else
    if ! "${CODEX_CMD_ARR[@]}" "${CODEX_FLAGS_ARR[@]}" "${prompt_text}"; then
      echo "❌ Codex failed on ${task_name}. Aborting to avoid cascading errors." >&2
      rm -f "${tmp_before}"
      exit 1
    fi
  fi

  tmp_after="$(mktemp)"
  collect_status_snapshot "${tmp_after}"

  new_files="$(diff_new_files "${tmp_before}" "${tmp_after}")"
  rm -f "${tmp_before}" "${tmp_after}"

  if [[ -n "${new_files}" ]]; then
    echo "🗃️  Files changed by this task:"
    print_changed_files "${new_files}"
    if (( DRY_RUN )); then
      echo "[dry-run] Would git add/commit the files above for task ${task_number}."
    else
      mapfile -t files_to_commit <<<"${new_files}"
      filtered_files=()
      for path in "${files_to_commit[@]}"; do
        [[ -z "${path}" ]] && continue
        filtered_files+=("${path}")
      done

      if [[ ${#filtered_files[@]} -eq 0 ]]; then
        echo "⚠️  No valid files detected after filtering; skipping commit."
      else
        git add -- "${filtered_files[@]}"
        if git diff --cached --quiet; then
          echo "⚠️  No staged changes detected after add; skipping commit."
        else
          commit_msg="feat(agent-api): automated task ${task_number}"
          git commit -m "${commit_msg}"
          echo "💾 Committed ${#filtered_files[@]} file(s) for ${task_name}."
        fi
      fi
    fi
  else
    echo "⚠️  No new files to commit for ${task_name}."
  fi

  echo "✅ Completed ${task_name}"
done < <(select_task_files)

echo "🎉 All requested tasks processed."
