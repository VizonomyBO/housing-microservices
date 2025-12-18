# How to Run Agent API Evals (Prod, Pytest)

Use the eval harness under `services/agent-api/tests/evals` to exercise the Agent API end-to-end (chat + SSE, attachments, retrieval/rerank) against prod using the preloaded MEX corpus and eval user.

## Prereqs
- `.env.prod` in repo root with: `EVAL_USER_EMAIL=eval_user@example.com`, `EVAL_USER_PASSWORD=TestPass123!`, `EVAL_USER_ID=52f96e69-2232-4215-878e-45041858ba30`, `OPENAI_API_KEY`, `VOYAGE_API_KEY`, and the default prod base URLs/ports. The eval fixtures auto-load `.env.prod` and override templated URLs to `http://52.207.140.87:8000` and `http://52.207.140.87:5001`.
- Network access to prod Agent API and OpenAI.

## Commands
- All evals: `cd services/agent-api && uv run pytest tests/evals -m eval --maxfail=1`
- Streaming focus: `uv run pytest tests/evals -m eval_sse --maxfail=1`

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
- Eval runs fail fast if required env vars are missing. OPENAI is mandatory; no stubs or fallbacks.
- Artifacts include inputs, outputs, citations, and metric scores for auditability. Delete or rotate as needed (gitignored).
