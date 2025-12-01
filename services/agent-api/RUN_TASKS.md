# `run_tasks.sh` Usage Guide

This script automates Codex CLI runs for the Agent API service. It reads the Epic 3 task files, renders the prompt template with the correct placeholders, and streams each task to Codex with the permissions and workflow required by `AGENTS.md`.

## Prerequisites

1. `cd services/agent-api` – paths are resolved relative to this directory.
2. `codex login` – ensure the CLI is authenticated.
3. Keep the staging area empty (the script refuses to run if `git diff --cached` is non-empty).
4. Python 3 must be on `PATH` (used for post-run diffing).

The script already follows Bash best practices recommended by Earthly’s “Understanding Bash” guide—`#!/usr/bin/env bash`, `set -euo pipefail`, defensive quoting, and helper functions for readability【earthly-bash-best-practices】.

## Command overview

```bash
./run_tasks.sh [options] [task_number...]
```

| Option | Description |
| --- | --- |
| `--dry-run` | Renders prompts, logs git diffs, skips Codex + git commits. |
| `--template <file>` | Override the default `prompt_template.txt`. Also works with `--template=path`. |
| `--help` | Print usage info. |
| `task_number` | Optional list (`03`, `05`, `12`, …). If omitted, every file in `epic-03/tasks` runs. |
| `--` | Treat everything that follows as task identifiers, even if they look like flags. |

Examples:

```bash
# Preview task 03 without invoking Codex
./run_tasks.sh 03 --dry-run

# Use a custom template for tasks 03 and 04
./run_tasks.sh --template custom_prompt.txt 03 04

# Run all tasks (real Codex run; be ready for edits/commits)
./run_tasks.sh
```

## Runtime behavior

1. **Argument parsing** – Options are accepted anywhere. The first positional argument that resolves to an existing file becomes the prompt template; everything else is treated as a task identifier.
2. **Prompt rendering** – `prompt_template.txt` includes `{{TASK_FILE}}`, `{{TASK_NUMBER}}`, `{{AGENT_GUIDE}}`, and `{{CHECKLIST}}` placeholders so each Codex run has full context.
3. **Codex invocation** – By default the script runs:<br>
   `codex exec --model gpt-5.1-codex --config 'model_reasoning_effort="medium"' --config 'approval_policy="never"' --config 'features.web_search_request=true' --sandbox danger-full-access "<prompt>"`<br>
   These flags are validated against the Codex CLI reference and configuration guide so only supported switches are passed to `codex exec`【codex-cli-reference】【codex-config-doc】.
4. **Git snapshotting** – Before and after each task, the script captures `git status --porcelain -z`, computes the delta via a small Python helper, and auto-commits only the files touched by the completed task (unless `--dry-run`).
5. **Dry runs** – With `--dry-run`, Codex/`git add`/`git commit` are skipped, but prompts and diff summaries still print so you can see exactly what would happen.

## Testing matrix

The following combinations were exercised locally using `--dry-run` to avoid real Codex work:

| Command | Notes |
| --- | --- |
| `./run_tasks.sh --dry-run` | Iterated every Epic 3 task sequentially. |
| `./run_tasks.sh 03 --dry-run` | Validated task filtering without a custom template. |
| `./run_tasks.sh ./prompt_template.txt 03 --dry-run` | Verified explicit template argument. |
| `./run_tasks.sh 03 --dry-run --template custom.txt` | Confirmed options work in any order (after adding `--template`). |

Feel free to add more spot checks (for example, targeting a small subset or using a custom prompt file) before unleashing full Codex runs.

## Implementation notes

- The script enforces clean staging to prevent committing unrelated work.
- Helper utilities (like the git diff parser) run via `uv run python …`, guaranteeing every Python process uses the project’s virtualenv.
- It automatically runs from the Agent API directory while issuing git commands from the repo root, so you can invoke it from anywhere without path glitches.
- Default Codex flags can be overridden via `CODEX_CMD` / `CODEX_FLAGS` environment variables if needed.
- All workflow instructions (plan, tracker, verification commands, checklist updates) come directly from `services/agent-api/AGENTS.md` and each task’s markdown file.

→ Keep this guide alongside `run_tasks.sh` so every teammate (or automation) knows exactly how to operate the runner safely.

---
**References**

- Codex CLI reference (`codex exec --help`) – confirms supported options (`--model`, `--config`, `--sandbox`) and shows that `--ask-for-approval` isn’t valid for `exec`, so approval is controlled via `--config approval_policy=…`.
- OpenAI Codex configuration guide – documents `model_reasoning_effort`, `approval_policy`, and feature flags like `features.web_search_request`【codex-config-doc】.
- Earthly Blog: *Understanding Bash* – recommends `#!/usr/bin/env bash`, `set -euo pipefail`, helper functions, and quoting variables for safe automation【earthly-bash-best-practices】.

[codex-cli-reference]: https://developers.openai.com/codex/cli/reference/
[codex-config-doc]: https://raw.githubusercontent.com/openai/codex/main/docs/config.md
[earthly-bash-best-practices]: https://earthly.dev/blog/understanding-bash/
