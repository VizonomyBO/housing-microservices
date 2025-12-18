# How to Run Agent API Evals (Prod, Pytest)

Use the eval harness under `services/agent-api/tests/evals` to exercise the Agent API end-to-end (chat + SSE, attachments, retrieval/rerank) against prod using the preloaded MEX corpus and eval user.

## Prereqs
- `.env.evals` is required (no `.env.prod` fallback). It should mirror prod settings but set `AGENT_BASE_URL=http://localhost:8000` for the local Agent API and include `AUTH_BASE_URL`, `AUTH_SHARED_SECRET`, `EVAL_USER_EMAIL=eval_user@example.com`, `EVAL_USER_PASSWORD=TestPass123!`, `EVAL_USER_ID=52f96e69-2232-4215-878e-45041858ba30`, `OPENAI_API_KEY`, and `VOYAGE_API_KEY`.
- Install Deno locally via `curl -fsSL https://deno.land/install.sh | sh` (defaults to `$HOME/.deno/bin`). Ensure `~/.deno/bin` is on `PATH` for non-login shells, e.g. `export DENO_INSTALL=\"$HOME/.deno\" && export PATH=\"$DENO_INSTALL/bin:$PATH\"`, then verify with `deno --version`. Do **not** add PATH overrides to `.env.evals` or `.env.prod`.
- Network access to prod services (auth/doc metadata/DB) and OpenAI/Voyage.

## Commands
- Load env and run blocking evals (streaming disabled for now):
  ```bash
  set -a && source .env.evals && set +a
  cd services/agent-api
  uv run pytest tests/evals -m eval --maxfail=1
  ```
- Code-tool evals run locally via Deno (Pyodide sandbox) and do not require `PYODIDE_BASE_URL`; just keep Deno on `PATH`. Streaming evals remain skipped by marker.

## Data & Scenarios
- Dataset lives in `services/agent-api/tests/evals/datasets/shared_mex_arg.yaml` and references the active MEX corpus doc IDs already owned by the eval user. Do **not** upload new copies; attach existing IDs.
- Scenarios specify attachments, prompts, response mode (blocking/stream), and metrics (citation coverage/precision/recall, retrieval relevance, latency, grounding, truthfulness, bias).

## Harness Structure
- `core/client.py`: HTTP client for auth/login, conversations, attachments, blocking + SSE chat.
- `core/scenarios.py`: Scenario + metric models, YAML loader.
- `core/runner.py`: Executes scenarios, attaches docs, runs metrics, writes artifacts.
- `core/metrics.py` + `core/judges.py`: Deterministic checks + LLM-as-judge (`gpt-5.1`, high reasoning effort).
- `core/telemetry.py`: Parses responses/citations, SSE streams; artifacts flatten to `services/agent-api/tests/evals/artifacts/<timestamp>_<scenario>.json` (gitignored).

## Notes
- Eval runs fail fast if required env vars are missing. OPENAI is mandatory; no stubs or fallbacks. Streaming evals are currently skipped by marker until SSE duplication is resolved.
- Artifacts include inputs, outputs, citations, and metric scores for auditability. Delete or rotate as needed (gitignored).
