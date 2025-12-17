# Task Plan: 009-local-end-to-end-smoke

## Summary
Investigate why the local end-to-end smoke flow is returning empty answers/no citations despite the recent report of passing results, and fix the pipeline so chat answers are grounded with citations.

## Impacted Files
- scripts/local_smoke.sh
- services/agent-api (retrieval/agent flow)
- services/ingestion-service (ingestion pipeline)
- packages/shared_data_layer (if schema/query changes are required)
- docs/runbooks/full_stack_compose.md (usage note if needed)

## Risks
- Running the smoke flow mutates local Postgres data; collisions with existing users/docs may affect results.
- LLM and Voyage calls may fail if env vars are missing or rate limited.
- Compose services may be stale; missing rebuilds can mask fixes.

## Ordered Steps
1. Load env via `env_file=$(scripts/use_env.sh local); set -a && source "$env_file" && set +a`; confirm compose stack is healthy (agent, ingestion, auth, user, Postgres).
2. Review `scripts/local_smoke.sh` validation criteria and question set to understand when it flags empty answers/citations.
3. Reproduce the issue by running the smoke script against `.env.local`, capturing answers/citations and relevant service logs (agent + ingestion).
4. Identify the failure point (ingestion status/polling, attachment mapping, retrieval/rerank, prompt) and implement targeted fixes using existing libraries.
5. Re-run the smoke script to verify non-empty, citation-backed answers; update tests/docs if behavior changed.

## Sources
- .kilocode/rules/memory-bank/*.md
- AGENTS.md
- tasks/009-local-end-to-end-smoke.md
- docs/runbooks/full_stack_compose.md
