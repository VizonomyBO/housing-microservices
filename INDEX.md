# Documentation Index

Use this map to find the refreshed docs for the text-only ingestion stack, ReAct agent, and EC2 deploy workflows.

## Getting started
- **Quick run:** [QUICKSTART.md](QUICKSTART.md) — env selection, Compose start/stop, health checks.
- **Full context:** [README.md](README.md) — architecture snapshot, workflows, quality gates.
- **Architecture:** [docs/overview/system_architecture.md](docs/overview/system_architecture.md) — services, data flow, deprecations.
- **Agent design:** [docs/agents/architecture.md](docs/agents/architecture.md) — ReAct tool loop, retrieval stack, Pyodide constraints.

## Runbooks & setup
- **Local dev:** [docs/setup/local.md](docs/setup/local.md) — LocalStack-first Compose.
- **Hybrid dev:** [docs/setup/dev.md](docs/setup/dev.md) — local services with remote data plane.
- **Prod:** [docs/setup/prod.md](docs/setup/prod.md) + [docs/runbooks/prod_setup.md](docs/runbooks/prod_setup.md) — deploy + smoke via `scripts/deploy_stack.sh` and `scripts/prod_smoke_check.sh`.
- **Compose runbook:** [docs/runbooks/full_stack_compose.md](docs/runbooks/full_stack_compose.md) — start/verify/teardown for the retained services.

## Agent, retrieval, and ingestion
- [docs/agents/implementation.md](docs/agents/implementation.md) — ReAct loop, retrieval flow, citations.
- [docs/agents/retrieval_config.md](docs/agents/retrieval_config.md) — Voyage `voyage-context-3` + `rerank-2.5`, BM25+vector fusion, HyDE/HyPE, rerank filters.
- [docs/agents/rag_blueprint.md](docs/agents/rag_blueprint.md) — ingestion-first RAG blueprint, advanced techniques, prompts.
- [docs/overview/project_status.md](docs/overview/project_status.md) — current focus, deprecations, and active constraints.

## Testing & smoke
- **API smoke:** `./test-api.sh` (local stack).
- **Prod smoke:** `scripts/prod_smoke_check.sh` (ingestion upload → activation → attach → chat). See [docs/runbooks/prod_setup.md](docs/runbooks/prod_setup.md).
- **LLM eval guidance:** [docs/testing/llm_eval_quality_improvements.md](docs/testing/llm_eval_quality_improvements.md) (advanced RAG + ReAct prompts).

## Deprecations & archives
- Graph RAG, Step Functions/Lambda ingestion, Valkey cache/rate limiter, telemetry extras, and reduced-scope modes are deprecated. Legacy epics/interfaces remain for history and are labeled accordingly.
- Swagger aggregator is disabled; use FastAPI/Flask endpoints directly.

## Repo waypoints
- Services: `services/agent-api`, `services/ingestion-service`, `services/auth-service`, `services/user-service`.
- Shared data layer: `packages/shared_data_layer` (graph/workflow tables retained but deprecated/nullable).
- Scripts: `scripts/use_env.sh`, `scripts/deploy_stack.sh`, `scripts/prod_smoke_check.sh`.
