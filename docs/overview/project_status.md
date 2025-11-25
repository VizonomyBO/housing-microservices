<!-- markdownlint-disable MD013 MD022 MD032 -->

# Design Deep Dive

## Final Recommendation: FastAPI Gateway + LangGraph Service
- **Gateway duties** now live inside a FastAPI application (served by uvicorn/gunicorn). Async handlers, HTTP/2 SSE streaming, and Python-native auth/rate-limit middleware let us terminate TLS, enforce policy, and expose `/v1/*` routes without context switches to another runtime. If sustained concurrency demands it, we can still re-platform the outer API into Go later by reusing the same REST contracts.
- **Agentic / ML workloads** continue to run in Python (LangGraph + tool stack). Co-locating the gateway and agent service in the same FastAPI process means we can share Pydantic models, DB clients, and caching primitives while keeping workload-specific routers (agent vs. ingestion vs. admin) isolated with dependency injection.
- **Platform decomposition**: Within FastAPI we maintain separate routers for north-south traffic and internal callbacks, plus background task pools for ingestion + async jobs. Future Go migration simply swaps the north-south router while keeping the LangGraph ASGI app mounted internally.

## Pending Definition Work

### 1. API & Event Contracts
- Completed in [interfaces/api_contracts.md](../interfaces/api_contracts.md), covering the REST schemas (`system_architecture.md:244-254`), ingestion event payloads, and LangGraph envelopes end-to-end.

### 2. Authentication, Authorization, and Tokens
- **Completed in [security/auth_and_tokens.md](../security/auth_and_tokens.md)**.
- Covers upstream token handover, `user_id` persistence, and the exclusion of IAM roles in favor of handcrafted User Service roles.

### 3. Database Schema & Persistence Rules
- Completed in [data/schema_and_persistence.md](../data/schema_and_persistence.md), now covering user-owned docs, country-scoped base docs, hash deduplication, `conversation_documents` ref-counting, and the garbage-collection rules other workstreams must respect.

### 4. Retrieval & Agent Configuration
- Completed in [agents/retrieval_config.md](../agents/retrieval_config.md), locking down the configuration knobs (`hybrid_k`, RRF windows, reranker limits, loop/repair thresholds, cache TTLs, chunking) along with fallback logic, score/metric emission, and the rules for merging base + user documents with `visibility_override`.

### 5. Asynchronous Jobs & Queues
- **Completed in [infrastructure/async_jobs.md](../infrastructure/async_jobs.md)**.
- Details SQS payloads, deduplication strategies, retry policies, and ref-counting safety for ingestion and export jobs.

### 6. Inter-Service Communication Details
- **Completed in [infrastructure/communication_and_resilience.md](../infrastructure/communication_and_resilience.md)**.
- Defines the co-located service model (FastAPI ↔ LangGraph via in-process function calls).
- Specifies resilience patterns: Health checks (`/health/live`, `/health/ready`), Circuit Breakers (User Service), and Timeouts.

### 7. Observability & Operations
- **Completed in [infrastructure/observability_and_ops.md](../infrastructure/observability_and_ops.md)**.
- Defines Logging (JSON), Tracing (OTEL), and Metrics (Business/System).
- Includes Alerting thresholds and the Operations Runbook (Deploy, Rollback, Hotfix).

### 8. Infrastructure & Deployment
- **Completed in [infrastructure/infrastructure_and_deployment.md](../infrastructure/infrastructure_and_deployment.md)**.
- Defines Terraform IaC strategy, VPC layout, and Hybrid ECS+Lambda compute.
- Outlines CI/CD pipelines using GitHub Actions and Secrets Management.
